"""
Pydantic request/response models for the FastAPI layer.

These are deliberately separate from the SQLAlchemy models in
database/models.py: the DB models describe what's stored, these describe
what crosses the wire. Keeping them separate means a column can be added
to the DB (e.g. for internal bookkeeping) without automatically exposing
it to API callers, and vice versa.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_person: str | None
    contact_title: str | None
    phone: str | None
    email: str | None
    industry: str | None
    location: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------


class EnquiryCreate(BaseModel):
    """
    Body for POST /enquiries -- the website's Request-a-Quote form posts
    structured fields directly, so there's no free-text extraction step
    for this source (that's only needed for the email intake path, where
    the enquiry arrives as an unstructured message).

    source defaults to "website_form" since that's this endpoint's actual
    caller today, but stays overridable so a later manual-entry screen in
    the dashboard can reuse this same endpoint with source="manual"
    instead of needing a new one.
    """

    customer_name: str
    contact_person: str | None = None
    contact_title: str | None = None
    email: str | None = None
    phone: str | None = None
    industry: str | None = None
    location: str | None = None
    capacity_cum_day: float | None = None
    raw_message: str | None = None
    requirement_details: str | None = None
    source: Literal["website_form", "manual"] = "website_form"


class EnquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int | None
    source: str
    product_type: str
    capacity_cum_day: float | None
    raw_message: str | None
    requirement_details: str | None
    expected_timeline: str | None
    budget_range: str | None
    status: str
    created_at: datetime


class EnquiryComplete(BaseModel):
    """
    Body for PATCH /enquiries/{id}/complete -- the review queue's "Complete"
    form for a needs_review enquiry (Gemini extraction couldn't confidently
    fill these in, so a human does). customer_name is required so a human
    can attach a customer to an enquiry that arrived with none (see
    database/models.py's note on why customer_id is nullable); the other
    identity fields stay optional the same way EnquiryCreate's do.
    Completing sets status back to "new" -- the enquiry now has everything
    generate-quotation needs, but no quotation has been generated yet, so
    jumping straight to "quoted" would be premature.
    """

    customer_name: str
    contact_person: str | None = None
    contact_title: str | None = None
    email: str | None = None
    phone: str | None = None
    industry: str | None = None
    location: str | None = None
    capacity_cum_day: float
    requirement_details: str | None = None
    expected_timeline: str | None = None
    budget_range: str | None = None


class GenerateQuotationRequest(BaseModel):
    """
    Body for POST /enquiries/{id}/generate-quotation.

    ref_no and the completion-week estimates are deliberately required,
    not defaulted -- documents/generate_docx.py's own docstring flags
    ref_no as "a placeholder that must be supplied per-quotation by the
    reviewing human, there is no single correct default", and the same
    is true of a completion-time promise that ends up on a real
    customer-facing letter. The API should not invent either.
    """

    ref_no: str
    completion_weeks_min: int
    completion_weeks_max: int
    attn_name: str | None = None


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enquiry_id: int
    capacity_cum_day: float
    price_total: float | None
    in_verified_range: bool
    docx_path: str | None
    pdf_path: str | None
    annexure_docx_path: str | None
    annexure_pdf_path: str | None
    notes: str | None
    status: str
    created_at: datetime
    sent_at: datetime | None
    sent_manually: bool


class QuotationStatusUpdate(BaseModel):
    """
    PATCH /quotations/{id}/status -- deliberately excludes "draft" and
    "sent" from the allowed values. Draft is the row's initial state, and
    "sent" only happens through /approve-and-send (the one endpoint
    allowed to actually email a customer), never through this generic
    status edit.
    """

    status: Literal["won", "lost", "no_response"]


class QuotationManualPricingNote(BaseModel):
    """
    Body for POST /quotations/{id}/manual-pricing -- the review queue's
    "Price manually" action for a draft whose capacity was outside
    price_capacity()'s verified range (in_verified_range=False, no
    fabricated price -- see pricing_engine/interpolate.py). This only
    records a reviewer's note and moves the row to needs_manual_pricing;
    it deliberately does not accept a price, since inventing one here
    would be the exact fabrication CLAUDE.md's non-negotiables forbid.
    """

    note: str


class QuotationMarkSentManuallyNote(BaseModel):
    """
    Body for POST /quotations/{id}/mark-sent-manually -- the review queue's
    escape hatch for when the business owner sends the quotation himself
    (custom email body, PDFs attached by hand) instead of using approve-
    and-send. note is required, not optional: since this path never goes
    through Postmark, the note is the only record of what actually
    happened and why (e.g. "sent manually on 2026-08-01, confirmed by
    phone").
    """

    note: str


# ---------------------------------------------------------------------------
# Claude email-extraction output (used by api/services/email_extraction.py)
# ---------------------------------------------------------------------------


class ExtractedEnquiryFields(BaseModel):
    """
    Strict-JSON shape Claude is asked to return when parsing a free-text
    inbound email. Mirrors the fields CLAUDE.md specifies exactly.
    """

    capacity_cum_day: float | None
    product_type: str | None
    location: str | None
    customer_name: str | None
    confidence: Literal["high", "low"]
