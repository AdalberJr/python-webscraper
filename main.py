#!/usr/bin/env python3
"""
Python Web Scraper — CLI-Interface

Verwendung:
    python main.py                           # Standard-Scraping (books.toscrape.com)
    python main.py --url https://example.com # Eigene URL
    python main.py --format excel csv json   # Mehrere Formate
    python main.py --pages 5                 # Nur 5 Seiten
    python main.py --async                   # Async-Modus
    python main.py --schedule 60             # Alle 60 Minuten
    python main.py --proxy http://proxy:8080 # Mit Proxy
    python main.py history                   # Letzte Scraping-Runs
"""

import asyncio
from pathlib import Path

import click
from rich.table import Table

from scraper.config import ScraperConfig
from scraper.core import scrape, scrape_async
from scraper.exporters import export_all
from scraper.storage import Database
from scraper.logger import log, console


@click.group(invoke_without_command=True)
@click.option("--url", "-u", default="https://books.toscrape.com", help="Basis-URL zum Scrapen")
@click.option("--pages", "-p", default=0, help="Max. Seitenanzahl (0 = alle)")
@click.option("--format", "-f", "formats", multiple=True, default=["excel"], help="Export-Formate: excel, csv, json")
@click.option("--output", "-o", default="output", help="Output-Verzeichnis")
@click.option("--async", "use_async", is_flag=True, help="Async-Modus (schneller)")
@click.option("--proxy", default=None, help="Proxy-URL (http://host:port)")
@click.option("--schedule", "interval", default=0, help="Intervall in Minuten (0 = einmalig)")
@click.option("--no-db", is_flag=True, help="Keine Datenbank-Speicherung")
@click.option("--delay", default=0.3, help="Verzögerung zwischen Requests (Sekunden)")
@click.option("--filename", default="ergebnisse", help="Dateiname für Export")
@click.pass_context
def cli(ctx, url, pages, formats, output, use_async, proxy, interval, no_db, delay, filename):
    """Python Web Scraper — Daten aus Websites extrahieren und exportieren."""
    ctx.ensure_object(dict)

    if ctx.invoked_subcommand:
        return

    # Config aufbauen
    config = ScraperConfig(
        base_url=url.rstrip("/"),
        max_pages=pages,
        use_async=use_async,
        proxy=proxy,
        output_dir=Path(output),
        db_path=Path(output) / "scraper.db",
        delay_between_requests=delay,
    )

    # Scheduler-Modus
    if interval > 0:
        from scraper.scheduler import start_scheduler
        start_scheduler(config, interval_minutes=interval, formats=list(formats))
        return

    # Banner
    console.print()
    console.print("[bold cyan]╔══════════════════════════════════╗[/]")
    console.print("[bold cyan]║   Python Web Scraper v2.0       ║[/]")
    console.print("[bold cyan]╚══════════════════════════════════╝[/]")
    console.print()

    # Scrapen
    if use_async:
        items = asyncio.run(scrape_async(config))
    else:
        items = scrape(config)

    if not items:
        log.warning("Keine Daten gefunden — prüfe URL und Selektoren")
        return

    # In DB speichern
    if not no_db:
        db = Database(config.db_path)
        run_id = db.start_run(url)
        db.save_items(run_id, items)
        db.finish_run(run_id, pages=pages, items=len(items))
        db.close()

    # Exportieren
    export_all(items, config.output_dir, filename=filename, formats=list(formats))

    # Zusammenfassung
    console.print()
    table = Table(title="Zusammenfassung", show_header=False, border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("URL", url)
    table.add_row("Items", str(len(items)))
    table.add_row("Formate", ", ".join(formats))
    table.add_row("Output", str(config.output_dir.absolute()))
    if not no_db:
        table.add_row("Datenbank", str(config.db_path.absolute()))
    console.print(table)
    console.print()


@cli.command()
@click.option("--limit", "-l", default=10, help="Anzahl der letzten Runs")
@click.option("--db", default="output/scraper.db", help="Pfad zur Datenbank")
def history(limit, db):
    """Zeigt die letzten Scraping-Runs."""
    db_path = Path(db)
    if not db_path.exists():
        log.warning("Keine Datenbank gefunden — zuerst scrapen!")
        return

    database = Database(db_path)
    runs = database.get_run_history(limit)
    database.close()

    if not runs:
        log.info("Noch keine Runs gespeichert")
        return

    table = Table(title="Scraping-History", border_style="cyan")
    table.add_column("#", style="bold cyan")
    table.add_column("URL")
    table.add_column("Start")
    table.add_column("Items", justify="right")
    table.add_column("Status")

    for run in runs:
        status_style = "green" if run["status"] == "completed" else "yellow" if run["status"] == "running" else "red"
        table.add_row(
            str(run["id"]),
            run["url"][:50],
            run["started_at"][:19],
            str(run["items_found"]),
            f"[{status_style}]{run['status']}[/]",
        )

    console.print()
    console.print(table)
    console.print()


@cli.command()
@click.argument("run_id", type=int)
@click.option("--db", default="output/scraper.db", help="Pfad zur Datenbank")
@click.option("--format", "-f", "formats", multiple=True, default=["excel"], help="Export-Formate")
@click.option("--output", "-o", default="output", help="Output-Verzeichnis")
def export(run_id, db, formats, output):
    """Exportiert Items eines bestimmten Runs erneut."""
    db_path = Path(db)
    if not db_path.exists():
        log.warning("Keine Datenbank gefunden")
        return

    database = Database(db_path)
    items = database.get_items_by_run(run_id)
    database.close()

    if not items:
        log.warning(f"Keine Items für Run #{run_id}")
        return

    export_all(items, Path(output), filename=f"run_{run_id}", formats=list(formats))


@cli.command()
def info():
    """Zeigt Infos über verfügbare Optionen und Presets."""
    console.print()
    console.print("[bold cyan]Python Web Scraper v2.0[/]")
    console.print()
    console.print("[bold]Verfügbare Export-Formate:[/]")
    console.print("  excel  → .xlsx (mit formatierten Spalten)")
    console.print("  csv    → .csv  (UTF-8 mit BOM)")
    console.print("  json   → .json (pretty-printed)")
    console.print()
    console.print("[bold]Beispiele:[/]")
    console.print("  python main.py                         # Standard")
    console.print("  python main.py -f excel -f csv -f json # Alle Formate")
    console.print("  python main.py -p 3                    # Nur 3 Seiten")
    console.print("  python main.py --schedule 30           # Alle 30 Min")
    console.print("  python main.py history                 # Letzte Runs")
    console.print("  python main.py export 1 -f csv         # Run neu exportieren")
    console.print()


if __name__ == "__main__":
    cli()
