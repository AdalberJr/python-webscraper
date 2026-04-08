#!/usr/bin/env python3
"""Web-UI Server für den Python Web Scraper."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scraper.config import ScraperConfig
from scraper.core import scrape
from scraper.exporters import to_dataframe
from scraper.storage import Database

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Web Scraper UI", version="2.0")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

DB_PATH = BASE_DIR / "output" / "scraper.db"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# DB beim Start initialisieren
_init_db = Database(DB_PATH)
_init_db.close()

# Globaler State für laufende Jobs
active_job = {
    "running": False,
    "progress": 0,
    "status": "",
    "items_count": 0,
    "items": [],
    "error": None,
}


def get_db() -> Database:
    return Database(DB_PATH)


# ─── Pages ──────────────────────────────────────────

@app.get("/debug")
async def debug():
    """Debug-Info für Deployment-Probleme."""
    template_dir = BASE_DIR / "templates"
    return {
        "base_dir": str(BASE_DIR),
        "template_dir": str(template_dir),
        "template_exists": template_dir.exists(),
        "template_files": [f.name for f in template_dir.iterdir()] if template_dir.exists() else [],
        "cwd": str(Path.cwd()),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        return HTMLResponse(f"<pre>Error: {e}\nBASE_DIR: {BASE_DIR}\nTemplates: {BASE_DIR / 'templates'}\nExists: {(BASE_DIR / 'templates').exists()}</pre>", status_code=500)


# ─── API: Scraping ──────────────────────────────────

@app.post("/api/scrape")
async def start_scrape(
    url: str = Query(default="https://books.toscrape.com"),
    pages: int = Query(default=0),
    formats: str = Query(default="excel"),
):
    """Startet einen Scrape-Job im Hintergrund."""
    if active_job["running"]:
        return JSONResponse({"error": "Ein Job läuft bereits"}, status_code=409)

    active_job["running"] = True
    active_job["progress"] = 0
    active_job["status"] = "Wird gestartet..."
    active_job["items_count"] = 0
    active_job["items"] = []
    active_job["error"] = None

    def run_job():
        try:
            config = ScraperConfig(
                base_url=url.rstrip("/"),
                max_pages=pages if pages > 0 else 0,
                output_dir=OUTPUT_DIR,
                db_path=DB_PATH,
            )

            active_job["status"] = "Scraping läuft..."
            items = scrape(config)

            active_job["items"] = items
            active_job["items_count"] = len(items)
            active_job["status"] = "Speichere Ergebnisse..."

            # In DB speichern
            db = get_db()
            run_id = db.start_run(url)
            if items:
                db.save_items(run_id, items)
                db.finish_run(run_id, pages=pages, items=len(items))
            else:
                db.finish_run(run_id, pages=0, items=0, status="empty")
            db.close()

            # Exportieren
            fmt_list = [f.strip() for f in formats.split(",")]
            from scraper.exporters import export_all
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_all(items, OUTPUT_DIR, filename=f"scrape_{timestamp}", formats=fmt_list)

            active_job["status"] = f"Fertig — {len(items)} Items gescrapt"
            active_job["progress"] = 100

        except Exception as e:
            active_job["error"] = str(e)
            active_job["status"] = f"Fehler: {e}"
        finally:
            active_job["running"] = False

    thread = threading.Thread(target=run_job, daemon=True)
    thread.start()

    return {"message": "Job gestartet", "status": "running"}


@app.get("/api/status")
async def get_status():
    """Aktueller Job-Status."""
    return {
        "running": active_job["running"],
        "progress": active_job["progress"],
        "status": active_job["status"],
        "items_count": active_job["items_count"],
        "error": active_job["error"],
    }


@app.get("/api/results")
async def get_results(
    run_id: Optional[int] = None,
    sort: str = "title",
    order: str = "asc",
    search: str = "",
    min_rating: int = 0,
    max_price: float = 0,
):
    """Gibt Scrape-Ergebnisse zurück."""
    items = []
    try:
        if run_id:
            db = get_db()
            items = db.get_items_by_run(run_id)
            db.close()
        elif active_job["items"]:
            items = active_job["items"]
        else:
            db = get_db()
            runs = db.get_run_history(1)
            if runs:
                items = db.get_items_by_run(runs[0]["id"])
            db.close()
    except Exception:
        items = active_job.get("items", [])

    # Filter
    if search:
        search_lower = search.lower()
        items = [i for i in items if search_lower in (i.get("title", "") or "").lower()]

    if min_rating > 0:
        items = [i for i in items if (i.get("rating") or 0) >= min_rating]

    if max_price > 0:
        def parse_price(p):
            try:
                return float(str(p).replace("£", "").replace("€", "").replace(",", ".").strip())
            except (ValueError, TypeError):
                return 999
        items = [i for i in items if parse_price(i.get("price")) <= max_price]

    # Sort
    reverse = order == "desc"
    if sort == "price":
        def price_key(i):
            try:
                return float(str(i.get("price", "0")).replace("£", "").replace("€", "").replace(",", ".").strip())
            except (ValueError, TypeError):
                return 0
        items.sort(key=price_key, reverse=reverse)
    elif sort == "rating":
        items.sort(key=lambda i: i.get("rating") or 0, reverse=reverse)
    else:
        items.sort(key=lambda i: (i.get("title") or "").lower(), reverse=reverse)

    return {"items": items, "total": len(items)}


# ─── API: History ───────────────────────────────────

@app.get("/api/history")
async def get_history(limit: int = 20):
    try:
        db = get_db()
        runs = db.get_run_history(limit)
        db.close()
        return {"runs": runs}
    except Exception:
        return {"runs": []}


@app.delete("/api/history/{run_id}")
async def delete_run(run_id: int):
    db = get_db()
    db.conn.execute("DELETE FROM items WHERE run_id = ?", (run_id,))
    db.conn.execute("DELETE FROM scrape_runs WHERE id = ?", (run_id,))
    db.conn.commit()
    db.close()
    return {"message": f"Run #{run_id} gelöscht"}


# ─── API: Downloads ─────────────────────────────────

@app.get("/api/download/{format}")
async def download(format: str, run_id: Optional[int] = None):
    """Download als Excel, CSV oder JSON."""
    # Items holen
    if run_id:
        db = get_db()
        items = db.get_items_by_run(run_id)
        db.close()
    elif active_job["items"]:
        items = active_job["items"]
    else:
        db = get_db()
        runs = db.get_run_history(1)
        items = db.get_items_by_run(runs[0]["id"]) if runs else []
        db.close()

    if not items:
        return JSONResponse({"error": "Keine Daten"}, status_code=404)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format == "excel":
        df = to_dataframe(items)
        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=scrape_{timestamp}.xlsx"},
        )
    elif format == "csv":
        df = to_dataframe(items)
        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding="utf-8-sig")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=scrape_{timestamp}.csv"},
        )
    elif format == "json":
        content = json.dumps(items, indent=2, ensure_ascii=False)
        return StreamingResponse(
            BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=scrape_{timestamp}.json"},
        )
    else:
        return JSONResponse({"error": "Unbekanntes Format"}, status_code=400)


# ─── API: Stats ─────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    try:
        db = get_db()
        runs = db.get_run_history(100)
        total_items = sum(r["items_found"] for r in runs)
        completed = sum(1 for r in runs if r["status"] == "completed")
        db.close()
        return {
            "total_runs": len(runs),
            "total_items": total_items,
            "completed_runs": completed,
            "last_run": runs[0] if runs else None,
        }
    except Exception:
        return {
            "total_runs": 0,
            "total_items": 0,
            "completed_runs": 0,
            "last_run": None,
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
