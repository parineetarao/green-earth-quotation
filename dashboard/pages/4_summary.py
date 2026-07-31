"""
Summary -- month-scoped headline metrics, two structural bar charts, and a
recent-activity feed. Every number here comes from real enquiries/
quotations fetched from the API; nothing is a stored "analytics" table --
this is plain aggregation in Python over the same rows the other pages use
(per CLAUDE.md Phase C's "plain SQL aggregation, no ML" instruction).

"Recent Activity" is built only from events this schema can actually prove
happened at a real timestamp (an enquiry's created_at, a quotation's
created_at, a quotation's sent_at) -- there's no status-change history
table, so a "status updated to X" line would need a fabricated timestamp,
which is exactly what CLAUDE.md's non-negotiables rule out.
"""

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from lib import api_client, theme
from lib.api_client import APIError
from lib.format import format_datetime, quotation_number, enquiry_number

theme.page_header("Summary", "Key metrics and insights")

try:
    enquiries = api_client.list_enquiries()
    quotations = api_client.list_quotations()
    customers = api_client.list_customers()
except APIError as error:
    st.error(str(error))
    st.stop()

customer_by_id = {c["id"]: c for c in customers}
enquiry_by_id = {e["id"]: e for e in enquiries}

BRAND_GREEN = theme.BRAND_ACCENT


def _month_options(n: int = 12) -> list[tuple[int, int]]:
    today = datetime.now()
    options = []
    y, m = today.year, today.month
    for _ in range(n):
        options.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return options


def _month_label(ym: tuple[int, int]) -> str:
    return datetime(ym[0], ym[1], 1).strftime("%B %Y")


def _prev_month(ym: tuple[int, int]) -> tuple[int, int]:
    y, m = ym
    return (y - 1, 12) if m == 1 else (y, m - 1)


def _in_month(iso_string: str, ym: tuple[int, int]) -> bool:
    dt = datetime.fromisoformat(iso_string)
    return (dt.year, dt.month) == ym


month_col, _ = st.columns([1, 3])
with month_col:
    month_options = _month_options()
    selected_month = st.selectbox(
        "Month", month_options, index=0, format_func=_month_label, label_visibility="collapsed"
    )
prev_month = _prev_month(selected_month)


def _delta_pct(current: int, previous: int) -> tuple[str, str]:
    if previous == 0:
        return ("New" if current > 0 else "No change"), ("good" if current > 0 else "neutral")
    change = (current - previous) / previous * 100
    arrow = "↑" if change >= 0 else "↓"
    return f"{arrow} {abs(change):.0f}%", ("good" if change >= 0 else "critical")


def _delta_pp(current: float, previous: float) -> tuple[str, str]:
    diff = current - previous
    arrow = "↑" if diff >= 0 else "↓"
    return f"{arrow} {abs(diff):.1f} pp", ("good" if diff >= 0 else "critical")


enquiries_this_month = [e for e in enquiries if _in_month(e["created_at"], selected_month)]
enquiries_prev_month = [e for e in enquiries if _in_month(e["created_at"], prev_month)]

quotations_this_month = [q for q in quotations if _in_month(q["created_at"], selected_month)]
quotations_prev_month = [q for q in quotations if _in_month(q["created_at"], prev_month)]


def _win_rate(month_quotations: list[dict]) -> float:
    if not month_quotations:
        return 0.0
    won = sum(1 for q in month_quotations if q["status"] == "won")
    return won / len(month_quotations) * 100


def _drafts_pending(month_quotations: list[dict]) -> int:
    return sum(1 for q in month_quotations if q["status"] == "draft")


win_rate_this = _win_rate(quotations_this_month)
win_rate_prev = _win_rate(quotations_prev_month)
drafts_this = _drafts_pending(quotations_this_month)
drafts_prev = _drafts_pending(quotations_prev_month)

month_label = _month_label(prev_month)

