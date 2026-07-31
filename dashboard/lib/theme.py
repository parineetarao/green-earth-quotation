"""
Colors, CSS, and small HTML-rendering helpers shared by every dashboard
page, so the look (dark forest-green sidebar, white content area, green
accent buttons, tinted status pills) stays consistent instead of each page
reinventing its own styling.

Streamlit doesn't expose per-widget CSS classes for things like "make this
one button red instead of green", so buttons that need a non-default look
are wrapped in `st.container(key=...)` -- Streamlit stamps that key onto the
container's own class as `st-key-<key>`, which the CSS below targets with
an attribute-contains selector so every button sharing a key *prefix*
(e.g. every "reject-{quotation_id}") picks up the same rule.
"""

import base64
from pathlib import Path

import streamlit as st

BRAND_DARK = "#0d2818"
BRAND_DARK_ACTIVE = "#16402a"
BRAND_ACCENT = "#1a7f37"
BRAND_ACCENT_HOVER = "#166a2e"
SIDEBAR_TEXT = "#eef3ef"
SIDEBAR_MUTED = "#9fb8a8"

TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#5b5b58"
TEXT_MUTED = "#8a8984"
CARD_BORDER = "#e7e5e0"

# Badge "kind" -> (background, text). Reused for every status pill in the
# app (enquiries, quotations, in_verified_range) so the same color always
# means the same thing everywhere it appears.
BADGE_COLORS = {
    "good": ("#e6f7ea", "#0f5c22"),
    "warning": ("#fdf1d8", "#8a5a00"),
    "critical": ("#fbe7e7", "#a12626"),
    "info": ("#e7eef9", "#1c4a86"),
    "violet": ("#efe9fb", "#4a3aa7"),
    "neutral": ("#eef0ee", "#52514e"),
}

ENQUIRY_STATUS_BADGE = {
    "new": "neutral",
    "needs_review": "warning",
    "quoted": "info",
    "closed_won": "good",
    "closed_lost": "critical",
}

QUOTATION_STATUS_BADGE = {
    "draft": "info",
    "sent": "violet",
    "won": "good",
    "lost": "critical",
    "no_response": "neutral",
    "rejected": "critical",
    "needs_manual_pricing": "warning",
}

VERIFIED_RANGE_BADGE = {True: "good", False: "warning"}

STATUS_LABELS = {
    "new": "New",
    "needs_review": "Needs Review",
    "quoted": "Quoted",
    "closed_won": "Closed Won",
    "closed_lost": "Closed Lost",
    "draft": "Draft",
    "sent": "Sent",
    "won": "Won",
    "lost": "Lost",
    "no_response": "No Response",
    "rejected": "Rejected",
    "needs_manual_pricing": "Needs Manual Pricing",
}

LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "logo.png"

# Minimal Lucide-style (stroke=currentColor) icon paths, hand-picked to
# match the reference design's thin outline sidebar icons without pulling
# in an icon font/library.
_ICONS = {
    "review_queue": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 3v4"/><path d="M8 11h8"/><path d="M8 15h5"/>',
    "customers": '<path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "enquiries": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 6-10 7L2 6"/>',
    "summary": '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "refresh": '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "back": '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
}


