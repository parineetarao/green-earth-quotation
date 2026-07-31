"""
Display-only formatting shared across pages. Quotation/enquiry "numbers"
(Q-2025-0005 style) are derived entirely from real fields (the row's own
id and the year of its real created_at) -- not a separate stored value --
so there's nothing here to keep in sync with the database.
"""

from datetime import datetime


def quotation_number(quotation: dict) -> str:
    year = datetime.fromisoformat(quotation["created_at"]).year
    return f"Q-{year}-{quotation['id']:04d}"


def enquiry_number(enquiry: dict) -> str:
    year = datetime.fromisoformat(enquiry["created_at"]).year
    return f"E-{year}-{enquiry['id']:04d}"


def capacity_kld(value: float | None) -> str:
    """
    cum/day and KLD (kiloliters/day) are the same physical quantity (1 m3 =
    1 kL) -- KLD is just the more common display unit in Indian STP
    industry practice. The API/DB keep the field named capacity_cum_day;
    this only affects what's printed on screen.
    """
    if value is None:
        return "—"
    return f"{value:g} KLD"


def format_datetime(iso_string: str) -> str:
    return datetime.fromisoformat(iso_string).strftime("%d %b %Y, %I:%M %p")
