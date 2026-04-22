"""
Worker: baixa imagens da Yupoo e envia para o Google Drive do usuário.
Roda em background thread via FastAPI BackgroundTasks.
"""
import re, time, uuid, requests, io, json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from database import get_conn
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
}

# ─── Helpers de banco ────────────────────────────────────────────────────────

def _update_job(job_id, **kwargs):
    conn = get_conn()
    kwargs["updated_at"] = int(time.time())
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    conn.execute(f"UPDATE jobs SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()

def _append_log(job_id, msg):
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET log = log || ?, updated_at = ? WHERE id = ?",
        (f"{msg}\n", int(time.time()), job_id)
    )
    conn.commit()
    conn.close()

def _deduct_credits(user_id, amount):
    conn = get_conn()
    conn.execute("UPDATE users SET credits = MAX(0, credits - ?) WHERE id = ?", (amount, user_id))
    conn.execute(
        "INSERT INTO transactions (id, user_id, type, amount, description) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, "usage", -amount, f"Download: {amount} images")
    )
    conn.commit()
    conn.close()

def _get_user_credits(user_id):
    conn = get_conn()
    row = conn.execute("SELECT credits FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row["credits"] if row else 0

# ─── Scraper Yupoo (Lógica Premium baseada em yupoo-downloader) ───────────────

def is_valid_yupoo_image(url, title=""):
    """Filtra imagens indesejadas, variações de tamanho e lixo."""
    if not url or "photo.yupoo.com" not in url:
        return False
    
    url_l = url.lower()
    title_l = (title or "").lower()
    
    # Blacklist de termos e variações
    blacklist = [
        "big.jpg", "medium.jpg", "small.jpg", "square.jpg", "thumb", 
        "logo", "banner", "static", "placeholder", "size", "chart", "icon"
    ]
    if any(word in url_l or word in title_l for word in blacklist):
        return False
        
    # Bloqueia pastas de thumbnails explicitamente
    if any(f"/{w}/" in url_l for w in ["small", "medium", "square", "thumb"]):
        return False
        
    return True

def _extract_photo_ids_and_images(html, base_url):
    """Extrai IDs de fotos e URLs de imagens de alta resolução."""
    soup = BeautifulSoup(html, "html.parser")
    images = []
    photo_ids = []
    seen_ids = set() # photo_id deduplication
    
    # Nome do álbum
    title_el = soup.find("span", class_="showalbum_title") or soup.find("h1") or soup.find("title")
    album_name = title_el.get_text(strip=True) if title_el else "album"
    album_name = re.sub(r'[\\/*?:"<>|]', "_", album_name)[:60].strip()

    # ESTRATÉGIA 1: Extração via JSON.parse (O Segredo da Qualidade)
    for script in soup.find_all("script"):
        text = script.string or ""
        if "JSON.parse" in text:
            try:
                match = re.search(r'JSON\.parse\("(.+?)"\)', text)
                if match:
                    # Desescapa o JSON (Yupoo escapa aspas no JS)
                    raw_json = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
                    data = json.loads(raw_json)
                    photos = data.get("album", {}).get("photos", [])
                    for p in photos:
                        # Prioridade: Original > Big > Padrão
                        url = p.get("origin_src") or p.get("big_src") or p.get("src")
                        title = p.get("title", "")
                        if not url: continue
                        if url.startswith("//"): url = "https:" + url
                        
                        clean_url = re.sub(r'\?.*$', '', url)
                        # ID único da foto no path (ex: d223daef)
                        photo_id = clean_url.split("/")[-2] if "/" in clean_url else clean_url
                        
                        if is_valid_yupoo_image(clean_url, title) and photo_id not in seen_ids:
                            seen_ids.add(photo_id)
                            images.append(clean_url)
            except: pass

    # ESTRATÉGIA 2: Photo IDs para visita de páginas de detalhes (Fallback)
    # Procura por links que levam para a página individual da foto
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Pattern: /photos/username/albums/id/
        if "/photos/" in href:
            parts = href.split("/")
            if len(parts) > 2:
                pid = parts[2]
                if pid not in photo_ids:
                    photo_ids.append(pid)

    return images, photo_ids, album_name

def _get_image_from_photo_page(session, photo_url):
    """Extrai a imagem original da página de detalhes da foto."""
    try:
        r = session.get(photo_url, timeout=15)
        if not r.ok: return None
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Procura links de 'imagem original'
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "photo.yupoo.com" in href and is_valid_yupoo_image(href):
                return re.sub(r'\?.*$', '', href)

        # Procura tags img com alta resolução
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if is_valid_yupoo_image(src):
                return re.sub(r'\?.*$', '', src)
                
    except Exception as e:
        logger.warning(f"Falha ao processar página de foto {photo_url}: {e}")
    return None

def scrape_album(start_url):
    """Função principal de scraping de álbum."""
    session = requests.Session()
    session.headers.update(HEADERS)
    all_images = []
    seen = set()
    
    parsed = urlparse(start_url)
    base_store = f"{parsed.scheme}://{parsed.netloc}"

    try:
        r = session.get(start_url, timeout=25)
        r.raise_for_status()
        images, photo_ids, album_name = _extract_photo_ids_and_images(r.text, start_url)

        # 1. Adiciona imagens encontradas via JSON (mais rápido e melhor)
        for img in images:
            if img not in seen:
                seen.add(img)
                all_images.append(img)

        # 2. Se não achou imagens mas achou IDs, visita as páginas de detalhes
        # Ou se a quantidade de fotos encontradas via JSON for menor que a de IDs
        if len(all_images) < len(photo_ids):
            for pid in photo_ids:
                # Verifica se já temos essa foto pelo ID dela contido na URL
                if any(pid in img for img in all_images): continue
                
                photo_url = f"{base_store}/photos/{pid}/?uid=1"
                img_url = _get_image_from_photo_page(session, photo_url)
                if img_url and img_url not in seen:
                    seen.add(img_url)
                    all_images.append(img_url)
                time.sleep(0.4)
                
    except Exception as e:
        logger.error(f"Erro ao escaneal álbum {start_url}: {e}")

    return all_images, album_name

# ─── Store Scraper ────────────────────────────────────────────────────────────

def scrape_store_albums(store_url):
    """Scrape a Yupoo store page and return list of album URLs."""
    session = requests.Session()
    session.headers.update(HEADERS)
    albums = []
    seen = set()

    # Normalize URL to albums page
    parsed = urlparse(store_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    page = 1

    while True:
        url = f"{base}/albums?page={page}"
        try:
            r = session.get(url, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # Find album links - pattern: /albums/{id}
            found = 0
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.search(r'/albums/(\d+)', href)
                if m:
                    album_id = m.group(1)
                    if album_id not in seen:
                        seen.add(album_id)
                        full_url = urljoin(base, f"/albums/{album_id}?uid=1")
                        title = a.get_text(strip=True) or f"Album {album_id}"
                        title = re.sub(r'[\\/*?:"<>|]', "_", title)[:60].strip()
                        albums.append({"url": full_url, "title": title, "id": album_id})
                        found += 1

            if found == 0:
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.warning(f"Error scraping store page {page}: {e}")
            break

    # Get store name
    try:
        r = session.get(base, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        title_el = soup.find("title")
        store_name = title_el.get_text(strip=True) if title_el else parsed.netloc.split(".")[0]
        store_name = re.sub(r'\s*\|.*$', '', store_name).strip()
        store_name = re.sub(r'[\\/*?:"<>|]', "_", store_name)[:40]
    except:
        store_name = parsed.netloc.split(".")[0]

    return albums, store_name

# ─── Google Drive helpers ─────────────────────────────────────────────────────

def _drive_create_folder(drive_token, name, parent_id=None):
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    r = requests.post(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {drive_token}", "Content-Type": "application/json"},
        json=meta, timeout=15
    )
    return r.json().get("id")

def _drive_upload(drive_token, data, filename, folder_id, mime="image/jpeg"):
    meta = {"name": filename, "parents": [folder_id]}
    boundary = "yupoo_boundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json\r\n\r\n"
        + json.dumps(meta)
        + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--".encode()

    r = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        headers={
            "Authorization": f"Bearer {drive_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body, timeout=60
    )
    return r.status_code == 200

# ─── Job principal ────────────────────────────────────────────────────────────

def _process_images(job_id, user_id, images, destination, drive_token, folder_id, yupoo_url=None):
    """Shared logic: download and upload images for a job."""
    session = requests.Session()
    referer = yupoo_url or "https://x.yupoo.com/"
    session.headers.update({**HEADERS, "Referer": referer})
    
    processed = failed = credits_used = 0
    images_in_current_batch = 0

    conn = get_conn()
    row = conn.execute("SELECT processed, failed, credits_used FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row:
        processed = row["processed"]
        failed = row["failed"]
        credits_used = row["credits_used"]
        images_in_current_batch = processed % 10

    for i, img_url in enumerate(images):
        conn = get_conn()
        status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
        conn.close()
        if status == "cancelled":
            _append_log(job_id, "Job cancelled by user.")
            return processed, failed, credits_used, True

        if images_in_current_batch == 0:
            available = _get_user_credits(user_id)
            if available < 1:
                _append_log(job_id, f"Credits exhausted (Balance: {available}) — job paused.")
                _update_job(job_id, status="paused")
                return processed, failed, credits_used, True

        fname = urlparse(img_url).path.split("/")[-1] or f"img_{i:04d}.jpg"
        fname = re.sub(r'[\\/*?:"<>|]', "_", fname)

        try:
            r = session.get(img_url, timeout=30)
            r.raise_for_status()
            data = r.content
            mime = "image/png" if fname.endswith(".png") else "image/jpeg"

            if destination == "drive" and folder_id:
                ok = _drive_upload(drive_token, data, fname, folder_id, mime)
                if ok:
                    processed += 1
                    images_in_current_batch += 1
                    if images_in_current_batch >= 10:
                        _deduct_credits(user_id, 1)
                        credits_used += 1
                        images_in_current_batch = 0
                else:
                    failed += 1
                    _append_log(job_id, f"Upload failed: {fname}")
            else:
                processed += 1
                images_in_current_batch += 1
                if images_in_current_batch >= 10:
                    _deduct_credits(user_id, 1)
                    credits_used += 1
                    images_in_current_batch = 0

        except Exception as e:
            failed += 1
            _append_log(job_id, f"Error: {fname} — {e}")

        _update_job(job_id, processed=processed, failed=failed, credits_used=credits_used)
        time.sleep(0.4)

    return processed, failed, credits_used, False


def run_job(job_id: str, user_id: str, yupoo_url: str, destination: str, drive_token: str):
    try:
        _update_job(job_id, status="running")
        _append_log(job_id, f"Starting scraping: {yupoo_url}")

        images, album_name = scrape_album(yupoo_url)
        total = len(images)

        if total == 0:
            _update_job(job_id, status="failed", log="No images found.")
            return

        _update_job(job_id, total_images=total)
        _append_log(job_id, f"Found {total} images in album: {album_name}")

        available = _get_user_credits(user_id)
        if available < 1:
            _update_job(job_id, status="failed")
            _append_log(job_id, "Insufficient credits.")
            return

        folder_id = None
        if destination == "drive" and drive_token:
            root = _drive_create_folder(drive_token, "Yupoo Downloads")
            folder_id = _drive_create_folder(drive_token, album_name, root)
            _update_job(job_id, drive_folder_id=folder_id)
            _append_log(job_id, f"Folder created in Drive: {album_name}")

        processed, failed, credits_used, stopped = _process_images(
            job_id, user_id, images, destination, drive_token, folder_id, yupoo_url=yupoo_url
        )

        if not stopped:
            _update_job(job_id, status="completed")
            _append_log(job_id, f"Completed. {processed} sent, {failed} failed.")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        _update_job(job_id, status="failed")
        _append_log(job_id, f"Critical error: {e}")


def run_store_job(job_id: str, user_id: str, store_url: str, destination: str, drive_token: str):
    """Download all albums from a Yupoo store."""
    try:
        _update_job(job_id, status="running")
        _append_log(job_id, f"Scanning store: {store_url}")

        albums, store_name = scrape_store_albums(store_url)

        if len(albums) == 0:
            _update_job(job_id, status="failed", log="No albums found in store.")
            return

        _append_log(job_id, f"Found {len(albums)} albums in store: {store_name}")

        available = _get_user_credits(user_id)
        if available < 1:
            _update_job(job_id, status="failed")
            _append_log(job_id, "Insufficient credits.")
            return

        root_folder = None
        if destination == "drive" and drive_token:
            root = _drive_create_folder(drive_token, "Yupoo Downloads")
            root_folder = _drive_create_folder(drive_token, store_name, root)
            _update_job(job_id, drive_folder_id=root_folder)
            _append_log(job_id, f"Root folder created: {store_name}")

        total_images_all = 0
        albums_done = 0

        for album in albums:
            conn = get_conn()
            status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
            conn.close()
            if status == "cancelled":
                _append_log(job_id, "Job cancelled by user.")
                break

            if _get_user_credits(user_id) < 1:
                _append_log(job_id, "Credits exhausted — job paused.")
                _update_job(job_id, status="paused")
                return

            album_url = album["url"]
            album_title = album["title"]
            _append_log(job_id, f"[{albums_done+1}/{len(albums)}] Scraping: {album_title}")

            try:
                images, album_name = scrape_album(album_url)
                if not images:
                    _append_log(job_id, f"  No images in {album_title}, skipping.")
                    albums_done += 1
                    continue

                total_images_all += len(images)
                _update_job(job_id, total_images=total_images_all)
                _append_log(job_id, f"  Found {len(images)} images")

                album_folder = None
                if destination == "drive" and drive_token and root_folder:
                    album_folder = _drive_create_folder(drive_token, album_name or album_title, root_folder)

                processed, failed, credits_used, stopped = _process_images(
                    job_id, user_id, images, destination, drive_token, album_folder, yupoo_url=album_url
                )

                if stopped:
                    return

                albums_done += 1
                _append_log(job_id, f"  Album done: {processed} images uploaded")

            except Exception as e:
                _append_log(job_id, f"  Error in album {album_title}: {e}")
                albums_done += 1

            time.sleep(1.5) # Respeita o servidor entre álbuns

        _update_job(job_id, status="completed")
        _append_log(job_id, f"Store completed. {albums_done}/{len(albums)} albums processed.")

    except Exception as e:
        logger.error(f"Store job {job_id} failed: {e}")
        _update_job(job_id, status="failed")
        _append_log(job_id, f"Critical error: {e}")
