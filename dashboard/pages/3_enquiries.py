"""
Enquiries -- every enquiry regardless of source (website form, inbound
email, manual entry), with a "Complete" action for needs_review rows: the
one place a human fills in what Gemini's email-extraction step (see
api/services/email_extraction.py) couldn't confidently determine.
"""

import streamlit as st

from lib import api_client, theme, ui
from lib.api_client import APIError
from lib.format import capacity_kld, enquiry_number, format_datetime

theme.page_header("Enquiries", "All sales enquiries")

try:
    enquiries = api_client.list_enquiries()
    customers = api_client.list_customers()
except APIError as error:
    st.error(str(error))
    st.stop()

customer_by_id = {c["id"]: c for c in customers}


def _customer_name(e: dict) -> str:
    customer = customer_by_id.get(e.get("customer_id"))
    return customer["name"] if customer else "— (no customer linked)"


FILTER_OPTIONS = ["All", "new", "needs_review", "quoted", "closed_won", "closed_lost"]
selected_filter = st.pills(
    "Status filter",
    FILTER_OPTIONS,
    default="All",
    format_func=lambda v: theme.STATUS_LABELS.get(v, v) if v != "All" else "All",
    label_visibility="collapsed",
    key="enquiry_status_filter",
)
selected_filter = selected_filter or "All"

filtered = enquiries if selected_filter == "All" else [e for e in enquiries if e["status"] == selected_filter]
filtered_sorted = sorted(filtered, key=lambda e: e["created_at"], reverse=True)
page_items, meta = ui.paginate(filtered_sorted, page_size=5, key="enquiries")

col_widths = [1.1, 1.4, 0.9, 0.9, 1.1, 1.4, 0.9]
headers = ["Enquiry #", "Customer", "Capacity", "Source", "Status", "Created At", "Actions"]
header_cols = st.columns(col_widths)
for col, label in zip(header_cols, headers):
    col.markdown(f'<span class="ge-muted"><b>{label}</b></span>', unsafe_allow_html=True)
st.markdown('<hr style="margin:6px 0 4px 0;">', unsafe_allow_html=True)

if not page_items:
    st.info("No enquiries match this filter.")

SOURCE_LABELS = {"website_form": "Website", "email": "Email", "manual": "Manual"}

for e in page_items:
    eid = e["id"]
    cols = st.columns(col_widths)
    cols[0].markdown(f"**{enquiry_number(e)}**")
    cols[1].write(_customer_name(e))
    cols[2].write(capacity_kld(e.get("capacity_cum_day")))
    cols[3].write(SOURCE_LABELS.get(e["source"], e["source"]))
    cols[4].markdown(theme.enquiry_status_badge(e["status"]), unsafe_allow_html=True)
    cols[5].write(format_datetime(e["created_at"]))
    with cols[6]:
        with st.container(key=f"link-enquiry-action-{eid}"):
            if e["status"] == "needs_review":
                if st.button("Complete", key=f"complete-{eid}"):
                    st.session_state["complete_target"] = eid
                    st.rerun()
            else:
                if st.button("View", key=f"view-enquiry-{eid}"):
                    st.session_state["view_target"] = eid
                    st.rerun()
    st.markdown('<hr style="margin:4px 0;">', unsafe_allow_html=True)

ui.pagination_footer(meta, "enquiries")

# ---------------------------------------------------------------------------
# View -- read-only detail for any enquiry
# ---------------------------------------------------------------------------