m1, m2, m3, m4 = st.columns(4)
tiles = [
    (m1, "Enquiries This Month", str(len(enquiries_this_month)), *_delta_pct(len(enquiries_this_month), len(enquiries_prev_month))),
    (m2, "Quotations Created", str(len(quotations_this_month)), *_delta_pct(len(quotations_this_month), len(quotations_prev_month))),
    (m3, "Win Rate", f"{win_rate_this:.1f}%", *_delta_pp(win_rate_this, win_rate_prev)),
    (m4, "Drafts Pending Review", str(drafts_this), *_delta_pct(drafts_this, drafts_prev)),
]
for col, label, value, delta_text, delta_kind in tiles:
    with col:
        st.metric(label, value)
        color = {"good": "#0f5c22", "critical": "#a12626", "neutral": theme.TEXT_MUTED}[delta_kind]
        st.markdown(
            f'<div style="color:{color};font-size:0.8rem;margin-top:-10px;">{delta_text} vs {month_label}</div>',
            unsafe_allow_html=True,
        )

st.write("")

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

chart_left, chart_right = st.columns(2)

with chart_left:
    st.markdown("**Enquiries by Status**")
    status_order = ["new", "needs_review", "quoted", "closed_won", "closed_lost"]
    counts = {status: 0 for status in status_order}
    for e in enquiries:
        if e["status"] in counts:
            counts[e["status"]] += 1
    df = pd.DataFrame(
        {
            "status": [theme.STATUS_LABELS[s] for s in status_order],
            "order": range(len(status_order)),
            "count": [counts[s] for s in status_order],
        }
    )
    chart = (
        alt.Chart(df)
        .mark_bar(color=BRAND_GREEN, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("status:N", sort=list(df["status"]), title=None, axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("count:Q", title=None),
            tooltip=["status", "count"],
        )
    )
    labels = chart.mark_text(dy=-8, color=theme.TEXT_SECONDARY).encode(text="count:Q")
    st.altair_chart((chart + labels).properties(height=280), use_container_width=True)

with chart_right:
    st.markdown("**Quotations by Month**")
    trend_months = list(reversed(_month_options(6)))
    trend_counts = []
    for ym in trend_months:
        trend_counts.append(sum(1 for q in quotations if _in_month(q["created_at"], ym)))
    df2 = pd.DataFrame(
        {
            "month": [datetime(y, m, 1).strftime("%b %Y") for y, m in trend_months],
            "order": range(len(trend_months)),
            "count": trend_counts,
        }
    )
    chart2 = (
        alt.Chart(df2)
        .mark_bar(color=BRAND_GREEN, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("month:N", sort=list(df2["month"]), title=None),
            y=alt.Y("count:Q", title=None),
            tooltip=["month", "count"],
        )
    )
    labels2 = chart2.mark_text(dy=-8, color=theme.TEXT_SECONDARY).encode(text="count:Q")
    st.altair_chart((chart2 + labels2).properties(height=280), use_container_width=True)

st.write("")

# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------

header_col, link_col = st.columns([4, 1])
header_col.markdown("**Recent Activity**")
with link_col:
    with st.container(key="link-view-all-activity"):
        show_all = st.toggle("View all activity", key="show_all_activity", label_visibility="visible")

events = []
for e in enquiries:
    customer = customer_by_id.get(e.get("customer_id"))
    events.append((e["created_at"], f"{enquiry_number(e)} received from {customer['name'] if customer else 'an unlinked customer'}"))
for q in quotations:
    enquiry = enquiry_by_id.get(q["enquiry_id"])
    customer = customer_by_id.get(enquiry.get("customer_id")) if enquiry else None
    name = customer["name"] if customer else "an unlinked customer"
    events.append((q["created_at"], f"{quotation_number(q)} created for {name}"))
    if q.get("sent_at"):
        events.append((q["sent_at"], f"{quotation_number(q)} sent to {name}"))

events.sort(key=lambda item: item[0], reverse=True)
visible_events = events if show_all else events[:5]

if not visible_events:
    st.caption("No activity yet.")
for timestamp, description in visible_events:
    ec1, ec2 = st.columns([4, 1])
    ec1.write(description)
    ec2.markdown(
        f'<div class="ge-muted" style="text-align:right;">{format_datetime(timestamp)}</div>',
        unsafe_allow_html=True,
    )
