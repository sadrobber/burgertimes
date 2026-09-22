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


def _short(name: str, codes: Dict[str, str] | None) -> str:
    return ((codes or {}).get(name) or name)


def _compose_ticket_line(
    *,
    qty: int,
    name_short: str,
    parens: List[str],
    extras: List[str],
    drink: str | None,
    kids_code: str | None = None,
) -> str:
    line = f"{qty}x {name_short}"
    if parens:
        line += f" ({', '.join(parens)})"
    for extra in extras:
        line += f" +{extra}"
    if kids_code:
        line += f" {kids_code}"
    if drink:
        line += f" - {drink}"
    return line


async def build_snapshots(
    lines: List[dict],
    menu_items: Dict[str, dict],
    burger_cfg: BurgerBuilderConfig,
    soda_flavours: List[str],
    sauce_codes: Dict[str, str] | None = None,
    drink_codes: Dict[str, str] | None = None,
    supplement_prices: Dict[str, float] | None = None,
    supplement_codes: Dict[str, str] | None = None,
    removal_codes: Dict[str, str] | None = None,
    kids_code: str = "c",
) -> Tuple[List[dict], float]:
    """Build validated OrderItemSnapshot list and compute subtotal."""
    snapshots: List[dict] = []
    subtotal = 0.0
    supplement_prices = supplement_prices or {}

    for line in lines:
        qty = int(line.get("quantity") or 1)
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be > 0")
        formula = line.get("formula") or "seul"
        if formula not in ("seul", "menu"):
            raise HTTPException(status_code=400, detail=f"Invalid formula: {formula!r}")
        sauces = list(line.get("sauces") or [])
        removals = list(line.get("removable_ingredients") or [])
        supplements = list(line.get("supplements") or [])
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
                pass
            elif soda_flavours and included_drink not in soda_flavours:
                raise HTTPException(
                    status_code=400,
                    detail=f"Drink '{included_drink}' not available.",
                )

        drink_short = _short(included_drink, drink_codes) if included_drink else None

        if line.get("is_burger"):
            burger_config = line.get("burger_config") or {}
            unit_price, denorm = compute_burger_price(burger_config, formula, burger_cfg)
            name = _burger_line_name(denorm, formula)
            # Compact ticket line
            style_short = denorm.get("style_code") or denorm.get("style_name") or "Burger"
            name_short = f"Menu {style_short}" if formula == "menu" else style_short
            parens = [m.get("code") or m.get("name") for m in denorm.get("meats") or []]
            if denorm.get("sauce_fromagere") is False:
                parens.append("sans from")
            extras = [c.get("code") or c.get("name") for c in denorm.get("cheeses") or []]
            extras += [s.get("code") or s.get("name") for s in denorm.get("supplements") or []]
            extras += [_short(s, sauce_codes) for s in (denorm.get("sauces") or [])]
            ticket_line = _compose_ticket_line(
                qty=qty, name_short=name_short, parens=parens, extras=extras,
                drink=drink_short, kids_code=None,
            )
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
                    "supplements": [],
                    "ticket_line": ticket_line,
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
            allowed_supps = item.get("supplement_options") or []
            if any(sup not in allowed_supps for sup in supplements):
                raise HTTPException(
                    status_code=400,
                    detail=f"Supplément indisponible pour : {item.get('name')}",
                )
            unit_price = compute_menu_item_price(item, formula, line.get("selected_format"))
            unit_price = round(unit_price + sum(supplement_prices.get(s, 0.0) for s in supplements), 2)
            display_name = item["name"]
            if line.get("selected_format"):
                display_name += f" ({line['selected_format']})"
            if formula == "menu":
                display_name = f"Menu {display_name}"
            # Compact ticket line
            item_short = item.get("ticket_shortcode") or item["name"]
            if line.get("selected_format"):
                item_short += f" {line['selected_format']}"
            name_short = f"Menu {item_short}" if formula == "menu" else item_short
            parens = [f"Sans {_short(r, removal_codes)}" for r in removals]
            extras = [_short(s, supplement_codes) for s in supplements] + [_short(s, sauce_codes) for s in sauces]
            is_kids = (item.get("category") == "kids")
            ticket_line = _compose_ticket_line(
                qty=qty, name_short=name_short, parens=parens, extras=extras,
                drink=drink_short, kids_code=(kids_code if is_kids else None),
            )
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
                    "supplements": supplements,
                    "ticket_line": ticket_line,
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