view_target = st.session_state.get("view_target")
if view_target is not None:
    target = next((e for e in enquiries if e["id"] == view_target), None)
    if target is not None:
        with st.container(border=True):
            top_left, top_right = st.columns([5, 1])
            top_left.markdown(f"**{enquiry_number(target)} -- {_customer_name(target)}**")
            with top_right:
                with st.container(key=f"cancel-view-{view_target}"):
                    if st.button("✕", key=f"close-view-{view_target}"):
                        st.session_state["view_target"] = None
                        st.rerun()

            d1, d2, d3 = st.columns(3)
            d1.markdown(f"**Capacity**  \n{capacity_kld(target.get('capacity_cum_day'))}")
            d2.markdown(f"**Source**  \n{SOURCE_LABELS.get(target['source'], target['source'])}")
            d3.markdown(f"**Created**  \n{format_datetime(target['created_at'])}")

            if target.get("raw_message"):
                st.markdown("**Raw message**")
                st.text(target["raw_message"])
            if target.get("requirement_details"):
                st.markdown(f"**Requirement details**  \n{target['requirement_details']}")
            timeline_budget = [
                bit
                for bit in (
                    f"Timeline: {target['expected_timeline']}" if target.get("expected_timeline") else None,
                    f"Budget: {target['budget_range']}" if target.get("budget_range") else None,
                )
                if bit
            ]
            if timeline_budget:
                st.markdown(" &nbsp;•&nbsp; ".join(timeline_budget))

# ---------------------------------------------------------------------------
# Complete -- fill in what extraction couldn't determine
# ---------------------------------------------------------------------------

complete_target = st.session_state.get("complete_target")
if complete_target is not None:
    target = next((e for e in enquiries if e["id"] == complete_target), None)
    if target is not None:
        with st.container(border=True):
            st.markdown(f"**Complete Enquiry {enquiry_number(target)}**")

            existing_customer = customer_by_id.get(target.get("customer_id"))
            c1, c2 = st.columns(2)
            with c1:
                customer_name = st.text_input(
                    "Customer", value=existing_customer["name"] if existing_customer else "", key=f"cf-name-{complete_target}"
                )
                capacity = st.number_input(
                    "Capacity (KLD)",
                    min_value=0.0,
                    value=float(target.get("capacity_cum_day") or 0.0),
                    step=10.0,
                    key=f"cf-capacity-{complete_target}",
                )
                timeline = st.selectbox(
                    "Expected Timeline",
                    ["Within 1 month", "Within 3 months", "Within 6 months", "Beyond 6 months", "Not sure yet"],
                    key=f"cf-timeline-{complete_target}",
                )
            with c2:
                requirement_details = st.text_area(
                    "Requirement Details",
                    value=target.get("requirement_details") or "",
                    key=f"cf-details-{complete_target}",
                )
                budget_range = st.text_input(
                    "Budget Range (₹)", value=target.get("budget_range") or "", key=f"cf-budget-{complete_target}"
                )

            b1, b2 = st.columns(2)
            with b1:
                with st.container(key=f"cancel-complete-{complete_target}"):
                    if st.button("Cancel", key=f"cancel-complete-btn-{complete_target}", use_container_width=True):
                        st.session_state["complete_target"] = None
                        st.rerun()
            with b2:
                if st.button(
                    "Mark as completed",
                    key=f"submit-complete-{complete_target}",
                    type="primary",
                    use_container_width=True,
                ):
                    if not customer_name.strip() or not capacity:
                        st.warning("Customer and capacity are required.")
                    else:
                        try:
                            api_client.complete_enquiry(
                                complete_target,
                                {
                                    "customer_name": customer_name.strip(),
                                    "email": existing_customer.get("email") if existing_customer else None,
                                    "phone": existing_customer.get("phone") if existing_customer else None,
                                    "contact_person": existing_customer.get("contact_person") if existing_customer else None,
                                    "industry": existing_customer.get("industry") if existing_customer else None,
                                    "location": existing_customer.get("location") if existing_customer else None,
                                    "capacity_cum_day": capacity,
                                    "requirement_details": requirement_details.strip() or None,
                                    "expected_timeline": timeline,
                                    "budget_range": budget_range.strip() or None,
                                },
                            )
                            st.session_state["complete_target"] = None
                            st.toast(f"{enquiry_number(target)} marked as completed.")
                            st.rerun()
                        except APIError as error:
                            st.error(str(error))
