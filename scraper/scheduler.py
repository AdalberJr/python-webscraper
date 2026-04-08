"""Scheduler — automatisches Scraping in Intervallen."""

from __future__ import annotations

import schedule
import time

from .config import ScraperConfig
from .core import scrape
from .exporters import export_all
from .storage import Database
from .logger import log


def run_scheduled_job(config: ScraperConfig, formats: list[str], use_db: bool = True):
    """Führt einen einzelnen Scraping-Job aus."""
    log.info("[cyan]Scheduled Job startet...[/cyan]")

    db = Database(config.db_path) if use_db else None
    run_id = db.start_run(config.base_url) if db else None

    try:
        items = scrape(config)

        if items:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_all(items, config.output_dir, filename=f"scrape_{timestamp}", formats=formats)

            if db and run_id:
                db.save_items(run_id, items)
                db.finish_run(run_id, pages=0, items=len(items))
        else:
            log.warning("Keine Items gefunden")
            if db and run_id:
                db.finish_run(run_id, pages=0, items=0, status="empty")

    except Exception as e:
        log.error(f"[red]Job fehlgeschlagen:[/red] {e}")
        if db and run_id:
            db.finish_run(run_id, pages=0, items=0, status="error")
    finally:
        if db:
            db.close()


def start_scheduler(config: ScraperConfig, interval_minutes: int = 60, formats: list[str] | None = None):
    """Startet den Scheduler."""
    formats = formats or ["excel"]

    log.info(f"[bold cyan]Scheduler gestartet[/bold cyan] — alle {interval_minutes} Minuten")
    log.info("Drücke Ctrl+C zum Stoppen")

    # Sofort ersten Job ausführen
    run_scheduled_job(config, formats)

    # Dann im Intervall
    schedule.every(interval_minutes).minutes.do(run_scheduled_job, config, formats)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("[yellow]Scheduler gestoppt[/yellow]")
