"""
GET /quotations, POST /quotations/{id}/approve-and-send, PATCH /quotations/{id}/status.

approve-and-send is the ONLY route in this entire system that emails a
customer, and it must be called explicitly -- never triggered by
generate-quotation or anything automatic. This is a CLAUDE.md
non-negotiable, not a stylistic choice.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import (
    QuotationManualPricingNote,
    QuotationMarkSentManuallyNote,
    QuotationOut,
    QuotationStatusUpdate,
)
from api.services.email_sender import send_quotation_email
from database.models import EnquiryStatus, Quotation, QuotationStatus
from database.session import get_db

router = APIRouter(prefix="/quotations", tags=["quotations"])


@router.get("", response_model=list[QuotationOut])
def list_quotations(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Quotation).order_by(Quotation.created_at.desc())
    if status:
        stmt = stmt.where(Quotation.status == status)
    return db.execute(stmt).scalars().all()


def _document_response(path_value: str | None, download_name: str) -> FileResponse:
    """
    Shared lookup for the two document-download routes below. A reviewer
    must be able to see the exact PDF before approving/sending it (that's
    the whole point of a review queue) -- 404 with a clear reason rather
    than a broken/empty download when the capacity was outside the
    verified pricing range and no document was ever generated (see
    api/services/quotation_service.py).
    """
    if not path_value:
        raise HTTPException(
            status_code=404,
            detail="No document has been generated for this quotation (likely outside the "
            "verified pricing range).",
        )
    path = Path(path_value)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Document file not found at {path}.")
    return FileResponse(path, media_type="application/pdf", filename=download_name)


@router.get("/{quotation_id}/letter")
def get_quotation_letter(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _document_response(quotation.pdf_path, f"quotation_{quotation_id}_letter.pdf")


@router.get("/{quotation_id}/annexure")
def get_quotation_annexure(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _document_response(quotation.annexure_pdf_path, f"quotation_{quotation_id}_annexure.pdf")


@router.post("/{quotation_id}/approve-and-send", response_model=QuotationOut)
def approve_and_send(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only a draft quotation can be approved and sent (current status: {quotation.status.value}).",
        )
    if not quotation.pdf_path:
        raise HTTPException(
            status_code=400,
            detail="This quotation has no generated PDF (likely outside the verified "
            "pricing range) -- it needs manual pricing before it can be sent.",
        )

    customer = quotation.enquiry.customer
    if customer is None or not customer.email:
        raise HTTPException(
            status_code=400,
            detail="The customer linked to this enquiry has no email address on file.",
        )

    try:
        send_quotation_email(
            to_email=customer.email,
            customer_name=customer.name,
            pdf_path=Path(quotation.pdf_path),
            annexure_pdf_path=Path(quotation.annexure_pdf_path) if quotation.annexure_pdf_path else None,
        )
    except RuntimeError as error:
        # Missing Postmark config or a failed send -- a real operational
        # problem, but a clear 503 with the reason beats an opaque 500.
        raise HTTPException(status_code=503, detail=str(error)) from error

    quotation.status = QuotationStatus.SENT
    quotation.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(quotation)
    return quotation


@router.post("/{quotation_id}/mark-sent-manually", response_model=QuotationOut)
def mark_sent_manually(
    quotation_id: int, payload: QuotationMarkSentManuallyNote, db: Session = Depends(get_db)
):
    """
    Review queue's escape hatch for when the business owner sends the
    quotation himself (custom email body, PDFs attached by hand) instead
    of using approve-and-send. Moves straight to SENT/sent_at like a real
    send so downstream won/lost/no_response follow-up works the same way,
    but never calls send_quotation_email -- sent_manually plus the
    required note is the only record that this didn't go through Postmark.
    """
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only a draft quotation can be marked as sent manually (current status: {quotation.status.value}).",
        )
    if not payload.note.strip():
        raise HTTPException(status_code=400, detail="A note is required to mark a quotation as sent manually.")

    quotation.status = QuotationStatus.SENT
    quotation.sent_at = datetime.now(timezone.utc)
    quotation.sent_manually = True
    quotation.notes = payload.note.strip()
    db.commit()
    db.refresh(quotation)
    return quotation


@router.post("/{quotation_id}/reject", response_model=QuotationOut)
def reject_quotation(quotation_id: int, db: Session = Depends(get_db)):
    """
    Review queue's "Reject" action -- a human deciding a draft should
    never go out, before it's ever sent. Distinct from the won/lost/
    no_response outcomes in QuotationStatusUpdate, which only apply
    after a quotation has actually been sent to the customer.

    Also moves the linked enquiry back to "new" -- rejecting a draft
    doesn't resolve the underlying enquiry, so it should stay available
    for a fresh generate-quotation attempt rather than sitting stuck as
    "quoted" for a quotation that will never be sent.
    """
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only a draft quotation can be rejected (current status: {quotation.status.value}).",
        )

    quotation.status = QuotationStatus.REJECTED
    quotation.enquiry.status = EnquiryStatus.NEW
    db.commit()
    db.refresh(quotation)
    return quotation


@router.post("/{quotation_id}/manual-pricing", response_model=QuotationOut)
def add_manual_pricing_note(
    quotation_id: int, payload: QuotationManualPricingNote, db: Session = Depends(get_db)
):
    """
    Review queue's "Price manually" action, for a draft whose capacity fell
    outside price_capacity()'s verified range. Records the reviewer's note
    and moves it out of the ordinary draft flow -- it never accepts or
    invents an actual price (see QuotationManualPricingNote's docstring).
    """
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only a draft quotation can be sent for manual pricing (current status: {quotation.status.value}).",
        )
    if quotation.in_verified_range:
        raise HTTPException(
            status_code=400,
            detail="This quotation already has a verified price -- manual pricing is only for "
            "quotations outside the verified pricing range.",
        )

    quotation.notes = payload.note
    quotation.status = QuotationStatus.NEEDS_MANUAL_PRICING
    db.commit()
    db.refresh(quotation)
    return quotation


@router.patch("/{quotation_id}/status", response_model=QuotationOut)
def update_quotation_status(
    quotation_id: int, payload: QuotationStatusUpdate, db: Session = Depends(get_db)
):
    quotation = db.get(Quotation, quotation_id)
    if quotation is None:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.SENT:
        raise HTTPException(
            status_code=400,
            detail=f"Only a sent quotation can be marked {payload.status} "
            f"(current status: {quotation.status.value}).",
        )

    quotation.status = QuotationStatus(payload.status)
    # Mirror the outcome onto the enquiry so the Enquiries page reflects it
    # (won -> closed_won; lost and no_response both read as closed_lost at
    # the enquiry level -- there's no separate "no reply" pill there, and
    # either way the enquiry didn't convert).
    quotation.enquiry.status = (
        EnquiryStatus.CLOSED_WON if quotation.status == QuotationStatus.WON else EnquiryStatus.CLOSED_LOST
    )
    db.commit()
    db.refresh(quotation)
    return quotation
