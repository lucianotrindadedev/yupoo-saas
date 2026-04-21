from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os, time
from routers import auth, credits, jobs
from database import init_db

app = FastAPI(title="Yupoo Downloader API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()

app.include_router(auth.router,    prefix="/auth",    tags=["auth"])
app.include_router(credits.router, prefix="/credits", tags=["credits"])
app.include_router(jobs.router,    prefix="/jobs",    tags=["jobs"])

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}
