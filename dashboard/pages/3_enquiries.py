"""
Enquiries -- every enquiry regardless of source (website form, inbound
email, manual entry), with a "Complete" action for needs_review rows: the
one place a human fills in what Gemini's email-extraction step (see
api/services/email_extraction.py) couldn't confidently determine.
"""

import streamlit as st

from lib import api_client, theme, ui
from lib.api_client import APIError
from lib.format import capacity_kld, enquiry_number, format_datetime, quotation_number

theme.page_header("Enquiries", "All sales enquiries")

try:
    enquiries = api_client.list_enquiries()
    customers = api_client.list_customers()
    quotations = api_client.list_quotations()
except APIError as error:
    st.error(str(error))
    st.stop()

customer_by_id = {c["id"]: c for c in customers}

# An enquiry with a rejected quotation resets to status "new" (see
# reject_quotation in api/routes/quotations.py -- it's meant to stay
# available for a fresh generate-quotation attempt), so that reset is left
# exactly as-is. This only adds a visible "previously rejected" marker so
# it isn't indistinguishable from an enquiry that was never quoted at all.
rejected_enquiry_ids = {q["enquiry_id"] for q in quotations if q["status"] == "rejected"}


def _customer_name(e: dict) -> str:
    customer = customer_by_id.get(e.get("customer_id"))
    return customer["name"] if customer else "— (no customer linked)"


filter_col, add_col = st.columns([5, 1])
with filter_col:
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
with add_col:
    if st.button("+ Add enquiry", key="open-add-enquiry", type="primary", use_container_width=True):
        st.session_state["add_enquiry_open"] = True
        st.rerun()

filtered = enquiries if selected_filter == "All" else [e for e in enquiries if e["status"] == selected_filter]
filtered_sorted = sorted(filtered, key=lambda e: e["created_at"], reverse=True)
page_items, meta = ui.paginate(filtered_sorted, page_size=5, key="enquiries")

col_widths = [1.1, 1.3, 0.8, 0.8, 1.0, 1.3, 1.7]
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
    status_html = theme.enquiry_status_badge(e["status"])
    if eid in rejected_enquiry_ids:
        status_html += (
            '<div style="margin-top:4px;">' + theme.badge_html("critical", "Previously rejected") + "</div>"
        )
    cols[4].markdown(status_html, unsafe_allow_html=True)
    cols[5].write(format_datetime(e["created_at"]))
    with cols[6]:
        with st.container(key=f"link-enquiry-action-{eid}"):
            if e["status"] == "needs_review":
                if st.button("Complete", key=f"complete-{eid}"):
                    st.session_state["complete_target"] = eid
                    st.rerun()
            elif e["status"] == "new":
                a1, a2 = st.columns(2)
                with a1:
                    if st.button(
                        "Generate quotation", key=f"genq-{eid}", type="primary", use_container_width=True
                    ):
                        st.session_state["genq_target"] = eid
                        st.session_state["genq_result"] = None
                        st.rerun()
                with a2:
                    if st.button("View", key=f"view-enquiry-{eid}", use_container_width=True):
                        st.session_state["view_target"] = eid
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
# Add enquiry -- manual entry, the primary way enquiries enter the system
# until the website form and email intake are live
# ---------------------------------------------------------------------------

if st.session_state.get("add_enquiry_open"):
    with st.container(border=True):
        st.markdown("**Add Enquiry**")

        c1, c2 = st.columns(2)
        with c1:
            add_customer_name = st.text_input("Customer name *", key="add-name")
            ct1, ct2 = st.columns([1, 2])
            with ct1:
                add_contact_title = st.selectbox(
                    "Title", ["(none)", "Mr", "Ms", "Mrs", "Dr"], key="add-contact-title"
                )
            with ct2:
                add_contact_person = st.text_input("Contact person", key="add-contact")
            add_email = st.text_input("Email", key="add-email")
            add_phone = st.text_input("Phone", key="add-phone")
        with c2:
            add_industry = st.text_input("Industry", key="add-industry")
            add_location = st.text_input("Location", key="add-location")
            add_capacity = st.number_input(
                "Capacity (KLD) *", min_value=0.0, value=0.0, step=10.0, key="add-capacity"
            )
            add_requirement_details = st.text_area("Requirement details", key="add-details")

        b1, b2 = st.columns(2)
        with b1:
            with st.container(key="cancel-add-enquiry"):
                if st.button("Cancel", key="cancel-add-enquiry-btn", use_container_width=True):
                    st.session_state["add_enquiry_open"] = False
                    st.rerun()
        with b2:
            if st.button(
                "Add enquiry", key="submit-add-enquiry", type="primary", use_container_width=True
            ):
                if not add_customer_name.strip():
                    st.warning("Customer name is required.")
                elif not add_capacity or add_capacity <= 0:
                    st.warning("Capacity (KLD) must be a positive number.")
                else:
                    try:
                        api_client.create_enquiry(
                            {
                                "customer_name": add_customer_name.strip(),
                                "contact_person": add_contact_person.strip() or None,
                                "contact_title": add_contact_title if add_contact_title != "(none)" else None,
                                "email": add_email.strip() or None,
                                "phone": add_phone.strip() or None,
                                "industry": add_industry.strip() or None,
                                "location": add_location.strip() or None,
                                "capacity_cum_day": add_capacity,
                                "requirement_details": add_requirement_details.strip() or None,
                                "source": "manual",
                            }
                        )
                        st.session_state["add_enquiry_open"] = False
                        st.toast(f"Enquiry for {add_customer_name.strip()} added.")
                        st.rerun()
                    except APIError as error:
                        st.error(str(error))

