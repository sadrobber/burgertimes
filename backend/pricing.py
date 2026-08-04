"""Burger builder pricing engine.

Server-side computation. Client prices are ignored.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException


class BurgerBuilderConfig:
    """Lightweight container for burger builder collection lookups."""

    def __init__(
        self,
        styles: Dict[str, dict],
        sizes: Dict[str, dict],
        meats: Dict[str, dict],
        cheeses: Dict[str, dict],
        supplements: Dict[str, dict],
    ) -> None:
        self.styles = styles
        self.sizes = sizes
        self.meats = meats
        self.cheeses = cheeses
        self.supplements = supplements


def _get(d: Dict[str, dict], key: Optional[str], label: str) -> dict:
    if not key or key not in d:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {key!r}")
    v = d[key]
    if not v.get("available", True):
        raise HTTPException(status_code=400, detail=f"{label} unavailable: {v.get('name', key)}")
    return v


def compute_burger_price(
    burger_config: Dict[str, Any],
    formula: str,
    config: BurgerBuilderConfig,
) -> Tuple[float, Dict[str, Any]]:
    """Compute burger unit price + return a denormalized snapshot dict."""
    style_id = burger_config.get("style_id")
    style = _get(config.styles, style_id, "burger style")

    is_flat = style.get("flat_price") is not None
    size_id = burger_config.get("size_id")

    if is_flat:
        base = (
            style.get("flat_price_menu")
            if formula == "menu" and style.get("flat_price_menu") is not None
            else style["flat_price"]
        )
        allowed_meats = style.get("max_meats") or 1
        supp_upcharge = 0.0
        size_snapshot: Optional[dict] = None
    else:
        size = _get(config.sizes, size_id, "burger size")
        base = size["price_menu"] if formula == "menu" else size["price_simple"]
        allowed_meats = size.get("nb_meats", 1)
        supp_upcharge = size.get("supplement_upcharge", 0.0) or 0.0
        size_snapshot = {"id": size["id"], "label": size.get("label"), "code": size.get("code")}

    # Meats
    meat_ids: List[str] = list(burger_config.get("meat_ids") or [])
    if len(meat_ids) != allowed_meats:
        raise HTTPException(
            status_code=400,
            detail=f"This style requires exactly {allowed_meats} meat(s); got {len(meat_ids)}.",
        )
    meats_snapshot: List[dict] = []
    meats_total = 0.0
    for mid in meat_ids:
        m = _get(config.meats, mid, "burger meat")
        meats_total += m.get("base_price", 0.0) or 0.0
        meats_snapshot.append({"id": m["id"], "name": m["name"]})

    # Cheeses (multi-select, each adds base_price)
    cheese_ids: List[str] = list(burger_config.get("cheese_ids") or [])
    cheeses_snapshot: List[dict] = []
    cheeses_total = 0.0
    for cid in cheese_ids:
        c = _get(config.cheeses, cid, "burger cheese")
        cheeses_total += c.get("base_price", 0.0) or 0.0
        cheeses_snapshot.append({"id": c["id"], "name": c["name"]})

    # Supplements (multi-select, each: base_price + size.supplement_upcharge)
    supp_ids: List[str] = list(burger_config.get("supplement_ids") or [])
    supps_snapshot: List[dict] = []
    supps_total = 0.0
    for sid in supp_ids:
        s = _get(config.supplements, sid, "burger supplement")
        supps_total += (s.get("base_price", 0.0) or 0.0) + supp_upcharge
        supps_snapshot.append({"id": s["id"], "name": s["name"]})

    # Style price_modifier
    price_modifier = style.get("price_modifier", 0.0) or 0.0

    unit_price = round(base + price_modifier + meats_total + cheeses_total + supps_total, 2)

    denorm = {
        "style_id": style["id"],
        "style_name": style["name"],
        "size": size_snapshot,
        "meats": meats_snapshot,
        "cheeses": cheeses_snapshot,
        "supplements": supps_snapshot,
        "sauces": list(burger_config.get("sauces") or []),
        "is_flat_style": is_flat,
    }
    return unit_price, denorm


def compute_menu_item_price(item: dict, formula: str, selected_format: Optional[str]) -> float:
    """Price for a plain menu item, optionally with a per-item format."""
    formats = item.get("formats") or []
    fmt = None
    if selected_format:
        for f in formats:
            if f.get("name") == selected_format:
                fmt = f
                break
        if fmt is None:
            raise HTTPException(status_code=400, detail=f"Invalid format: {selected_format!r}")

    if formula == "menu":
        if fmt and fmt.get("price_menu") is not None:
            return float(fmt["price_menu"])
        if item.get("price_menu") is not None:
            return float(item["price_menu"])
        raise HTTPException(status_code=400, detail=f"Item '{item.get('name')}' has no menu price.")
    # seul
    if fmt:
        return float(fmt["price_seul"])
    return float(item["price_seul"])
