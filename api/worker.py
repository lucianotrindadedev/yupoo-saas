"""
Worker: baixa imagens da Yupoo e envia para o Google Drive do usuário.
Roda em background thread via FastAPI BackgroundTasks.
"""
import re, time, uuid, requests, io
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
        (str(uuid.uuid4()), user_id, "usage", -amount, f"Download de {amount} imagens")
    )
    conn.commit()
    conn.close()

def _get_user_credits(user_id):
    conn = get_conn()
    row = conn.execute("SELECT credits FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row["credits"] if row else 0

# ─── Scraper Yupoo ───────────────────────────────────────────────────────────

def _extract_images(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    images = []
    seen = set()

    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            val = img.get(attr, "")
            if val and val.startswith("http") and any(
                ext in val.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
            ):
                clean = re.sub(r'\?.*$', '', val)
                clean = re.sub(r'_\d+x\d+\.', '.', clean)
                if clean not in seen:
                    seen.add(clean)
                    images.append(clean)

    for script in soup.find_all("script"):
        text = script.string or ""
        for m in re.findall(r'https?://[^\s"\'\\]+\.(?:jpg|jpeg|png|webp)', text):
            clean = re.sub(r'\?.*$', '', m)
            if clean not in seen:
                seen.add(clean)
                images.append(clean)

    # Paginação
    next_pages = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r'[?&]page=\d+', href):
            full = urljoin(base_url, href)
            if full != base_url:
                next_pages.append(full)

    title_el = soup.find("h1") or soup.find("title")
    album_name = title_el.get_text(strip=True) if title_el else "album"
    album_name = re.sub(r'[\\/*?:"<>|]', "_", album_name)[:60].strip()

    return images, album_name, list(set(next_pages))

def scrape_album(start_url):
    session = requests.Session()
    session.headers.update(HEADERS)
    all_images, album_name = [], "album"
    visited, queue = set(), [start_url]

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            r = session.get(url, timeout=20)
            r.raise_for_status()
            imgs, name, next_pages = _extract_images(r.text, url)
            if album_name == "album":
                album_name = name
            new = [i for i in imgs if i not in all_images]
            all_images.extend(new)
            for p in next_pages:
                if p not in visited:
                    queue.append(p)
            time.sleep(0.6)
        except Exception as e:
            logger.warning(f"Erro ao scrape {url}: {e}")

    return all_images, album_name

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
    import json
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

def run_job(job_id: str, user_id: str, yupoo_url: str, destination: str, drive_token: str):
    try:
        _update_job(job_id, status="running")
        _append_log(job_id, f"Iniciando scraping: {yupoo_url}")

        images, album_name = scrape_album(yupoo_url)
        total = len(images)

        if total == 0:
            _update_job(job_id, status="failed", log="Nenhuma imagem encontrada.")
            return

        _update_job(job_id, total_images=total)
        _append_log(job_id, f"Encontradas {total} imagens no álbum: {album_name}")

        # Verifica créditos
        available = _get_user_credits(user_id)
        if available < 1:
            _update_job(job_id, status="failed")
            _append_log(job_id, "Créditos insuficientes.")
            return

        # Cria pasta no Drive
        folder_id = None
        if destination == "drive" and drive_token:
            root = _drive_create_folder(drive_token, "Yupoo Downloads")
            folder_id = _drive_create_folder(drive_token, album_name, root)
            _update_job(job_id, drive_folder_id=folder_id)
            _append_log(job_id, f"Pasta criada no Drive: {album_name}")

        session = requests.Session()
        session.headers.update(HEADERS)
        processed = failed = credits_used = 0

        for i, img_url in enumerate(images):
            # Checa cancelamento
            conn = get_conn()
            status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
            conn.close()
            if status == "cancelled":
                _append_log(job_id, "Job cancelado pelo usuário.")
                break

            # Verifica créditos a cada imagem
            if _get_user_credits(user_id) < 1:
                _append_log(job_id, "Créditos esgotados — job pausado.")
                _update_job(job_id, status="paused")
                return

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
                        credits_used += 1
                        _deduct_credits(user_id, 1)
                    else:
                        failed += 1
                        _append_log(job_id, f"Falha upload: {fname}")
                else:
                    processed += 1
                    credits_used += 1
                    _deduct_credits(user_id, 1)

            except Exception as e:
                failed += 1
                _append_log(job_id, f"Erro: {fname} — {e}")

            _update_job(job_id, processed=processed, failed=failed, credits_used=credits_used)
            time.sleep(0.3)

        _update_job(job_id, status="completed")
        _append_log(job_id, f"Concluído. {processed} enviadas, {failed} falhas.")

    except Exception as e:
        logger.error(f"Job {job_id} falhou: {e}")
        _update_job(job_id, status="failed")
        _append_log(job_id, f"Erro crítico: {e}")
