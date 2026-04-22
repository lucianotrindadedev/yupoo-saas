"""
Worker: baixa imagens da Yupoo e envia para o Google Drive do usuário.
Roda em background thread via FastAPI BackgroundTasks.
"""
import re, time, uuid, requests, io, json, traceback
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

# ─── Scraper Yupoo ───────────────────────────────────────────────────────────

def is_valid_yupoo_image(url, title=""):
    if not url or "photo.yupoo.com" not in url:
        return False
    u = url.lower()
    t = (title or "").lower()
    blacklist = ["big.jpg", "medium.jpg", "small.jpg", "square.jpg", "thumb", "logo", "banner", "static", "placeholder", "size", "chart"]
    if any(w in u or w in t for w in blacklist): return False
    if any(f"/{w}/" in u for w in ["small", "medium", "square", "thumb"]): return False
    return True

def _extract_photo_ids_and_images(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    images = []
    photo_ids = []
    seen_ids = set()
    
    # Nome do álbum
    title_el = soup.find("span", class_="showalbum_title") or soup.find("h1") or soup.find("title")
    album_name = title_el.get_text(strip=True) if title_el else "album"
    album_name = re.sub(r'[\\/*?:"<>|]', "_", album_name)[:60].strip()

    # Estratégia JSON
    for script in soup.find_all("script"):
        text = script.string or ""
        if "JSON.parse" in text:
            try:
                # Regex robusta para capturar o conteúdo entre aspas do JSON.parse
                match = re.search(r'JSON\.parse\(([\'"])(.*?)\1\)', text, re.DOTALL)
                if match:
                    raw_content = match.group(2)
                    # Limpeza profunda do JSON escapado
                    raw_json = raw_content.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
                    data = json.loads(raw_json)
                    photos = data.get("album", {}).get("photos", [])
                    for p in photos:
                        url = p.get("origin_src") or p.get("big_src") or p.get("src")
                        if not url: continue
                        if url.startswith("//"): url = "https:" + url
                        
                        clean_url = re.sub(r'\?.*$', '', url)
                        photo_id = clean_url.split("/")[-2] if "/" in clean_url else clean_url
                        
                        if is_valid_yupoo_image(clean_url, p.get("title", "")) and photo_id not in seen_ids:
                            seen_ids.add(photo_id)
                            images.append(clean_url)
            except Exception as e:
                logger.debug(f"JSON Parse fail: {e}")

    # Fallback IDs
    for a in soup.find_all("a", href=True):
        if "/photos/" in a["href"]:
            parts = a["href"].split("/")
            if len(parts) > 2:
                pid = parts[2]
                if pid not in photo_ids: photo_ids.append(pid)

    return images, photo_ids, album_name

def _get_image_from_photo_page(session, photo_url):
    try:
        r = session.get(photo_url, timeout=15)
        if not r.ok: return None
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if "photo.yupoo.com" in a["href"] and is_valid_yupoo_image(a["href"]):
                return re.sub(r'\?.*$', '', a["href"])
        for img in soup.find_all("img", src=True):
            if is_valid_yupoo_image(img["src"]):
                return re.sub(r'\?.*$', '', img["src"])
    except: pass
    return None

def scrape_album(start_url):
    session = requests.Session()
    session.headers.update(HEADERS)
    r = session.get(start_url, timeout=25)
    r.raise_for_status()
    return _extract_photo_ids_and_images(r.text, start_url)

# ─── Store Scraper ────────────────────────────────────────────────────────────

def scrape_store_albums(store_url):
    session = requests.Session()
    session.headers.update(HEADERS)
    albums = []
    seen = set()
    parsed = urlparse(store_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    page = 1
    while True:
        url = f"{base}/albums?page={page}"
        try:
            r = session.get(url, timeout=20)
            if not r.ok: break
            soup = BeautifulSoup(r.text, "html.parser")
            found = 0
            for a in soup.find_all("a", href=True):
                m = re.search(r'/albums/(\d+)', a["href"])
                if m:
                    aid = m.group(1)
                    if aid not in seen:
                        seen.add(aid)
                        albums.append({"url": urljoin(base, f"/albums/{aid}?uid=1"), "title": a.get_text(strip=True) or aid})
                        found += 1
            if found == 0 or page > 50: break
            page += 1
            time.sleep(1)
        except: break
    return albums, parsed.netloc.split(".")[0]

# ─── Google Drive ─────────────────────────────────────────────────────────────

def _drive_create_folder(drive_token, name, parent_id=None):
    try:
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id: meta["parents"] = [parent_id]
        r = requests.post(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {drive_token}"},
            json=meta, timeout=15
        )
        return r.json().get("id")
    except Exception as e:
        logger.error(f"Drive Folder Error: {e}")
        return None

def _drive_upload(drive_token, data, filename, folder_id, mime="image/jpeg"):
    try:
        meta = {"name": filename, "parents": [folder_id]}
        boundary = "yupoo_boundary"
        body = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {drive_token}", "Content-Type": f"multipart/related; boundary={boundary}"},
            data=body, timeout=60
        )
        return r.status_code == 200
    except: return False

# ─── Execution ───────────────────────────────────────────────────────────────

def _process_images(job_id, user_id, images, destination, drive_token, folder_id, yupoo_url):
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": yupoo_url})
    processed = failed = 0
    
    for i, img_url in enumerate(images):
        # Cancel check
        conn = get_conn(); status = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()["status"]; conn.close()
        if status == "cancelled": break

        # Credit check
        if processed % 10 == 0:
            if _get_user_credits(user_id) < 1:
                _append_log(job_id, "Créditos insuficientes.")
                _update_job(job_id, status="paused")
                return True

        try:
            r = session.get(img_url, timeout=30)
            r.raise_for_status()
            fname = urlparse(img_url).path.split("/")[-1] or f"img_{i}.jpg"
            if destination == "drive" and folder_id:
                if _drive_upload(drive_token, r.content, fname, folder_id):
                    processed += 1
                    if processed % 10 == 0: _deduct_credits(user_id, 1)
                else: failed += 1
            else: processed += 1
        except Exception as e:
            failed += 1
            _append_log(job_id, f"Erro na imagem: {e}")

        _update_job(job_id, processed=processed, failed=failed)
        time.sleep(0.5)
    return False

def run_job(job_id, user_id, yupoo_url, destination, drive_token):
    try:
        _update_job(job_id, status="running")
        _append_log(job_id, "Iniciando extração...")
        
        images, photo_ids, album_name = scrape_album(yupoo_url)
        
        # Se Strategy JSON falhar, tenta detalhe por detalhe
        if not images and photo_ids:
            _append_log(job_id, "JSON falhou, tentando fallback por páginas de detalhe...")
            session = requests.Session(); session.headers.update(HEADERS)
            base = f"{urlparse(yupoo_url).scheme}://{urlparse(yupoo_url).netloc}"
            for pid in photo_ids:
                img = _get_image_from_photo_page(session, f"{base}/photos/{pid}/?uid=1")
                if img: images.append(img)
                time.sleep(0.3)

        if not images:
            _update_job(job_id, status="failed", log="Nenhuma imagem encontrada.")
            return

        _update_job(job_id, total_images=len(images))
        _append_log(job_id, f"Encontradas {len(images)} imagens.")

        folder_id = None
        if destination == "drive":
            root = _drive_create_folder(drive_token, "Yupoo Downloads")
            folder_id = _drive_create_folder(drive_token, album_name, root)
            if not folder_id:
                raise Exception("Não foi possível criar a pasta no Google Drive. Verifique sua conexão.")

        _process_images(job_id, user_id, images, destination, drive_token, folder_id, yupoo_url)
        _update_job(job_id, status="completed")

    except Exception as e:
        err_detail = traceback.format_exc()
        logger.error(f"Job Error: {err_detail}")
        _update_job(job_id, status="failed")
        _append_log(job_id, f"ERRO CRÍTICO:\n{err_detail}")

def run_store_job(job_id, user_id, store_url, destination, drive_token):
    try:
        _update_job(job_id, status="running")
        albums, store_name = scrape_store_albums(store_url)
        if not albums:
            _update_job(job_id, status="failed", log="Nenhum álbum encontrado.")
            return
            
        _append_log(job_id, f"Loja {store_name}: {len(albums)} álbuns encontrados.")
        root_id = None
        if destination == "drive":
            base_root = _drive_create_folder(drive_token, "Yupoo Downloads")
            root_id = _drive_create_folder(drive_token, store_name, base_root)

        for i, alb in enumerate(albums):
            _append_log(job_id, f"Processando álbum {i+1}/{len(albums)}: {alb['title']}")
            # Aqui simplificamos: rodamos a lógica de álbum dentro da loja
            try:
                # Re-usa a lógica do run_job para cada álbum
                images, photo_ids, album_name = scrape_album(alb['url'])
                if images:
                    folder = _drive_create_folder(drive_token, album_name, root_id) if root_id else None
                    _process_images(job_id, user_id, images, destination, drive_token, folder, alb['url'])
            except: pass
            time.sleep(2)
            
        _update_job(job_id, status="completed")
    except Exception as e:
        err_detail = traceback.format_exc()
        _update_job(job_id, status="failed")
        _append_log(job_id, f"ERRO CRÍTICO NA LOJA:\n{err_detail}")
