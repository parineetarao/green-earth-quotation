"""
Customers -- searchable directory plus each customer's full quotation
history. The "status" filter isn't a stored customer field (the real
schema has none -- see database/models.py) -- it's each customer's most
recent enquiry status, computed here from real enquiry rows so the filter
reflects actual data rather than a fabricated column.
"""

import streamlit as st

from lib import api_client, theme, ui
from lib.api_client import APIError
from lib.format import capacity_kld, format_datetime, quotation_number

theme.page_header("Customers", "All customers")

try:
    enquiries = api_client.list_enquiries()
    quotations = api_client.list_quotations()
except APIError as error:
    st.error(str(error))
    st.stop()

enquiries_by_customer: dict[int, list[dict]] = {}
for e in enquiries:
    cid = e.get("customer_id")
    if cid is not None:
        enquiries_by_customer.setdefault(cid, []).append(e)

quotations_by_customer: dict[int, list[dict]] = {}
enquiry_by_id = {e["id"]: e for e in enquiries}
for q in quotations:
    enquiry = enquiry_by_id.get(q["enquiry_id"])
    cid = enquiry.get("customer_id") if enquiry else None
    if cid is not None:
        quotations_by_customer.setdefault(cid, []).append(q)


def _latest_status(customer_id: int) -> str | None:
    customer_enquiries = enquiries_by_customer.get(customer_id)
    if not customer_enquiries:
        return None
    return max(customer_enquiries, key=lambda e: e["created_at"])["status"]


STATUS_FILTER_OPTIONS = {
    "All Status": None,
    "New": "new",
    "Needs Review": "needs_review",
    "Quoted": "quoted",
    "Closed Won": "closed_won",
    "Closed Lost": "closed_lost",
    "No Enquiries Yet": "__none__",
}

search_col, filter_col = st.columns([2.5, 1])
with search_col:
    search_term = st.text_input(
        "Search", placeholder="Search customers...", label_visibility="collapsed", key="customer_search"
    )
with filter_col:
    status_label = st.selectbox(
        "Status", list(STATUS_FILTER_OPTIONS.keys()), label_visibility="collapsed", key="customer_status_filter"
    )

try:
    customers = api_client.list_customers(search=search_term or None)
except APIError as error:
    st.error(str(error))
    st.stop()

status_value = STATUS_FILTER_OPTIONS[status_label]
if status_value is not None:
    if status_value == "__none__":
        customers = [c for c in customers if _latest_status(c["id"]) is None]
    else:
        customers = [c for c in customers if _latest_status(c["id"]) == status_value]

page_items, meta = ui.paginate(customers, page_size=5, key="customers")

col_widths = [1.4, 1.2, 1.6, 1.1, 1.0, 1.1, 0.6]
headers = ["Customer", "Contact Person", "Email", "Phone", "City", "Total Quotations", ""]
header_cols = st.columns(col_widths)
for col, label in zip(header_cols, headers):
    col.markdown(f'<span class="ge-muted"><b>{label}</b></span>', unsafe_allow_html=True)
st.markdown('<hr style="margin:6px 0 4px 0;">', unsafe_allow_html=True)

if not page_items:
    st.info("No customers match this search/filter.")

for c in page_items:
    cols = st.columns(col_widths)
    cols[0].markdown(f"**{c['name']}**")
    cols[1].write(c.get("contact_person") or "—")
    cols[2].write(c.get("email") or "—")
    cols[3].write(c.get("phone") or "—")
    cols[4].write(c.get("location") or "—")
    cols[5].write(str(len(quotations_by_customer.get(c["id"], []))))
    with cols[6]:
        with st.container(key=f"link-view-customer-{c['id']}"):
            if st.button("View", key=f"view-customer-{c['id']}"):
                st.session_state["selected_customer_id"] = c["id"]
                st.rerun()
    st.markdown('<hr style="margin:4px 0;">', unsafe_allow_html=True)

ui.pagination_footer(meta, "customers")

# ---------------------------------------------------------------------------
# Customer detail + quotation history
# ---------------------------------------------------------------------------

selected_id = st.session_state.get("selected_customer_id")
if selected_id is not None:
    try:
        customer = api_client.get_customer(selected_id)
    except APIError as error:
        st.error(str(error))
        customer = None

    if customer:
        st.write("")
        with st.container(key="link-back-to-customers"):
            if st.button("← Back to customers", key="back-to-customers"):
                st.session_state["selected_customer_id"] = None
                st.rerun()

        st.markdown(f"### {customer['name']}")
        contact_bits = [
            bit
            for bit in (
                f"Contact: {customer['contact_person']}" if customer.get("contact_person") else None,
                customer.get("email"),
                customer.get("phone"),
                customer.get("location"),
            )
            if bit
        ]
        st.markdown(
            f'<div class="ge-muted">{" &nbsp;•&nbsp; ".join(contact_bits)}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("#### Quotation History")
        history = sorted(
            quotations_by_customer.get(customer["id"], []),
            key=lambda q: q["created_at"],
            reverse=True,
        )
        if not history:
            st.caption("No quotations for this customer yet.")
        else:
            hist_widths = [1.1, 1.4, 0.9, 1.2, 1.0, 1.1]
            hist_headers = ["Quotation #", "Created At", "Capacity", "Price (₹)", "Status", "In Verified Range"]
            hist_cols = st.columns(hist_widths)
            for col, label in zip(hist_cols, hist_headers):
                col.markdown(f'<span class="ge-muted"><b>{label}</b></span>', unsafe_allow_html=True)
            st.markdown('<hr style="margin:6px 0 4px 0;">', unsafe_allow_html=True)
            for q in history:
                cols = st.columns(hist_widths)
                cols[0].markdown(f"**{quotation_number(q)}**")
                cols[1].write(format_datetime(q["created_at"]))
                cols[2].write(capacity_kld(q["capacity_cum_day"]))
                cols[3].write(
                    theme.format_inr(q["price_total"])
                    if q["in_verified_range"]
                    else "Outside verified range"
                )
                cols[4].markdown(theme.quotation_status_badge(q["status"]), unsafe_allow_html=True)
                cols[5].markdown(theme.verified_range_badge(q["in_verified_range"]), unsafe_allow_html=True)
