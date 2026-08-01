"""
Review Queue -- draft quotations awaiting a human decision. Every
quotation lands here in "draft" status (see database/models.py) and stays
until a person explicitly approves, rejects, or (if the capacity was
outside the verified pricing range) sends it for manual pricing. Nothing
on this page emails a customer without the confirmation dialog below --
that's a CLAUDE.md non-negotiable, not a UI nicety.
"""

import streamlit as st

from lib import api_client, theme, ui
from lib.api_client import APIError
from lib.format import capacity_kld, format_datetime, now_ist_str, quotation_number

theme.page_header("Review Queue", "Draft quotations awaiting review")

header_left, header_right = st.columns([3, 1])
with header_right:
    r1, r2 = st.columns([2, 1])
    with r1:
        st.markdown(
            f'<div class="ge-muted" style="text-align:right;padding-top:8px;">'
            f"Last refreshed: {now_ist_str()}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with r2:
        if st.button("", icon=":material/refresh:", key="rq-refresh"):
            api_client.clear_all_caches()
            st.rerun()

try:
    quotations = [q for q in api_client.list_quotations() if q["status"] == "draft"]
    enquiries = api_client.list_enquiries()
    customers = api_client.list_customers()
except APIError as error:
    st.error(str(error))
    st.stop()

enquiry_by_id = {e["id"]: e for e in enquiries}
customer_by_id = {c["id"]: c for c in customers}


def _customer_name(q: dict) -> str:
    enquiry = enquiry_by_id.get(q["enquiry_id"])
    if not enquiry:
        return "—"
    customer = customer_by_id.get(enquiry.get("customer_id"))
    return customer["name"] if customer else "—"


def _render_document_downloads(quotation: dict, qnum: str, key_prefix: str) -> None:
    """
    Shared by the per-row expander and the approve-and-send confirmation
    dialog -- a reviewer must be able to see the actual letter and
    Annexure IV price sheet before deciding, not just the summary row.
    """
    if not quotation["in_verified_range"]:
        st.caption(
            "No documents were generated for this quotation -- the capacity is outside "
            "the verified pricing range (see the note on quotation_service.py)."
        )
        return

    try:
        letter_bytes = api_client.get_quotation_letter(quotation["id"])
        annexure_bytes = api_client.get_quotation_annexure(quotation["id"])
    except APIError as error:
        st.error(str(error))
        return

    d1, d2 = st.columns(2)
    with d1:
        if letter_bytes:
            st.download_button(
                "Quotation letter (PDF)",
                letter_bytes,
                file_name=f"{qnum}_letter.pdf",
                mime="application/pdf",
                key=f"{key_prefix}-letter",
                use_container_width=True,
            )
        else:
            st.caption("Quotation letter not available.")
    with d2:
        if annexure_bytes:
            st.download_button(
                "Annexure IV -- price sheet (PDF)",
                annexure_bytes,
                file_name=f"{qnum}_annexure.pdf",
                mime="application/pdf",
                key=f"{key_prefix}-annexure",
                use_container_width=True,
            )
        else:
            st.caption("Annexure IV not available.")


quotations_sorted = sorted(quotations, key=lambda q: q["created_at"], reverse=True)
page_items, meta = ui.paginate(quotations_sorted, page_size=5, key="review_queue")

if not page_items:
    st.info("No draft quotations right now -- the review queue is empty.")

col_widths = [1.1, 1.4, 0.8, 1.2, 1.0, 0.9, 1.3, 2.1]
headers = ["Quotation #", "Customer", "Capacity", "Price (₹)", "In Verified Range", "Status", "Created At", "Actions"]
header_cols = st.columns(col_widths)
for col, label in zip(header_cols, headers):
    col.markdown(f'<span class="ge-muted"><b>{label}</b></span>', unsafe_allow_html=True)

st.markdown('<hr style="margin:6px 0 4px 0;">', unsafe_allow_html=True)

manual_target = st.session_state.get("manual_pricing_target")
approve_target = st.session_state.get("approve_target")

for q in page_items:
    qid = q["id"]
    qnum = quotation_number(q)
    cols = st.columns(col_widths)

    cols[0].markdown(f"**{qnum}**")
    cols[1].write(_customer_name(q))
    cols[2].write(capacity_kld(q['capacity_cum_day']))

    if q["in_verified_range"]:
        cols[3].write(theme.format_inr(q["price_total"]))
    else:
        cols[3].markdown(theme.badge_html("warning", "Outside verified range"), unsafe_allow_html=True)

    cols[4].markdown(theme.verified_range_badge(q["in_verified_range"]), unsafe_allow_html=True)
    cols[5].markdown(theme.quotation_status_badge(q["status"]), unsafe_allow_html=True)
    cols[6].write(format_datetime(q["created_at"]))

    with cols[7]:
        if q["in_verified_range"]:
            a1, a2 = st.columns(2)
            with a1:
                if st.button("Approve and send", key=f"approve-{qid}", type="primary", use_container_width=True):
                    st.session_state["approve_target"] = qid
                    st.rerun()
            with a2:
                with st.container(key=f"reject-{qid}"):
                    if st.button("Reject", key=f"reject-btn-{qid}", use_container_width=True):
                        try:
                            api_client.reject_quotation(qid)
                            st.toast(f"{qnum} rejected.")
                            st.rerun()
                        except APIError as error:
                            st.error(str(error))
        else:
            with st.container(key=f"neutral-price-{qid}"):
                if st.button("Price manually", key=f"price-manually-{qid}", use_container_width=True):
                    st.session_state["manual_pricing_target"] = qid
                    st.rerun()

        # Subtle overflow action, deliberately not a third full-width button
        # next to Approve/Reject -- this is for the exceptional case where
        # the business owner sent the quotation himself (custom email body,
        # PDFs attached by hand), not the everyday path.
        with st.popover("More options", use_container_width=True):
            st.caption(
                "If this quotation was already sent outside the system "
                "(e.g. the business owner emailed it himself), record it "
                "here. This will not send anything through email."
            )
            manual_note = st.text_area(
                "Note (required)",
                key=f"sent-manually-note-{qid}",
                placeholder="e.g. sent manually on 2026-08-01, confirmed by phone",
            )
            if st.button("Mark as sent manually", key=f"sent-manually-btn-{qid}"):
                if not manual_note.strip():
                    st.warning("Add a short note before saving.")
                else:
                    try:
                        api_client.mark_sent_manually(qid, manual_note.strip())
                        st.toast(f"{qnum} marked as sent manually.")
                        st.rerun()
                    except APIError as error:
                        st.error(str(error))

    with st.expander(f"View documents -- {qnum}"):
        _render_document_downloads(q, qnum, key_prefix=f"row-{qid}")

    st.markdown('<hr style="margin:4px 0;">', unsafe_allow_html=True)

ui.pagination_footer(meta, "quotations")


# ---------------------------------------------------------------------------
# Price manually -- inline note panel
# ---------------------------------------------------------------------------

if manual_target is not None:
    target = next((q for q in quotations if q["id"] == manual_target), None)
    if target is not None:
        with st.container(border=True):
            st.markdown(f"**Price manually -- {quotation_number(target)}**")
            st.caption(
                f"{capacity_kld(target['capacity_cum_day'])} is outside the verified pricing range. "
                "Add a note for the team handling manual pricing; this does not set a price."
            )
            note = st.text_area("Note", key=f"note-{manual_target}", label_visibility="collapsed")
            b1, b2 = st.columns([1, 1])
            with b1:
                with st.container(key=f"cancel-manual-{manual_target}"):
                    if st.button("Cancel", key=f"cancel-manual-btn-{manual_target}", use_container_width=True):
                        st.session_state["manual_pricing_target"] = None
                        st.rerun()
            with b2:
                if st.button(
                    "Save note", key=f"save-manual-{manual_target}", type="primary", use_container_width=True
                ):
                    if not note.strip():
                        st.warning("Add a short note before saving.")
                    else:
                        try:
                            api_client.manual_pricing_note(manual_target, note.strip())
                            st.session_state["manual_pricing_target"] = None
                            st.toast("Sent for manual pricing.")
                            st.rerun()
                        except APIError as error:
                            st.error(str(error))


# ---------------------------------------------------------------------------
# Approve and send -- confirmation dialog (never sends on the first click)
# ---------------------------------------------------------------------------

if approve_target is not None:
    target = next((q for q in quotations if q["id"] == approve_target), None)
    if target is not None:
        qnum = quotation_number(target)
        customer_name = _customer_name(target)

        @st.dialog(f"Approve and send quotation {qnum}")
        def _confirm_approve(qid=approve_target, qnum=qnum, customer_name=customer_name, target=target):
            st.markdown("**Review the documents before sending:**")
            _render_document_downloads(target, qnum, key_prefix=f"dialog-{qid}")
            st.divider()
            st.write(
                f"Are you sure you want to send this to **{customer_name}**?"
            )
            c1, c2 = st.columns(2)
            with c1:
                with st.container(key=f"cancel-approve-{qid}"):
                    if st.button("Cancel", key=f"cancel-approve-btn-{qid}", use_container_width=True):
                        st.session_state["approve_target"] = None
                        st.rerun()
            with c2:
                if st.button(
                    "Yes, approve and send", key=f"confirm-approve-{qid}", type="primary", use_container_width=True
                ):
                    try:
                        api_client.approve_and_send(qid)
                        st.session_state["approve_target"] = None
                        st.toast(f"{qnum} sent.")
                        st.rerun()
                    except APIError as error:
                        st.error(str(error))

        _confirm_approve()
    else:
        st.session_state["approve_target"] = None