def icon_svg(name: str, size: int = 18, color: str = "currentColor") -> str:
    path = _ICONS.get(name, "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


def badge_html(kind: str, label: str) -> str:
    bg, text = BADGE_COLORS.get(kind, BADGE_COLORS["neutral"])
    return (
        f'<span style="background:{bg};color:{text};padding:3px 10px;'
        f'border-radius:999px;font-size:0.78rem;font-weight:600;'
        f'white-space:nowrap;">{label}</span>'
    )


def enquiry_status_badge(status: str) -> str:
    kind = ENQUIRY_STATUS_BADGE.get(status, "neutral")
    return badge_html(kind, STATUS_LABELS.get(status, status))


def quotation_status_badge(status: str) -> str:
    kind = QUOTATION_STATUS_BADGE.get(status, "neutral")
    return badge_html(kind, STATUS_LABELS.get(status, status))


def verified_range_badge(in_verified_range: bool) -> str:
    kind = VERIFIED_RANGE_BADGE[in_verified_range]
    return badge_html(kind, "Yes" if in_verified_range else "No")


def format_inr(amount: float | None) -> str:
    """
    Indian digit grouping (last 3 digits, then groups of 2): 1860000 ->
    "18,60,000". Formatted here rather than trusting a locale package --
    same reasoning as documents/number_to_words_indian.py: this is a small,
    easily hand-verified piece of formatting logic, not worth an external
    dependency for.
    """
    if amount is None:
        return "-"
    whole = int(round(amount))
    sign = "-" if whole < 0 else ""
    whole = abs(whole)
    s = str(whole)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    return f"{sign}₹ {grouped}"


def _logo_data_uri() -> str | None:
    if not LOGO_PATH.exists():
        return None
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_sidebar_brand() -> None:
    logo_uri = _logo_data_uri()
    logo_html = (
        # Real logo: rendered as-is, no added background -- the artwork's
        # own transparent glow is meant to sit directly on the dark
        # sidebar, not be clipped into a hard white circle.
        f'<img src="{logo_uri}" style="width:48px;height:48px;object-fit:contain;'
        f'flex-shrink:0;" />'
        if logo_uri
        # Placeholder only (no logo file yet): a plain white circle stands
        # in for where the real mark will sit.
        else '<div style="width:42px;height:42px;border-radius:50%;background:#ffffff;'
        'flex-shrink:0;"></div>'
    )
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;padding:4px 2px 18px 2px;">
            {logo_html}
            <div style="line-height:1.25;">
                <div style="color:{SIDEBAR_TEXT};font-weight:700;font-size:0.95rem;">
                    Green Earth
                </div>
                <div style="color:{SIDEBAR_MUTED};font-size:0.68rem;">
                    Engineers and Consultants
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if logo_uri is None:
        st.caption(
            "Drop the real logo at dashboard/static/logo.png to replace this placeholder."
        )


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        [data-testid="stSidebar"] {{
            background-color: {BRAND_DARK};
        }}
        [data-testid="stSidebar"] * {{
            color: {SIDEBAR_TEXT};
        }}
        [data-testid="stSidebarUserContent"] {{
            display: flex;
            flex-direction: column;
            min-height: calc(100vh - 3rem);
            padding-top: 0.5rem;
        }}
        [class*="st-key-sidebar-logout-spacer"] {{
            margin-top: auto;
        }}

        /* page_link nav rows, styled to look like flat icon+label buttons */
        [data-testid="stSidebar"] [data-testid="stPageLink"] {{
            border-radius: 8px;
            padding: 2px 6px;
            margin-bottom: 2px;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"]:hover {{
            background-color: {BRAND_DARK_ACTIVE};
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] p {{
            font-size: 0.92rem;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"][aria-current="page"] {{
            background-color: {BRAND_DARK_ACTIVE};
            font-weight: 600;
        }}

        /* Primary (green) buttons */
        [data-testid="stSidebar"] div[data-testid="stButton"] button,
        button[kind="primary"], button[kind="primaryFormSubmit"],
        [data-testid="stBaseButton-primary"] {{
            background-color: {BRAND_ACCENT} !important;
            color: #ffffff !important;
            border: 1px solid {BRAND_ACCENT} !important;
            border-radius: 6px !important;
        }}
        button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{
            background-color: {BRAND_ACCENT_HOVER} !important;
            border-color: {BRAND_ACCENT_HOVER} !important;
        }}
        [data-testid="stSidebar"] div[data-testid="stButton"] button {{
            background-color: transparent !important;
            border: none !important;
            color: {SIDEBAR_TEXT} !important;
            text-align: left !important;
            justify-content: flex-start !important;
        }}
        [data-testid="stSidebar"] div[data-testid="stButton"] button:hover {{
            background-color: {BRAND_DARK_ACTIVE} !important;
            color: #ffffff !important;
        }}

        /* Danger (red-outline) buttons: wrap in st.container(key="reject-...") */
        [class*="st-key-reject-"] button {{
            background-color: #ffffff !important;
            color: #c0392b !important;
            border: 1px solid #d03b3b !important;
            border-radius: 6px !important;
        }}
        [class*="st-key-reject-"] button:hover {{
            background-color: #fbe7e7 !important;
        }}

        /* Neutral outline buttons (Price manually, Cancel, View) */
        [class*="st-key-neutral-"] button, [class*="st-key-cancel-"] button {{
            background-color: #ffffff !important;
            color: {TEXT_PRIMARY} !important;
            border: 1px solid #d8d6d0 !important;
            border-radius: 6px !important;
        }}
        [class*="st-key-neutral-"] button:hover, [class*="st-key-cancel-"] button:hover {{
            background-color: #f5f4f1 !important;
        }}

        /* Link-style buttons (View / Complete in tables) */
        [class*="st-key-link-"] button {{
            background-color: transparent !important;
            color: #1c4a86 !important;
            border: none !important;
            padding: 0 !important;
            font-weight: 600;
        }}
        [class*="st-key-link-"] button:hover {{
            text-decoration: underline;
        }}

        .ge-page-title {{
            font-size: 1.7rem;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            margin-bottom: 0;
        }}
        .ge-page-subtitle {{
            color: {TEXT_SECONDARY};
            font-size: 0.92rem;
            margin-top: 2px;
        }}
        .ge-panel {{
            border: 1px solid {CARD_BORDER};
            border-radius: 10px;
            padding: 1rem 1.2rem;
        }}
        .ge-muted {{
            color: {TEXT_MUTED};
            font-size: 0.85rem;
        }}
        div[data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid {CARD_BORDER};
            border-radius: 10px;
            padding: 0.9rem 1rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="ge-page-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="ge-page-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.write("")
