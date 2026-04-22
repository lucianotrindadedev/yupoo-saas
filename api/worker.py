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

def _extract_photo_ids_and_images(html, base_url):
    """Extract photo IDs and image URLs from Yupoo album page."""
    soup = BeautifulSoup(html, "html.parser")
    images = []
    photo_ids = []
    seen = set()

    # 1) Try to find image data in embedded JSON/JavaScript
    for script in soup.find_all("script"):
        text = script.string or ""
        # Look for photo.yupoo.com URLs in scripts
        for m in re.findall(r'https?://photo\.yupoo\.com/[^"\s\'\\]+\.(?:jpg|jpeg|png|webp)', text):
            clean = re.sub(r'\?.*$', '', m)
            if clean not in seen:
                seen.add(clean)
                images.append(clean)

    # 2) Extract photo IDs from album children elements
    for el in soup.find_all(attrs={"data-id": True}):
        pid = el.get("data-id")
        if pid and pid not in photo_ids:
            photo_ids.append(pid)

    # 3) Also look for photo links in href patterns like /12345678
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.match(r'.*/(\d{6,})(?:\?.*)?$', href)
        if m and "albums" not in href and "categories" not in href:
            pid = m.group(1)
            if pid not in photo_ids:
                photo_ids.append(pid)

    # 4) Find showalbum__children image containers
    for div in soup.find_all(class_=re.compile(r'showalbum__children')):
        # Check for background-image style
        style = div.get("style", "")
        bg_match = re.search(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', style)
        if bg_match:
            url = bg_match.group(1)
            # Convert thumbnail to full-size
            clean = re.sub(r'_\d+x\d+\.', '.', url)
            clean = re.sub(r'\?.*$', '', clean)
            if clean not in seen:
                seen.add(clean)
                images.append(clean)
        # Check for img inside the container
        img = div.find("img")
        if img:
            for attr in ("src", "data-src", "data-original", "data-lazy-src"):
                val = img.get(attr, "")
                if val and "photo.yupoo.com" in val:
                    clean = re.sub(r'_\d+x\d+\.', '.', val)
                    clean = re.sub(r'\?.*$', '', clean)
                    if clean not in seen:
                        seen.add(clean)
                        images.append(clean)

    # 5) Fallback: any img with photo.yupoo.com in src
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            val = img.get(attr, "")
            if val and "photo.yupoo.com" in val:
                clean = re.sub(r'_\d+x\d+\.', '.', val)
                clean = re.sub(r'\?.*$', '', clean)
                if clean not in seen:
                    seen.add(clean)
                    images.append(clean)

    # Get album title
    title_el = soup.find("h1") or soup.find("title")
    album_name = title_el.get_text(strip=True) if title_el else "album"
    album_name = re.sub(r'[\\/*?:"<>|]', "_", album_name)[:60].strip()
    # Remove common Yupoo suffixes
    album_name = re.sub(r'\s*\|\s*相册.*$', '', album_name).strip()

    return images, photo_ids, album_name


def _get_image_from_photo_page(session, photo_url):
    """Visit individual photo page and extract full-resolution image URL."""
    try:
        r = session.get(photo_url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Look for original image link
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "photo.yupoo.com" in href and any(
                ext in href.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
            ):
                return re.sub(r'\?.*$', '', href)

        # Look in img tags
        for img in soup.find_all("img"):
            for attr in ("src", "data-src", "data-original"):
                val = img.get(attr, "")
                if val and "photo.yupoo.com" in val and any(
                    ext in val.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
                ):
                    clean = re.sub(r'_\d+x\d+\.', '.', val)
                    return re.sub(r'\?.*$', '', clean)

        # Look in scripts
        for script in soup.find_all("script"):
            text = script.string or ""
            matches = re.findall(r'https?://photo\.yupoo\.com/[^"\s\'\\]+\.(?:jpg|jpeg|png|webp)', text)
            if matches:
                return re.sub(r'\?.*$', '', matches[0])

    except Exception as e:
        logger.warning(f"Failed to fetch photo page {photo_url}: {e}")
    return None


def scrape_album(start_url):
    session = requests.Session()
    session.headers.update(HEADERS)
    all_images = []
    album_name = "album"
    seen = set()

    # Parse the base store URL from the album URL
    parsed = urlparse(start_url)
    base_store = f"{parsed.scheme}://{parsed.netloc}"

    try:
        r = session.get(start_url, timeout=20)
        r.raise_for_status()
        images, photo_ids, album_name = _extract_photo_ids_and_images(r.text, start_url)

        # Add directly found images
        for img in images:
            if img not in seen:
                seen.add(img)
                all_images.append(img)

        logger.info(f"Direct images found: {len(images)}, Photo IDs found: {len(photo_ids)}")

        # For each photo ID, visit the detail page to get full-res URL
        for pid in photo_ids:
            photo_url = f"{base_store}/{pid}?uid=1"
            img_url = _get_image_from_photo_page(session, photo_url)
            if img_url and img_url not in seen:
                seen.add(img_url)
                all_images.append(img_url)
            
            # Filter to get high-res image only
            # The high-res images usually have a long hex ID like '01e91c86.jpg'
            # We explicitly ignore generic names that Yupoo uses for thumbnails/previews
            soup = BeautifulSoup(r.text, "html.parser")
            for img in soup.find_all("img", src=True):
                src = img["src"]
                if "photo.yupoo.com" in src:
                    # Skip generic/duplicate sizes
                    fname = src.split("/")[-1].lower()
                    if fname in ["big.jpg", "medium.jpg", "small.jpg", "square.jpg", "logo.png"]:
                        continue
                    
                    # Ensure it's not a thumbnail (usually has /small/ or /medium/ in path)
                    if "/small/" in src or "/medium/" in src or "/square/" in src:
                        continue

                    img_url = urljoin("https:", src) if src.startswith("//") else src
                    if img_url and img_url not in seen:
                        seen.add(img_url)
                        all_images.append(img_url)
            time.sleep(0.4)

    except Exception as e:
        logger.error(f"Error scraping album {start_url}: {e}")

    logger.info(f"Total images found: {len(all_images)} for album: {album_name}")
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
                        # Try to get album title from the link text or nearby element
                        title = a.get_text(strip=True) or f"Album {album_id}"
                        title = re.sub(r'[\\/*?:"<>|]', "_", title)[:60].strip()
                        albums.append({"url": full_url, "title": title, "id": album_id})
                        found += 1

            if found == 0:
                break  # No more albums on this page

            page += 1
            time.sleep(0.8)

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

    logger.info(f"Store '{store_name}': found {len(albums)} albums")
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

def _process_images(job_id, user_id, images, destination, drive_token, folder_id, yupoo_url=None):
    """Shared logic: download and upload images for a job."""
    session = requests.Session()
    # IMPORTANT: Yupoo requires Referer to allow image downloads
    referer = yupoo_url or "https://x.yupoo.com/"
    session.headers.update({**HEADERS, "Referer": referer})
    
    processed = failed = credits_used = 0
    # Track images since last credit deduction
    images_in_current_batch = 0

    # Get current progress (for store jobs that process multiple albums)
    conn = get_conn()
    row = conn.execute("SELECT processed, failed, credits_used FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row:
        processed = row["processed"]
        failed = row["failed"]
        credits_used = row["credits_used"]
        # Resume batch counter based on total processed
        images_in_current_batch = processed % 10

    for i, img_url in enumerate(images):
        # Check cancellation
        conn = get_conn()
        status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
        conn.close()
        if status == "cancelled":
            _append_log(job_id, "Job cancelled by user.")
            return processed, failed, credits_used, True

        # Check credits: only if we are about to start a NEW batch of 10
        if images_in_current_batch == 0:
            if _get_user_credits(user_id) < 1:
                _append_log(job_id, "Credits exhausted — job paused.")
                _update_job(job_id, status="paused")
                return processed, failed, credits_used, True

        fname = urlparse(img_url).path.split("/")[-1] or f"img_{i:04d}.jpg"
        fname = re.sub(r'[\\/*?:"<>|]', "_", fname)

        try:
            # Re-verify referer just in case
            r = session.get(img_url, timeout=30)
            r.raise_for_status()
            data = r.content
            mime = "image/png" if fname.endswith(".png") else "image/jpeg"

            if destination == "drive" and folder_id:
                ok = _drive_upload(drive_token, data, fname, folder_id, mime)
                if ok:
                    processed += 1
                    images_in_current_batch += 1
                    # Deduct 1 credit for every 10 images
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
        time.sleep(0.3)

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

        # Create Drive folder
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

        # Create root Drive folder
        root_folder = None
        if destination == "drive" and drive_token:
            root = _drive_create_folder(drive_token, "Yupoo Downloads")
            root_folder = _drive_create_folder(drive_token, store_name, root)
            _update_job(job_id, drive_folder_id=root_folder)
            _append_log(job_id, f"Root folder created: {store_name}")

        total_images_all = 0
        albums_done = 0

        for album in albums:
            # Check cancellation
            conn = get_conn()
            status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()["status"]
            conn.close()
            if status == "cancelled":
                _append_log(job_id, "Job cancelled by user.")
                break

            # Check credits
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

                # Create album subfolder
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

            time.sleep(1)  # Pause between albums

        _update_job(job_id, status="completed")
        _append_log(job_id, f"Store completed. {albums_done}/{len(albums)} albums processed.")

    except Exception as e:
        logger.error(f"Store job {job_id} failed: {e}")
        _update_job(job_id, status="failed")
        _append_log(job_id, f"Critical error: {e}")
