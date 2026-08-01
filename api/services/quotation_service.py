"""
Orchestrates the proven pricing_engine + documents modules into one
"generate a quotation for this enquiry" operation. This module contains
NO pricing or document-formatting logic of its own -- it only calls the
already-tested functions in pricing_engine/ and documents/ in sequence
and records the result, per CLAUDE.md's instruction not to modify or
duplicate that logic.

CORE NON-NEGOTIABLE HANDLED HERE:
If price_capacity() reports the capacity is outside the verified range,
this still creates a Quotation row (status "draft") so the enquiry shows
up in the review queue -- but with price_total=None and
in_verified_range=False, and no documents generated. Never silently
extrapolate, never skip the row, never hide the flag.
"""

import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from database.models import Enquiry, Quotation, QuotationStatus

# documents/generate_docx.py does `from number_to_words_indian import ...` as a
# bare same-directory import -- that only resolves automatically when the
# script is run directly (Python adds a script's own directory to sys.path).
# Imported as documents.generate_docx from elsewhere (this FastAPI app,
# pytest), it doesn't -- so we add the documents/ directory ourselves rather
# than editing that proven, already-tested module.
_DOCUMENTS_DIR = Path(__file__).resolve().parents[2] / "documents"
if str(_DOCUMENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_DOCUMENTS_DIR))

from documents.convert_to_pdf import convert_docx_to_pdf  # noqa: E402
from documents.generate_boq_annexure import generate_boq_docx  # noqa: E402
from documents.generate_docx import build_quotation_context, generate_quotation_docx  # noqa: E402
from pricing_engine.interpolate import load_tier_data, price_capacity  # noqa: E402

STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage" / "generated_quotations"


class QuotationGenerationError(Exception):
    """Raised for a caller-fixable problem (missing capacity/customer), not a bug."""


def generate_quotation(
    db: Session,
    enquiry: Enquiry,
    ref_no: str,
    completion_weeks_min: int,
    completion_weeks_max: int,
    attn_name: str | None = None,
) -> Quotation:
    if enquiry.capacity_cum_day is None:
        raise QuotationGenerationError(
            "This enquiry has no capacity_cum_day set. Fill it in (review queue "
            "-> needs_review) before generating a quotation."
        )
    if enquiry.customer is None:
        raise QuotationGenerationError(
            "This enquiry has no linked customer. Link a customer before "
            "generating a quotation -- the letter needs a name to address."
        )

    capacity = enquiry.capacity_cum_day
    pricing_result = price_capacity(capacity, load_tier_data())

    if not pricing_result.in_verified_range:
        quotation = Quotation(
            enquiry=enquiry,
            capacity_cum_day=capacity,
            price_total=None,
            in_verified_range=False,
            docx_path=None,
            pdf_path=None,
            annexure_docx_path=None,
            annexure_pdf_path=None,
            status=QuotationStatus.DRAFT,
        )
        db.add(quotation)
        db.commit()
        db.refresh(quotation)
        return quotation

    customer_name = enquiry.customer.name
    customer_contact = " ".join(
        part for part in (enquiry.customer.contact_title, enquiry.customer.contact_person) if part
    )
    resolved_attn_name = attn_name or customer_contact or customer_name

    context, pricing_result, _dimension_result = build_quotation_context(
        capacity=capacity,
        customer_name=customer_name,
        attn_name=resolved_attn_name,
        ref_no=ref_no,
        completion_weeks_min=completion_weeks_min,
        completion_weeks_max=completion_weeks_max,
    )

    base_name = f"enquiry_{enquiry.id}_{int(capacity)}_{uuid4().hex[:8]}"
    docx_path = STORAGE_DIR / f"{base_name}_quotation.docx"
    annexure_docx_path = STORAGE_DIR / f"{base_name}_annexure.docx"

    generate_quotation_docx(context, docx_path)
    generate_boq_docx(capacity=capacity, customer_name=customer_name, output_path=annexure_docx_path)

    pdf_path = convert_docx_to_pdf(docx_path)
    annexure_pdf_path = convert_docx_to_pdf(annexure_docx_path)

    quotation = Quotation(
        enquiry=enquiry,
        capacity_cum_day=capacity,
        price_total=pricing_result.total,
        in_verified_range=True,
        docx_path=str(docx_path),
        pdf_path=str(pdf_path),
        annexure_docx_path=str(annexure_docx_path),
        annexure_pdf_path=str(annexure_pdf_path),
        status=QuotationStatus.DRAFT,
    )
    db.add(quotation)
    db.commit()
    db.refresh(quotation)
    return quotation
