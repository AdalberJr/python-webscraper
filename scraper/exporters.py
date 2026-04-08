"""Export-Module — Excel, CSV, JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .logger import log


def to_dataframe(items: list[dict]) -> pd.DataFrame:
    """Konvertiert Items in einen sauberen DataFrame."""
    df = pd.DataFrame(items)
    if "price" in df.columns:
        df["price_numeric"] = (
            df["price"]
            .str.replace("£", "", regex=False)
            .str.replace("€", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
            .astype(float, errors="ignore")
        )
    return df


def export_excel(items: list[dict], filepath: Path) -> Path:
    """Exportiert nach Excel mit formatiertem Sheet."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df = to_dataframe(items)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Scrape-Ergebnisse")

        worksheet = writer.sheets["Scrape-Ergebnisse"]
        for col_idx, col in enumerate(df.columns, 1):
            max_len = max(len(str(col)), df[col].astype(str).str.len().max())
            worksheet.column_dimensions[chr(64 + col_idx)].width = min(max_len + 4, 50)

    log.info(f"[green]Excel[/green] exportiert → {filepath} ({len(df)} Zeilen)")
    return filepath


def export_csv(items: list[dict], filepath: Path) -> Path:
    """Exportiert nach CSV."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df = to_dataframe(items)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    log.info(f"[green]CSV[/green] exportiert → {filepath} ({len(df)} Zeilen)")
    return filepath


def export_json(items: list[dict], filepath: Path) -> Path:
    """Exportiert nach JSON."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[green]JSON[/green] exportiert → {filepath} ({len(items)} Items)")
    return filepath


EXPORTERS = {
    "excel": (export_excel, ".xlsx"),
    "csv": (export_csv, ".csv"),
    "json": (export_json, ".json"),
}


def export_all(items: list[dict], output_dir: Path, filename: str = "ergebnisse", formats: list[str] | None = None):
    """Exportiert in alle angegebenen Formate."""
    formats = formats or ["excel"]
    exported = []

    for fmt in formats:
        if fmt not in EXPORTERS:
            log.warning(f"Unbekanntes Format: {fmt}")
            continue
        func, ext = EXPORTERS[fmt]
        path = func(items, output_dir / f"{filename}{ext}")
        exported.append(path)

    return exported
