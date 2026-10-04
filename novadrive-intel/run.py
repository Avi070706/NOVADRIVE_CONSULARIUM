"""Start NovaDrive Supply Intelligence:  python run.py  → http://localhost:8000"""
import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).parent / "backend"))
if __name__ == "__main__":
    uvicorn.run("app:app", app_dir="backend", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8000)))