# ---------------------------------------------------------------------------
# Generate quotation -- the step manual entry (and any other "new" enquiry)
# was previously stuck without a dashboard path for: capture the two fields
# generate-quotation actually needs beyond what's already on the enquiry
# (ref_no, completion week estimates -- see GenerateQuotationRequest's
# docstring for why these are never defaulted), then call the existing
# POST /enquiries/{id}/generate-quotation. The endpoint itself still owns
# the in_verified_range safeguard -- this form only supplies the inputs.
# ---------------------------------------------------------------------------

genq_target = st.session_state.get("genq_target")
if genq_target is not None:
    target = next((e for e in enquiries if e["id"] == genq_target), None)
    if target is not None:
        existing_customer = customer_by_id.get(target.get("customer_id"))
        with st.container(border=True):
            st.markdown(f"**Generate Quotation -- {enquiry_number(target)} ({_customer_name(target)})**")
            st.caption(f"Capacity: {capacity_kld(target.get('capacity_cum_day'))}")

            c1, c2 = st.columns(2)
            with c1:
                ref_no = st.text_input("Reference No. *", key=f"gq-ref-{genq_target}")
                existing_title = (existing_customer.get("contact_title") if existing_customer else "") or "(none)"
                title_options = ["(none)", "Mr", "Ms", "Mrs", "Dr"]
                at1, at2 = st.columns([1, 2])
                with at1:
                    attn_title = st.selectbox(
                        "Title",
                        title_options,
                        index=title_options.index(existing_title) if existing_title in title_options else 0,
                        key=f"gq-attn-title-{genq_target}",
                    )
                with at2:
                    attn_name = st.text_input(
                        "Attn (contact person)",
                        value=(existing_customer.get("contact_person") if existing_customer else "") or "",
                        key=f"gq-attn-{genq_target}",
                    )
            with c2:
                w1, w2 = st.columns(2)
                with w1:
                    weeks_min = st.number_input(
                        "Completion -- min weeks *", min_value=1, value=8, step=1, key=f"gq-wmin-{genq_target}"
                    )
                with w2:
                    weeks_max = st.number_input(
                        "Completion -- max weeks *", min_value=1, value=10, step=1, key=f"gq-wmax-{genq_target}"
                    )

            b1, b2 = st.columns(2)
            with b1:
                with st.container(key=f"cancel-genq-{genq_target}"):
                    if st.button("Cancel", key=f"cancel-genq-btn-{genq_target}", use_container_width=True):
                        st.session_state["genq_target"] = None
                        st.rerun()
            with b2:
                if st.button(
                    "Generate quotation",
                    key=f"submit-genq-{genq_target}",
                    type="primary",
                    use_container_width=True,
                ):
                    if not ref_no.strip():
                        st.warning("Reference No. is required.")
                    elif weeks_max < weeks_min:
                        st.warning("Max completion weeks must be at least the min.")
                    else:
                        try:
                            resolved_attn_name = " ".join(
                                part for part in (
                                    attn_title if attn_title != "(none)" else None,
                                    attn_name.strip() or None,
                                ) if part
                            ) or None
                            quotation = api_client.generate_quotation(
                                genq_target,
                                ref_no.strip(),
                                int(weeks_min),
                                int(weeks_max),
                                resolved_attn_name,
                            )
                            st.session_state["genq_target"] = None
                            st.session_state["genq_result"] = {
                                "quotation": quotation,
                                "enquiry_label": enquiry_number(target),
                            }
                            st.rerun()
                        except APIError as error:
                            st.error(str(error))

genq_result = st.session_state.get("genq_result")
if genq_result is not None:
    quotation = genq_result["quotation"]
    qnum = quotation_number(quotation)
    with st.container(border=True):
        top_left, top_right = st.columns([5, 1])
        if quotation["in_verified_range"]:
            top_left.success(
                f"{qnum} generated from {genq_result['enquiry_label']} -- "
                f"{theme.format_inr(quotation['price_total'])}. It's now in the Review Queue awaiting approval."
            )
        else:
            top_left.warning(
                f"{qnum} generated from {genq_result['enquiry_label']}, but its capacity is outside the "
                "verified pricing range -- no price was fabricated. It's in the Review Queue's manual-pricing "
                "flow instead."
            )
        with top_right:
            with st.container(key="dismiss-genq-result"):
                if st.button("✕", key="dismiss-genq-result-btn"):
                    st.session_state["genq_result"] = None
                    st.rerun()
        st.page_link(
            "pages/1_review_queue.py", label="Go to Review Queue →", icon=":material/checklist:"
        )

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
                                    "contact_title": existing_customer.get("contact_title") if existing_customer else None,
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
