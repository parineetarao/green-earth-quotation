"""
Proves the Phase A schema behaves correctly BEFORE anything in Phase B
(the FastAPI routes) is built on top of it.

Runs against an in-memory sqlite database, not the real Supabase
Postgres instance -- these tests only need to prove the table
definitions, relationships, defaults, and constraints are correct, which
sqlite can do without any real credentials or network access. That's why
this imports database.models directly instead of database.session (which
requires a real DATABASE_URL and would fail these tests immediately).

Run with:
    pytest database/tests/test_models.py -v
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Make the `database` package importable when running pytest from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from database.models import (  # noqa: E402
    Base,
    Customer,
    Enquiry,
    EnquirySource,
    EnquiryStatus,
    ProductType,
    Quotation,
    QuotationStatus,
)


@pytest.fixture()
def session():
    """Fresh in-memory sqlite database, tables created, per test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_customer_created_with_only_required_fields(session):
    """name is the only required field -- everything else can be filled in later."""
    customer = Customer(name="Acme Textiles")
    session.add(customer)
    session.commit()

    assert customer.id is not None
    assert customer.created_at is not None
    assert customer.contact_person is None
    assert customer.email is None


def test_enquiry_defaults_to_stp_and_new_status(session):
    """product_type and status should default without the caller specifying them."""
    enquiry = Enquiry(source=EnquirySource.WEBSITE_FORM, capacity_cum_day=200)
    session.add(enquiry)
    session.commit()

    assert enquiry.product_type == ProductType.STP
    assert enquiry.status == EnquiryStatus.NEW
    assert enquiry.customer_id is None  # no customer linked yet is a valid state


def test_enquiry_can_exist_without_a_linked_customer(session):
    """
    Mirrors the real needs_review case: an inbound email where Claude's
    extraction couldn't confidently identify the customer. The enquiry
    still needs to land in the queue for a human to fill in by hand.
    """
    enquiry = Enquiry(
        source=EnquirySource.EMAIL,
        raw_message="Hi, we need a plant for our factory, no other details given.",
        status=EnquiryStatus.NEEDS_REVIEW,
    )
    session.add(enquiry)
    session.commit()

    assert enquiry.customer_id is None
    assert enquiry.status == EnquiryStatus.NEEDS_REVIEW


def test_customer_to_enquiry_to_quotation_relationship_roundtrip(session):
    """The chain a Streamlit page needs: customer -> their enquiries -> each enquiry's quotations."""
    customer = Customer(name="Green Valley Dyes", email="ops@greenvalley.example")
    enquiry = Enquiry(
        customer=customer,
        source=EnquirySource.MANUAL,
        capacity_cum_day=275,
        status=EnquiryStatus.QUOTED,
    )
    quotation = Quotation(
        enquiry=enquiry,
        capacity_cum_day=275,
        price_total=2483790.0,
        in_verified_range=True,
        docx_path="storage/generated_quotations/q1.docx",
        pdf_path="storage/generated_quotations/q1.pdf",
        annexure_docx_path="storage/generated_quotations/q1_annexure.docx",
        annexure_pdf_path="storage/generated_quotations/q1_annexure.pdf",
    )
    session.add_all([customer, enquiry, quotation])
    session.commit()

    session.expire_all()
    fetched_customer = session.get(Customer, customer.id)
    assert len(fetched_customer.enquiries) == 1
    assert len(fetched_customer.enquiries[0].quotations) == 1
    fetched_quotation = fetched_customer.enquiries[0].quotations[0]
    assert fetched_quotation.enquiry_id == enquiry.id
    assert fetched_quotation.annexure_pdf_path == "storage/generated_quotations/q1_annexure.pdf"


def test_quotation_defaults_to_draft_status(session):
    enquiry = Enquiry(source=EnquirySource.WEBSITE_FORM, capacity_cum_day=100)
    quotation = Quotation(enquiry=enquiry, capacity_cum_day=100, in_verified_range=True)
    session.add_all([enquiry, quotation])
    session.commit()

    assert quotation.status == QuotationStatus.DRAFT
    assert quotation.sent_at is None


def test_quotation_out_of_verified_range_allows_null_price():
    """
    Core non-negotiable from CLAUDE.md: price_capacity() returning
    in_verified_range=False must be representable without fabricating a
    price_total. This should not raise or silently coerce to 0.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        enquiry = Enquiry(source=EnquirySource.EMAIL, capacity_cum_day=1000)
        quotation = Quotation(
            enquiry=enquiry,
            capacity_cum_day=1000,
            price_total=None,
            in_verified_range=False,
        )
        session.add_all([enquiry, quotation])
        session.commit()

        assert quotation.price_total is None
        assert quotation.in_verified_range is False


def test_invalid_enquiry_status_rejected_at_db_level(session):
    """
    Going through the ORM (or even SQLAlchemy Core) would validate the
    enum in Python before the value ever reaches the database, so that
    only proves our own code checks itself. Insert via raw literal SQL
    instead -- bypassing SQLAlchemy's type layer entirely -- to prove the
    CHECK constraint baked into the table itself rejects an out-of-set
    value, the same way it would if something other than this codebase
    (a psql session, a different service) tried to write bad data.
    """
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO enquiries (source, product_type, status) "
                "VALUES ('email', 'STP', 'not_a_real_status')"
            )
        )
        session.commit()


def test_sent_at_is_set_only_when_a_quotation_is_actually_sent(session):
    enquiry = Enquiry(source=EnquirySource.WEBSITE_FORM, capacity_cum_day=150)
    quotation = Quotation(enquiry=enquiry, capacity_cum_day=150, in_verified_range=True)
    session.add_all([enquiry, quotation])
    session.commit()
    assert quotation.sent_at is None

    quotation.status = QuotationStatus.SENT
    quotation.sent_at = datetime.now(timezone.utc)
    session.commit()

    session.refresh(quotation)
    assert quotation.status == QuotationStatus.SENT
    assert quotation.sent_at is not None
