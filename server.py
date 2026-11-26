"""Web UI backend for the KB Link Checker.

Run:  KB_HEADLESS=1 .venv/bin/uvicorn server:app --port 8000
Open: http://localhost:8000

The Playwright scan (sync API) runs in a background thread; progress events are
stored per scan and streamed to the browser over Server-Sent Events.
"""

import asyncio
import json
import os
import threading
import time
import uuid

os.environ.setdefault("KB_HEADLESS", "1")  # must be set before config import

from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scanner import (
    run_scan, is_valid_url, get_kb_name, SCOPE_FOLDER, SCOPE_ARTICLE,
)
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
REPORT_ROOT = os.path.join(BASE_DIR, "reports")

# Optional allow-list, e.g. KB_ALLOWED_HOSTS="help.zoho.com,help.zoho.eu".
# Strongly recommended once the app is public (stops it being used to make
# the server browse arbitrary sites).
ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("KB_ALLOWED_HOSTS", "").split(",")
    if h.strip()
}

# Safety limits for a public deployment (override with environment variables).
MAX_ARTICLES = int(os.environ.get("KB_MAX_ARTICLES", "100"))
MAX_SCAN_MINUTES = int(os.environ.get("KB_MAX_SCAN_MINUTES", "30"))
MAX_SCANS_PER_HOUR = int(os.environ.get("KB_MAX_SCANS_PER_HOUR", "10"))

DOWNLOADS = {
    "articles": "articles.csv",
    "validation": "validation_results.csv",
    "result": "result.txt",
}

app = FastAPI(title="KB Link Checker")

scans = {}  # scan_id -> dict(events, cancel, state, report_dir, started)
scans_lock = threading.Lock()


class ScanRequest(BaseModel):
    url: str
    scope: str = SCOPE_FOLDER


recent_starts = {}  # client ip -> [timestamps]


def _client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip):
    now = time.time()
    stamps = [t for t in recent_starts.get(ip, []) if now - t < 3600]
    if len(stamps) >= MAX_SCANS_PER_HOUR:
        recent_starts[ip] = stamps
        return True
    stamps.append(now)
    recent_starts[ip] = stamps
    return False


def _running_scan():
    return next((s for s in scans.values() if s["state"] == "running"), None)


def _worker(scan_id, url, scope):
    scan = scans[scan_id]

    def emit(event):
        scan["events"].append(event)  # list.append is thread-safe

    try:
        summary = run_scan(
            url, scope=scope, emit=emit, cancel=scan["cancel"],
            report_root=REPORT_ROOT,
            report_name=f"{get_kb_name(url)}-{scan_id[:8]}",
            max_articles=MAX_ARTICLES or None,
            max_seconds=MAX_SCAN_MINUTES * 60 or None,
        )
        scan["report_dir"] = summary.get("report_dir")
        scan["state"] = summary["state"]
    except Exception as exc:  # run_scan handles its own errors; belt & braces
        emit({"type": "done", "summary": {"state": "error", "error": str(exc)}})
        scan["state"] = "error"


@app.post("/api/scans")
def start_scan(req: ScanRequest, request: Request):
    url = req.url.strip()
    if not is_valid_url(url):
        raise HTTPException(400, "Enter a full URL starting with http:// or https://")
    if req.scope not in (SCOPE_FOLDER, SCOPE_ARTICLE):
        raise HTTPException(400, "scope must be 'folder' or 'article'")
    if ALLOWED_HOSTS and urlparse(url).netloc.lower() not in ALLOWED_HOSTS:
        raise HTTPException(400, "This host is not allowed.")

    with scans_lock:
        if _running_scan():
            raise HTTPException(409, "A scan is already running. Wait or stop it first.")
        if _rate_limited(_client_ip(request)):
            raise HTTPException(
                429, f"Limit reached: {MAX_SCANS_PER_HOUR} scans per hour. Try again later.")
        scan_id = uuid.uuid4().hex
        scans[scan_id] = {
            "events": [],
            "cancel": threading.Event(),
            "state": "running",
            "report_dir": None,
            "started": time.time(),
            "url": url,
            "scope": req.scope,
        }
        threading.Thread(
            target=_worker, args=(scan_id, url, req.scope), daemon=True
        ).start()
    return {"scan_id": scan_id}


@app.get("/api/scans/{scan_id}/events")
async def stream_events(scan_id: str, last_event_id: Optional[str] = Header(None)):
    scan = scans.get(scan_id)
    if not scan:
        raise HTTPException(404, "Unknown scan")

    start = int(last_event_id) + 1 if (last_event_id or "").isdigit() else 0

    async def gen():
        index = start
        while True:
            events = scan["events"]
            while index < len(events):
                event = events[index]
                yield f"id: {index}\ndata: {json.dumps(event)}\n\n"
                index += 1
                if event.get("type") == "done":
                    return
            await asyncio.sleep(0.3)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/scans/{scan_id}/stop")
def stop_scan(scan_id: str):
    scan = scans.get(scan_id)
    if not scan:
        raise HTTPException(404, "Unknown scan")
    scan["cancel"].set()
    return {"ok": True}


@app.get("/api/scans/{scan_id}")
def scan_status(scan_id: str):
    scan = scans.get(scan_id)
    if not scan:
        raise HTTPException(404, "Unknown scan")
    return {"state": scan["state"], "events": len(scan["events"])}


@app.get("/api/scans/{scan_id}/files/{kind}")
def download(scan_id: str, kind: str):
    scan = scans.get(scan_id)
    if not scan or not scan.get("report_dir"):
        raise HTTPException(404, "Report not available yet")
    filename = DOWNLOADS.get(kind)
    if not filename:
        raise HTTPException(404, "Unknown report")
    path = os.path.join(scan["report_dir"], filename)
    if not os.path.isfile(path):
        raise HTTPException(404, "Report file not found")
    return FileResponse(path, filename=filename)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/limits")
def limits():
    return {"max_articles": MAX_ARTICLES, "max_minutes": MAX_SCAN_MINUTES}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
