from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from database import get_conn
from routers.auth import get_current_user
from worker import run_job, run_store_job
import uuid, time, re

router = APIRouter()

class JobCreate(BaseModel):
    yupoo_url: str
    destination: str = "drive"
    drive_token: str = ""

def _is_store_url(url: str) -> bool:
    """Detect if URL is a store root (e.g. store.x.yupoo.com/albums) vs album (e.g. store.x.yupoo.com/albums/12345)"""
    # Album URLs have /albums/{numeric_id}
    if re.search(r'/albums/\d+', url):
        return False
    # Store URLs are like: store.x.yupoo.com or store.x.yupoo.com/albums
    return True

@router.post("/")
def create_job(body: JobCreate, request: Request, background_tasks: BackgroundTasks):
    user = get_current_user(request)

    if user["credits"] < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits. Buy more credits.")

    is_store = _is_store_url(body.yupoo_url)
    job_type = "store" if is_store else "album"

    job_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        """INSERT INTO jobs (id, user_id, yupoo_url, status, destination, job_type)
           VALUES (?, ?, ?, 'pending', ?, ?)""",
        (job_id, user["id"], body.yupoo_url, body.destination, job_type)
    )
    conn.commit()
    conn.close()

    if is_store:
        background_tasks.add_task(run_store_job, job_id, user["id"], body.yupoo_url, body.destination, body.drive_token)
    else:
        background_tasks.add_task(run_job, job_id, user["id"], body.yupoo_url, body.destination, body.drive_token)

    return {"job_id": job_id, "status": "pending", "type": job_type}

@router.get("/")
def list_jobs(request: Request):
    user = get_current_user(request)
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, yupoo_url, status, destination, total_images, processed, failed,
                  credits_used, created_at, updated_at, job_type, log
           FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT 50""",
        (user["id"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/{job_id}")
def get_job(job_id: str, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)

@router.delete("/{job_id}")
def cancel_job(job_id: str, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status IN ('pending', 'running')",
        (job_id, user["id"])
    )
    conn.commit()
    conn.close()
    return {"cancelled": True}
