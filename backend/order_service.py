"""Order creation service: builds server-side snapshots, validates, computes totals."""
from __future__ import annotations

import random
import string
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from pricing import BurgerBuilderConfig, compute_burger_price, compute_menu_item_price


def gen_order_number() -> str:
    """BT-XXXXXX using uppercase letters + digits (readable)."""
    alphabet = string.ascii_uppercase + string.digits
    return "BT-" + "".join(random.choices(alphabet, k=6))


def gen_pickup_code() -> str:
    return "".join(random.choices(string.digits, k=4))


def _burger_line_name(denorm: Dict[str, Any], formula: str) -> str:
    # Just the base style name (e.g. "Tacos") — size/meats/cheeses/
    # supplements are rendered separately from burger_config by every
    # consumer (kitchen tablet, admin order drawer, printed tickets), so
    # baking them into the name here just duplicated them everywhere.
    name = denorm.get("style_name") or "Burger"
    if formula == "menu":
        name = f"Menu {name}"
    return name


async def build_snapshots(
    lines: List[dict],
    menu_items: Dict[str, dict],
    burger_cfg: BurgerBuilderConfig,
    soda_flavours: List[str],
) -> Tuple[List[dict], float]:
    """Build validated OrderItemSnapshot list and compute subtotal."""
    snapshots: List[dict] = []
    subtotal = 0.0

    for line in lines:
        qty = int(line.get("quantity") or 1)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be > 0")
        formula = line.get("formula") or "seul"
        if formula not in ("seul", "menu"):
            raise HTTPException(status_code=400, detail=f"Invalid formula: {formula!r}")
        sauces = list(line.get("sauces") or [])
        removals = list(line.get("removable_ingredients") or [])
        if len(sauces) > 2:
            raise HTTPException(status_code=400, detail="Maximum 2 sauces par article.")
        if len(removals) > 2:
            raise HTTPException(status_code=400, detail="Maximum 2 ingrédients retirés par article.")
        # Validate included drink for menu formula
        included_drink = line.get("included_drink")
        included_drink_variant = line.get("included_drink_variant")
        if formula == "menu":
            if not included_drink:
                raise HTTPException(
                    status_code=400,
                    detail="A drink is required for menu formula.",
                )
            if included_drink not in soda_flavours and not soda_flavours:
                # if no soda_flavours configured, accept freely
                pass
            elif soda_flavours and included_drink not in soda_flavours:
                raise HTTPException(
                    status_code=400,
                    detail=f"Drink '{included_drink}' not available.",
                )

        if line.get("is_burger"):
            burger_config = line.get("burger_config") or {}
            unit_price, denorm = compute_burger_price(burger_config, formula, burger_cfg)
            name = _burger_line_name(denorm, formula)
            snapshots.append(
                {
                    "line_id": line.get("line_id"),
                    "item_id": None,
                    "name": name,
                    "is_burger": True,
                    "burger_config": denorm,
                    "formula": formula,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": round(unit_price * qty, 2),
                    "sauces": list(line.get("sauces") or []),
                    "included_drink": included_drink,
                    "included_drink_variant": included_drink_variant,
                    "selected_format": None,
                    "selected_variant": None,
                    "notes": line.get("notes"),
                }
            )
        else:
            item_id = line.get("item_id")
            if not item_id or item_id not in menu_items:
                raise HTTPException(status_code=400, detail="item_id manquant ou invalide.")
            item = menu_items[item_id]
            if not item.get("available", True):
                raise HTTPException(
                    status_code=400,
                    detail=f"Item indisponible : {item.get('name')}",
                )
            if line.get("sauces") and not item.get("uses_sauces", False):
                raise HTTPException(
                    status_code=400,
                    detail=f"Les sauces ne sont pas disponibles pour : {item.get('name')}",
                )
            allowed_removals = item.get("removable_ingredients") or []
            if any(removal not in allowed_removals for removal in removals):
                raise HTTPException(
                    status_code=400,
                    detail=f"Retrait indisponible pour : {item.get('name')}",
                )
            unit_price = compute_menu_item_price(item, formula, line.get("selected_format"))
            display_name = item["name"]
            if line.get("selected_format"):
                display_name += f" ({line['selected_format']})"
            if formula == "menu":
                display_name = f"Menu {display_name}"
            snapshots.append(
                {
                    "line_id": line.get("line_id"),
                    "item_id": item_id,
                    "name": display_name,
                    "is_burger": False,
                    "burger_config": None,
                    "formula": formula,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": round(unit_price * qty, 2),
                    "sauces": sauces,
                    "included_drink": included_drink,
                    "included_drink_variant": included_drink_variant,
                    "selected_format": line.get("selected_format"),
                    "selected_variant": line.get("selected_variant"),
                    "notes": " · ".join(
                        [f"Sans {removal}" for removal in removals] + ([line["notes"]] if line.get("notes") else [])
                    ) or None,
                }
            )
        subtotal += snapshots[-1]["line_total"]

    return snapshots, round(subtotal, 2)
