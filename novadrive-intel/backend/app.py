"""NovaDrive Supply Intelligence — API + static frontend.

Run:  python run.py        (or: uvicorn app:app --app-dir backend)
The workbook at data/NovaDrive.xlsx (or $NOVADRIVE_XLSX) is watched; every save rebuilds
the network, scores, alerts and story, and the browser picks the change up within ~2 s.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import engine
from search.alternates import find_alternates
from search.providers import SearchService

ROOT = Path(__file__).resolve().parent.parent
SERVERLESS = bool(os.environ.get("VERCEL"))
TMP = Path("/tmp") if SERVERLESS else ROOT / "data"
# Optional cloud workbook (Google Sheets export link, OneDrive/SharePoint direct-download link).
# When set, the app re-fetches it at most every WORKBOOK_TTL seconds: edit the sheet online and the dashboard follows.
WORKBOOK_URL = os.environ.get("WORKBOOK_URL")
WORKBOOK_TTL = int(os.environ.get("WORKBOOK_TTL", "30"))
BUNDLED = Path(os.environ.get("NOVADRIVE_XLSX", ROOT / "data" / "NovaDrive.xlsx"))
XLSX = TMP / "NovaDrive.remote.xlsx" if WORKBOOK_URL else (TMP / "NovaDrive.xlsx" if SERVERLESS else BUNDLED)
_remote = {"at": 0.0, "etag": None}


def sync_remote():
    """Download the cloud workbook when it changed (ETag / content), at most once per TTL."""
    if not WORKBOOK_URL or time.time() - _remote["at"] < WORKBOOK_TTL:
        return
    _remote["at"] = time.time()
    try:
        import httpx
        r = httpx.get(WORKBOOK_URL, follow_redirects=True, timeout=15)
        r.raise_for_status()
        if r.content[:2] != b"PK":
            raise ValueError("link did not return an .xlsx file (check sharing / export link)")
        old = XLSX.read_bytes() if XLSX.exists() else None
        if r.content != old:
            XLSX.write_bytes(r.content)
        S["remote_error"] = None
    except Exception as e:
        S["remote_error"] = f"Cloud workbook not reachable: {e}"
        if not XLSX.exists():
            shutil.copy2(BUNDLED, XLSX)  # fall back to the bundled copy so the app still works
STATIC = Path(__file__).resolve().parent / "static"
SNAPSHOT = Path(__file__).resolve().parent / "search" / "snapshot.json"
svc = SearchService(TMP / "search_cache.json")

app = FastAPI(title="NovaDrive Supply Intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

S = {"remote_error": None, "mtime": 0.0, "state": None, "prev": None, "error": None, "built": None, "ctx": None, "changes": []}
LOCK = threading.Lock()


def diff(old, new):
    if not old:
        return []
    out = []
    on = {n["id"]: n for n in old["nodes"]}
    nn = {n["id"]: n for n in new["nodes"]}
    for k, n in nn.items():
        o = on.get(k)
        if not o:
            out.append({"kind": "node_added", "id": k, "text": f"{n['short']} entered the network (Tier {n['tier']})"})
            continue
        if abs(o["risk"] - n["risk"]) >= 1:
            out.append({"kind": "risk", "id": k, "from": o["risk"], "to": n["risk"], "text": f"{n['short']} risk {o['risk']} → {n['risk']}"})
        if o.get("reading") != n.get("reading"):
            out.append({"kind": "reading", "id": k, "text": f"{n['short']}: {o.get('reading')} → {n.get('reading')}"})
        if o.get("grade") != n.get("grade"):
            out.append({"kind": "grade", "id": k, "text": f"{n['short']} evidence grade {o.get('grade')} → {n.get('grade')}"})
    for k in on.keys() - nn.keys():
        out.append({"kind": "node_removed", "id": k, "text": f"{on[k]['short']} no longer has a supported link"})
    oe = {e["id"]: e for e in old["edges"]}
    ne = {e["id"]: e for e in new["edges"]}
    for k in ne.keys() - oe.keys():
        out.append({"kind": "edge_added", "id": k, "text": f"New {ne[k]['status']} link {k}"})
    for k in oe.keys() - ne.keys():
        out.append({"kind": "edge_removed", "id": k, "text": f"Link {k} removed"})
    oa = {e["id"]: e for e in old["events"]}
    for e in new["events"]:
        o = oa.get(e["id"])
        if not o:
            out.append({"kind": "event_added", "id": e["id"], "text": f"New signal {e['id']}: {e.get('verdict') or e['decision'].title()}"})
        elif o.get("verdict") != e.get("verdict") or o.get("priority") != e.get("priority"):
            out.append({"kind": "event", "id": e["id"], "text": f"{e['id']}: {o.get('verdict')} → {e.get('verdict')}"})
    if old["total"] != new["total"]:
        out.append({"kind": "revenue", "text": f"Revenue in scope ${old['total']:,.0f}m → ${new['total']:,.0f}m"})
    return out


def refresh(force=False):
    if SERVERLESS and not WORKBOOK_URL and not XLSX.exists():
        shutil.copy2(BUNDLED, XLSX)
    sync_remote()
    with LOCK:
        try:
            m = XLSX.stat().st_mtime
        except FileNotFoundError:
            S["error"] = f"Workbook not found: {XLSX}"
            return
        if not force and m == S["mtime"] and S["state"] is not None:
            return
        try:
            new = engine.build(XLSX)
            S["changes"] = diff(S["state"], new)
            S["prev"], S["state"] = S["state"], new
            S["ctx"] = engine.context_for(XLSX)
            S["mtime"], S["error"], S["built"] = m, None, time.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:  # keep serving the last good build while Excel is mid-save or a sheet is broken
            S["mtime"] = m
            S["error"] = f"{type(e).__name__}: {e}"


def watcher():
    while True:
        refresh()
        time.sleep(1.0)


@app.on_event("startup")
def _start():
    refresh(force=True)
    if not SERVERLESS:  # serverless functions have no long-lived threads; requests trigger refresh() instead
        threading.Thread(target=watcher, daemon=True).start()


def state():
    if S["state"] is None:
        refresh(force=True)
    if S["state"] is None:
        raise HTTPException(503, S["error"] or "Workbook not loaded")
    return S["state"]


@app.get("/api/version")
def version():
    if SERVERLESS or WORKBOOK_URL:
        refresh()
    return {"version": S["mtime"], "built": S["built"], "error": S["error"], "changes": S["changes"]}


@app.get("/api/state")
def get_state():
    st = state()
    return JSONResponse({**st, "version": S["mtime"], "built": S["built"], "error": S["error"], "changes": S["changes"],
                         "source": {"path": WORKBOOK_URL or str(XLSX), "name": "Cloud workbook" if WORKBOOK_URL else BUNDLED.name, "remote_error": S.get("remote_error"), "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(S["mtime"]))}})


class Signal(BaseModel):
    title: str
    detail: str = ""
    published: str | None = None
    effective: str | None = None


@app.post("/api/signal")
def test_signal(sig: Signal):
    state()
    return engine.test_signal(S["ctx"], sig.title, sig.detail, sig.published, sig.effective)


@app.get("/api/alternates")
def alternates(node: str, live: bool = True):
    st = state()
    n = next((x for x in st["nodes"] if x["id"] == node), None)
    if not n:
        raise HTTPException(404, "Unknown node")
    return find_alternates(n, st, svc, SNAPSHOT, live, str(date.today()))


@app.get("/api/search/status")
def search_status():
    return {"providers": svc.status()}


@app.get("/api/search")
def search(q: str):
    return svc.search(q, 10)


@app.post("/api/workbook")
async def upload(file: UploadFile):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Upload an .xlsx workbook")
    tmp = XLSX.with_suffix(".upload.xlsx")
    tmp.write_bytes(await file.read())
    try:
        engine.build(tmp)  # validate before replacing
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, f"Workbook could not be read: {e}")
    if XLSX.exists():
        shutil.copy2(XLSX, XLSX.with_suffix(".backup.xlsx"))
    tmp.replace(XLSX)
    refresh(force=True)
    return {"ok": True, "changes": S["changes"]}


@app.get("/api/workbook")
def download():
    return FileResponse(XLSX, filename=XLSX.name)


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
