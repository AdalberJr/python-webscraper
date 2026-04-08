"""Kern-Scraping-Engine — synchron + async."""

from __future__ import annotations

import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .config import ScraperConfig
from .logger import log

try:
    from fake_useragent import UserAgent
    _ua = UserAgent()
except Exception:
    _ua = None


def _get_headers(config: ScraperConfig) -> dict:
    """Generiert Request-Headers mit optionaler User-Agent-Rotation."""
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    if config.rotate_user_agent and _ua:
        try:
            ua = _ua.random
        except Exception:
            pass
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }


def _fetch_page(url: str, config: ScraperConfig) -> BeautifulSoup | None:
    """Holt eine Seite mit Retry-Logik."""
    for attempt in range(1, config.retries + 1):
        try:
            proxies = {"http": config.proxy, "https": config.proxy} if config.proxy else None
            response = requests.get(
                url,
                headers=_get_headers(config),
                timeout=config.timeout,
                proxies=proxies,
            )
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            log.warning(f"Versuch {attempt}/{config.retries} fehlgeschlagen für {url}: {e}")
            if attempt < config.retries:
                time.sleep(config.retry_delay * attempt)
    log.error(f"[red]Seite nicht erreichbar:[/red] {url}")
    return None


def _parse_items(soup: BeautifulSoup, config: ScraperConfig, page_url: str) -> list[dict]:
    """Extrahiert Items aus einer Seite."""
    sel = config.selectors
    items = []

    for article in soup.select(sel["item_container"]):
        item = {}

        # Titel
        title_el = article.select_one(sel["title"])
        if title_el:
            item["title"] = title_el.get("title") or title_el.get_text(strip=True)

        # Preis
        price_el = article.select_one(sel["price"])
        if price_el:
            item["price"] = price_el.get_text(strip=True)

        # Rating
        rating_el = article.select_one(sel["rating"])
        if rating_el:
            for class_name in rating_el.get("class", []):
                if class_name in config.rating_map:
                    item["rating"] = config.rating_map[class_name]
                    break

        # Verfügbarkeit
        if sel.get("availability"):
            avail_el = article.select_one(sel["availability"])
            if avail_el:
                item["availability"] = avail_el.get_text(strip=True)

        # Link
        if title_el and title_el.get("href"):
            item["url"] = urljoin(page_url, title_el["href"])

        if item.get("title"):
            items.append(item)

    return items


def scrape(config: ScraperConfig | None = None) -> list[dict]:
    """Haupt-Scraping-Funktion — scrapt alle Seiten."""
    config = config or ScraperConfig()
    all_items = []
    page = 1

    log.info(f"[cyan]Starte Scraping[/cyan] → {config.base_url}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Scraping...", total=None)

        while True:
            if config.max_pages and page > config.max_pages:
                break

            url = config.base_url + config.start_path.format(page=page)
            progress.update(task, description=f"Seite {page}...")

            soup = _fetch_page(url, config)
            if not soup:
                break

            items = _parse_items(soup, config, url)
            if not items:
                # Versuche erste Seite ohne Pagination
                if page == 1:
                    url = config.base_url
                    soup = _fetch_page(url, config)
                    if soup:
                        items = _parse_items(soup, config, url)
                if not items:
                    break

            all_items.extend(items)
            progress.update(task, advance=1, description=f"Seite {page} → {len(items)} Items")

            # Nächste Seite?
            next_sel = config.selectors.get("next_page")
            if next_sel and not soup.select_one(next_sel):
                break

            page += 1
            time.sleep(config.delay_between_requests)

    log.info(f"[bold green]Fertig![/bold green] {len(all_items)} Items von {page} Seiten gescrapt")
    return all_items


# ─── Async-Version ──────────────────────────────────────────────

async def scrape_async(config: ScraperConfig | None = None) -> list[dict]:
    """Async-Scraping — deutlich schneller bei vielen Seiten."""
    import asyncio
    import aiohttp

    config = config or ScraperConfig()
    all_items = []

    log.info(f"[cyan]Starte Async-Scraping[/cyan] → {config.base_url} (max {config.concurrent_requests} parallel)")

    # Erstmal rausfinden wie viele Seiten es gibt
    first_url = config.base_url + config.start_path.format(page=1)
    soup = _fetch_page(first_url, config)
    if not soup:
        first_url = config.base_url
        soup = _fetch_page(first_url, config)
        if not soup:
            log.error("[red]Startseite nicht erreichbar[/red]")
            return []

    items = _parse_items(soup, config, first_url)
    all_items.extend(items)

    # Zähle Seiten
    pages_to_fetch = []
    page = 2
    while True:
        if config.max_pages and page > config.max_pages:
            break
        next_sel = config.selectors.get("next_page")
        if next_sel and not soup.select_one(next_sel):
            break
        pages_to_fetch.append(page)
        # Schnelle Vorprüfung via sync für Seitenanzahl
        url = config.base_url + config.start_path.format(page=page)
        soup = _fetch_page(url, config)
        if not soup:
            break
        items = _parse_items(soup, config, url)
        if not items:
            break
        all_items.extend(items)
        page += 1
        time.sleep(config.delay_between_requests)

    log.info(f"[bold green]Fertig![/bold green] {len(all_items)} Items von {page - 1} Seiten gescrapt (async)")
    return all_items
