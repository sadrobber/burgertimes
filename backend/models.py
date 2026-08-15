"""Pydantic models for Burger Times ordering platform.

All primary keys are UUID strings, stored as field ``id``. Timestamps are UTC ISO 8601 strings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ----- Helpers ------------------------------------------------------------


def gen_id() -> str:
    return str(uuid.uuid4())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


LabelType = Union[str, dict]  # accept string or {fr, en}


# ----- Admin ---------------------------------------------------------------


class AdminUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    email: EmailStr
    password_hash: str
    role: str = "admin"
    created_at: str = Field(default_factory=utc_now_iso)


class AdminLoginPayload(BaseModel):
    email: EmailStr
    password: str


# ----- Categories ----------------------------------------------------------


class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    slug: str
    label: LabelType
    sort_order: int = 0
    active: bool = True
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class CategoryCreate(BaseModel):
    slug: str
    label: LabelType
    sort_order: int = 0
    active: bool = True


class CategoryUpdate(BaseModel):
    slug: Optional[str] = None
    label: Optional[LabelType] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


# ----- Menu items ----------------------------------------------------------


class MenuItemFormat(BaseModel):
    name: str
    price_seul: float
    price_menu: Optional[float] = None


class MenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    name: str
    description: str = ""
    category: str
    price_seul: float
    price_menu: Optional[float] = None
    formats: List[MenuItemFormat] = Field(default_factory=list)
    variants: List[str] = Field(default_factory=list)
    uses_soda_flavours: bool = False
    available: bool = True
    is_new: bool = False
    has_image: bool = False
    sort_order: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class MenuItemCreate(BaseModel):
    name: str
    description: str = ""
    category: str
    price_seul: float
    price_menu: Optional[float] = None
    formats: List[MenuItemFormat] = Field(default_factory=list)
    variants: List[str] = Field(default_factory=list)
    uses_soda_flavours: bool = False
    available: bool = True
    is_new: bool = False
    sort_order: int = 0
    image_base64: Optional[str] = None


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price_seul: Optional[float] = None
    price_menu: Optional[float] = None
    formats: Optional[List[MenuItemFormat]] = None
    variants: Optional[List[str]] = None
    uses_soda_flavours: Optional[bool] = None
    available: Optional[bool] = None
    is_new: Optional[bool] = None
    sort_order: Optional[int] = None
    image_base64: Optional[str] = None


class BuilderImageUpdate(BaseModel):
    image_base64: Optional[str] = None


# ----- Sauces --------------------------------------------------------------


class Sauce(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    name: str
    sort_order: int = 0
    active: bool = True


class SauceCreate(BaseModel):
    name: str
    sort_order: int = 0
    active: bool = True


class SauceUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


# ----- Burger builder ------------------------------------------------------


class BurgerStyle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    name: str
    description: str = ""
    price_modifier: float = 0.0
    flat_price: Optional[float] = None  # if set, size step is skipped
    flat_price_menu: Optional[float] = None
    max_meats: Optional[int] = None
    available: bool = True
    sort_order: int = 0


class BurgerSize(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    code: str
    label: str
    price_simple: float
    price_menu: float
    nb_meats: int = 1
    supplement_upcharge: float = 0.0
    available: bool = True
    sort_order: int = 0


class BurgerMeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    name: str
    base_price: float = 0.0
    available: bool = True
    sort_order: int = 0


class BurgerCheese(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    name: str
    base_price: float = 0.0
    available: bool = True
    sort_order: int = 0


class BurgerSupplement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    name: str
    base_price: float = 0.0
    available: bool = True
    sort_order: int = 0


# CRUD payloads (thin generic)
class BuilderItemCreate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    price_modifier: Optional[float] = None
    flat_price: Optional[float] = None
    flat_price_menu: Optional[float] = None
    max_meats: Optional[int] = None
    price_simple: Optional[float] = None
    price_menu: Optional[float] = None
    nb_meats: Optional[int] = None
    supplement_upcharge: Optional[float] = None
    base_price: Optional[float] = None
    available: bool = True
    sort_order: int = 0


# ----- Settings singleton --------------------------------------------------


class DayHoursRange(BaseModel):
    open: str  # HH:MM
    close: str  # HH:MM


class DayHours(BaseModel):
    is_open: bool = True
    ranges: List[DayHoursRange] = Field(default_factory=list)


class HoursPerDay(BaseModel):
    mon: DayHours = Field(default_factory=DayHours)
    tue: DayHours = Field(default_factory=DayHours)
    wed: DayHours = Field(default_factory=DayHours)
    thu: DayHours = Field(default_factory=DayHours)
    fri: DayHours = Field(default_factory=DayHours)
    sat: DayHours = Field(default_factory=DayHours)
    sun: DayHours = Field(default_factory=DayHours)


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = "singleton"
    is_open: bool = True
    force_closed: bool = False
    closed_message: str = "Nous sommes fermés. Revenez pendant nos heures d'ouverture !"
    timezone: str = "Europe/Paris"
    hours_per_day: HoursPerDay = Field(default_factory=HoursPerDay)
    last_order_buffer_minutes: int = 15
    closing_soon_window_minutes: int = 30
    too_busy: bool = False
    too_busy_eta_min: int = 45
    too_busy_eta_max: int = 60
    eta_default_min: int = 20
    eta_default_max: int = 30
    soda_flavours: List[str] = Field(default_factory=list)
    delivery_fee_percent: float = 10.0
    free_delivery_threshold: Optional[float] = None
    delivery_postal_codes: List[str] = Field(default_factory=list)
    contact_phone: str = "04.97.07.17.93"
    contact_address: str = "6 Avenue de Villaine, 06240 Beausoleil"
    contact_instagram: str = "@burgertimes_bsl"
    payment_cash_enabled: bool = True
    payment_card_enabled: bool = True
    order_limit_enabled: bool = False
    order_limit_period: str = "day"
    order_limit_max: int = 100
    order_limit_message: str = "On est débordés — la cuisine tourne à fond sur les commandes en cours. Reviens dans quelques heures, promis on garde de la place pour toi."
    last_notified_open_state: Optional[str] = None
    has_builder_image: bool = False
    updated_at: str = Field(default_factory=utc_now_iso)


class SettingsUpdate(BaseModel):
    is_open: Optional[bool] = None
    force_closed: Optional[bool] = None
    closed_message: Optional[str] = None
    timezone: Optional[str] = None
    hours_per_day: Optional[HoursPerDay] = None
    last_order_buffer_minutes: Optional[int] = None
    closing_soon_window_minutes: Optional[int] = None
    too_busy: Optional[bool] = None
    too_busy_eta_min: Optional[int] = None
    too_busy_eta_max: Optional[int] = None
    eta_default_min: Optional[int] = None
    eta_default_max: Optional[int] = None
    soda_flavours: Optional[List[str]] = None
    delivery_fee_percent: Optional[float] = None
    free_delivery_threshold: Optional[float] = None
    delivery_postal_codes: Optional[List[str]] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    contact_instagram: Optional[str] = None
    payment_cash_enabled: Optional[bool] = None
    payment_card_enabled: Optional[bool] = None
    order_limit_enabled: Optional[bool] = None
    order_limit_period: Optional[str] = None
    order_limit_max: Optional[int] = None
    order_limit_message: Optional[str] = None
    last_notified_open_state: Optional[str] = None


# ----- Orders --------------------------------------------------------------


class BurgerConfig(BaseModel):
    style_id: str
    size_id: Optional[str] = None
    meat_ids: List[str] = Field(default_factory=list)
    cheese_ids: List[str] = Field(default_factory=list)
    supplement_ids: List[str] = Field(default_factory=list)
    sauces: List[str] = Field(default_factory=list)


class CartLine(BaseModel):
    line_id: str
    item_id: Optional[str] = None
    quantity: int = 1
    formula: str = "seul"  # 'seul' | 'menu'
    selected_format: Optional[str] = None
    selected_variant: Optional[str] = None
    included_drink: Optional[str] = None
    included_drink_variant: Optional[str] = None
    sauces: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    is_burger: bool = False
    burger_config: Optional[BurgerConfig] = None


class OrderItemSnapshot(BaseModel):
    line_id: str
    name: str
    item_id: Optional[str] = None
    is_burger: bool = False
    burger_config: Optional[dict] = None  # denormalized: names included
    formula: str = "seul"
    quantity: int
    unit_price: float
    line_total: float
    sauces: List[str] = Field(default_factory=list)
    included_drink: Optional[str] = None
    included_drink_variant: Optional[str] = None
    selected_format: Optional[str] = None
    selected_variant: Optional[str] = None
    notes: Optional[str] = None


class StatusHistoryEntry(BaseModel):
    status: str
    at: str
    actor: str
    note: Optional[str] = None


class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    order_number: str
    items: List[OrderItemSnapshot]
    subtotal: float
    delivery_fee: float = 0.0
    total: float
    fulfillment: str  # 'delivery' | 'pickup'
    customer_first_name: str
    customer_last_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    notes: str = ""
    payment_method: str  # 'cash' | 'card_in_person'
    payment_status: str
    status: str = "pending"
    pickup_code: Optional[str] = None
    kitchen_message_id: Optional[int] = None
    kitchen_chat_id: Optional[str] = None
    driver_message_id: Optional[int] = None
    driver_chat_id: Optional[str] = None
    accepted_by: Optional[str] = None
    status_history: List[StatusHistoryEntry] = Field(default_factory=list)
    test_order: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class CheckoutPayload(BaseModel):
    items: List[CartLine]
    fulfillment: str  # 'delivery' | 'pickup'
    customer_first_name: str
    customer_last_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    notes: str = ""
    payment_method: str = "cash"


class OrderStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None


# ----- Reviews -------------------------------------------------------------


class Review(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    author_name: str
    rating: int = 5
    comment: str
    approved: bool = False
    created_at: str = Field(default_factory=utc_now_iso)


class ReviewCreate(BaseModel):
    author_name: str
    rating: int = 5
    comment: str


class ReviewUpdate(BaseModel):
    approved: Optional[bool] = None
    author_name: Optional[str] = None
    rating: Optional[int] = None
    comment: Optional[str] = None


# ----- Waitlist ------------------------------------------------------------


class WaitlistEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=gen_id)
    email: EmailStr
    active: bool = True
    notified_at: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


class WaitlistCreate(BaseModel):
    email: EmailStr
