"""Konfiguration für den Webscraper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ScraperConfig:
    """Zentrale Konfiguration."""

    base_url: str = "https://books.toscrape.com"
    start_path: str = "/catalogue/page-{page}.html"
    max_pages: int = 0  # 0 = alle Seiten
    timeout: int = 15
    retries: int = 3
    retry_delay: float = 1.5
    delay_between_requests: float = 0.3
    concurrent_requests: int = 5
    use_async: bool = False
    proxy: Optional[str] = None
    rotate_user_agent: bool = True
    output_dir: Path = field(default_factory=lambda: Path("output"))
    db_path: Path = field(default_factory=lambda: Path("output/scraper.db"))

    # CSS-Selektoren — anpassbar für beliebige Websites
    selectors: dict = field(default_factory=lambda: {
        "item_container": "article.product_pod",
        "title": "h3 a",
        "price": ".price_color",
        "rating": "p.star-rating",
        "availability": ".instock.availability",
        "next_page": "li.next a",
    })

    # Rating-Mapping
    rating_map: dict = field(default_factory=lambda: {
        "One": 1,
        "Two": 2,
        "Three": 3,
        "Four": 4,
        "Five": 5,
    })


# Vordefinierte Presets für verschiedene Websites
PRESETS = {
    "books": ScraperConfig(),
    "custom": ScraperConfig(
        base_url="",
        start_path="",
        selectors={
            "item_container": "",
            "title": "",
            "price": "",
        },
    ),
}
