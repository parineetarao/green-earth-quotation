"""
POST /enquiries, POST /enquiries/from-email, POST /enquiries/{id}/generate-quotation,
GET /enquiries.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import (
    EnquiryComplete,
    EnquiryCreate,
    EnquiryOut,
    GenerateQuotationRequest,
    QuotationOut,
)
from api.services.email_extraction import extract_enquiry_fields
from api.services.quotation_service import QuotationGenerationError, generate_quotation
from database.models import Customer, Enquiry, EnquiryStatus, ProductType
from database.session import get_db
from intake.email_webhook import PostmarkInboundPayload, parse_inbound_email

router = APIRouter(prefix="/enquiries", tags=["enquiries"])


def _find_or_create_customer(
    db: Session,
    *,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    contact_person: str | None = None,
    industry: str | None = None,
    location: str | None = None,
) -> Customer:
    """
    Matches an existing customer by email first (the more reliable
    identifier), falling back to an exact name match, before creating a
    new row. This is deliberately simple fuzzy-free matching -- getting
    this wrong means two customer rows for the same real company, which
    a human can merge later; getting clever here risks merging two
    different companies into one.
    """
    existing = None
    if email:
        existing = db.execute(
            select(Customer).where(func.lower(Customer.email) == email.lower())
        ).scalar_one_or_none()
    if existing is None:
        existing = db.execute(
            select(Customer).where(func.lower(Customer.name) == name.lower())
        ).scalar_one_or_none()
    if existing is not None:
        return existing

    customer = Customer(
        name=name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        industry=industry,
        location=location,
    )
    db.add(customer)
    db.flush()  # assigns customer.id without committing yet
    return customer


@router.post("", response_model=EnquiryOut, status_code=201)
def create_enquiry(payload: EnquiryCreate, db: Session = Depends(get_db)):
    customer = _find_or_create_customer(
        db,
        name=payload.customer_name,
        email=payload.email,
        phone=payload.phone,
        contact_person=payload.contact_person,
        industry=payload.industry,
        location=payload.location,
    )

    enquiry = Enquiry(
        customer=customer,
        source=payload.source,
        product_type=ProductType.STP,
        capacity_cum_day=payload.capacity_cum_day,
        raw_message=payload.raw_message,
        status=EnquiryStatus.NEW,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)
    return enquiry


@router.post("/from-email", response_model=EnquiryOut, status_code=201)
def create_enquiry_from_email(payload: PostmarkInboundPayload, db: Session = Depends(get_db)):
    parsed = parse_inbound_email(payload)
    extracted = extract_enquiry_fields(parsed.raw_message)

    # Never auto-proceed past "needs_review" if capacity is missing, the
    # extraction wasn't confident, or the enquiry isn't actually for an
    # STP (the only product_type this system currently prices/quotes).
    is_stp = extracted.product_type is None or extracted.product_type.strip().upper() == "STP"
    needs_review = (
        extracted.capacity_cum_day is None
        or extracted.confidence == "low"
        or not is_stp
    )

    customer = _find_or_create_customer(
        db,
        name=extracted.customer_name or parsed.sender_name,
        email=parsed.sender_email,
    )

    enquiry = Enquiry(
        customer=customer,
        source="email",
        product_type=ProductType.STP,
        capacity_cum_day=extracted.capacity_cum_day,
        raw_message=parsed.raw_message,
        status=EnquiryStatus.NEEDS_REVIEW if needs_review else EnquiryStatus.NEW,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)
    return enquiry


@router.post("/{enquiry_id}/generate-quotation", response_model=QuotationOut, status_code=201)
def generate_quotation_for_enquiry(
    enquiry_id: int, payload: GenerateQuotationRequest, db: Session = Depends(get_db)
):
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    try:
        quotation = generate_quotation(
            db,
            enquiry,
            ref_no=payload.ref_no,
            completion_weeks_min=payload.completion_weeks_min,
            completion_weeks_max=payload.completion_weeks_max,
            attn_name=payload.attn_name,
        )
    except QuotationGenerationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    # A generated quotation always means "quoted" from the enquiry's point of
    # view UNLESS price_capacity() couldn't verify the capacity (see
    # quotation_service.py) -- in that case the quotation sits in
    # needs_manual_pricing/draft limbo, so the enquiry stays needs_review
    # rather than claiming to be quoted before it actually has a usable price.
    enquiry.status = (
        EnquiryStatus.QUOTED if quotation.in_verified_range else EnquiryStatus.NEEDS_REVIEW
    )
    db.commit()
    db.refresh(quotation)
    return quotation


@router.patch("/{enquiry_id}/complete", response_model=EnquiryOut)
def complete_enquiry(enquiry_id: int, payload: EnquiryComplete, db: Session = Depends(get_db)):
    """
    Enquiries page's "Complete" form for a needs_review row -- fills in by
    hand what Gemini's extraction couldn't confidently determine (see
    EnquiryComplete's docstring). Moves status back to "new": the enquiry
    now has everything generate-quotation needs, but no quotation has been
    generated yet, so "quoted" would be premature.
    """
    enquiry = db.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    customer = _find_or_create_customer(
        db,
        name=payload.customer_name,
        email=payload.email,
        phone=payload.phone,
        contact_person=payload.contact_person,
        industry=payload.industry,
        location=payload.location,
    )

    enquiry.customer = customer
    enquiry.capacity_cum_day = payload.capacity_cum_day
    enquiry.requirement_details = payload.requirement_details
    enquiry.expected_timeline = payload.expected_timeline
    enquiry.budget_range = payload.budget_range
    enquiry.status = EnquiryStatus.NEW
    db.commit()
    db.refresh(enquiry)
    return enquiry


@router.get("", response_model=list[EnquiryOut])
def list_enquiries(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Enquiry).order_by(Enquiry.created_at.desc())
    if status:
        stmt = stmt.where(Enquiry.status == status)
    return db.execute(stmt).scalars().all()
