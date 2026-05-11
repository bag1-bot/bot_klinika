from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CatalogServiceItem:
    section: str
    service: str
    price: str
    consists_of: list[str]
    nomenclature: list[str]


def _repo_root() -> Path:
    # bot/services/price_catalog.py -> bot/services -> bot -> repo root
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_price_catalog() -> dict[str, Any]:
    path = _repo_root() / "tools" / "price_parsed_full.pretty.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_sections() -> list[str]:
    data = load_price_catalog()
    sections = data.get("разделы") or []
    # Keep stable ordering and avoid duplicates
    seen: set[str] = set()
    out: list[str] = []
    for s in sections:
        s = str(s).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def list_services(section: str) -> list[CatalogServiceItem]:
    catalog = load_price_catalog()
    all_data = catalog.get("данные") or {}
    items = all_data.get(section) or []
    out: list[CatalogServiceItem] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        service = str(it.get("услуга", "")).strip()
        if not service:
            continue
        price_val = it.get("цена", "")
        price = str(price_val).strip()
        consists = [str(x).strip() for x in (it.get("состоит_из") or []) if str(x).strip()]
        nomen = [str(x).strip() for x in (it.get("номенклатура") or []) if str(x).strip()]
        out.append(
            CatalogServiceItem(
                section=section,
                service=service,
                price=price,
                consists_of=consists,
                nomenclature=nomen,
            )
        )
    return out


def get_service(section: str, service_idx: int) -> CatalogServiceItem | None:
    services = list_services(section)
    if service_idx < 0 or service_idx >= len(services):
        return None
    return services[service_idx]

