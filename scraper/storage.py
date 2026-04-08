"""SQLite-Storage für persistente Daten und Scraping-History."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .logger import log


class Database:
    """SQLite-Datenbank für Scraping-Ergebnisse und History."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                pages_scraped INTEGER DEFAULT 0,
                items_found INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                title TEXT,
                price TEXT,
                rating INTEGER,
                availability TEXT,
                url TEXT,
                scraped_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES scrape_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_items_run ON items(run_id);
            CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);
        """)
        self.conn.commit()

    def start_run(self, url: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO scrape_runs (url, started_at) VALUES (?, ?)",
            (url, datetime.now().isoformat()),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_run(self, run_id: int, pages: int, items: int, status: str = "completed"):
        self.conn.execute(
            "UPDATE scrape_runs SET finished_at=?, pages_scraped=?, items_found=?, status=? WHERE id=?",
            (datetime.now().isoformat(), pages, items, status, run_id),
        )
        self.conn.commit()

    def save_items(self, run_id: int, items: list[dict]):
        now = datetime.now().isoformat()
        self.conn.executemany(
            "INSERT INTO items (run_id, title, price, rating, availability, url, scraped_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (run_id, i.get("title"), i.get("price"), i.get("rating"),
                 i.get("availability"), i.get("url"), now)
                for i in items
            ],
        )
        self.conn.commit()
        log.info(f"[green]{len(items)} Items[/green] in DB gespeichert (Run #{run_id})")

    def get_run_history(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scrape_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_items_by_run(self, run_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM items WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
