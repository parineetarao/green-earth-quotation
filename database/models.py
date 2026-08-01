"""
Phase A -- the three core tables: customers, enquiries, quotations.

WHY STR ENUMS + native_enum=False:
Several columns below (source, product_type, status) only make sense as
one of a small fixed set of values -- CLAUDE.md spells these out exactly,
e.g. product_type is currently only "STP". Using SQLAlchemy's Enum type
with native_enum=False stores the value as a plain VARCHAR with a CHECK
constraint, instead of creating a Postgres-native enum type. A native
Postgres enum makes adding a new value (e.g. "ETP" later) an awkward
ALTER TYPE ... ADD VALUE operation with its own transaction quirks. A
CHECK constraint on a VARCHAR is a plain ALTER TABLE to update, which
matches the CLAUDE.md instruction to make ETP addable later without a
rebuild.

values_callable is required on every one of these Enum() columns:
SQLAlchemy's default behaviour for a Python Enum is to store/check the
member's NAME ("WEBSITE_FORM"), not its value ("website_form"). Without
values_callable, the database would enforce the wrong strings -- ones
that don't match what CLAUDE.md specifies and what the API/dashboard
will actually send.

WHY customer_id ON enquiries IS NULLABLE:
An enquiry can arrive from an inbound email where Claude's extraction
step could not confidently identify who the customer is (that's exactly
what status="needs_review" is for). The row still needs to exist so a
human can open it in the review queue and fill in the customer by hand --
it just doesn't have a customer linked yet at creation time.

WHY annexure_docx_path / annexure_pdf_path EXIST BEYOND THE CLAUDE.md LIST:
The real company documents never embed the BOQ price table inside the
quotation letter -- documents/generate_boq_annexure.py produces it as a
genuinely separate file (Annexure IV). docx_path/pdf_path point at the
letter; these two columns point at that second document, mirroring the
same pattern rather than overloading the letter's path columns.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EnquirySource(str, enum.Enum):
    WEBSITE_FORM = "website_form"
    EMAIL = "email"
    MANUAL = "manual"


class ProductType(str, enum.Enum):
    STP = "STP"
    # ETP intentionally not added -- no real pricing/template data exists
    # yet. Add it here (and nowhere else in this file) once the business
    # owner provides real ETP source data.


class EnquiryStatus(str, enum.Enum):
    NEW = "new"
    NEEDS_REVIEW = "needs_review"
    # QUOTED/CLOSED_WON/CLOSED_LOST replace the original PROCESSED value --
    # added for the Phase C dashboard's Enquiries page, which needs to show
    # an enquiry's outcome (quoted / won / lost), not just "a quotation
    # exists for this". Set by api/routes/enquiries.py once
    # generate-quotation succeeds (QUOTED, or back to NEEDS_REVIEW if the
    # capacity was outside the verified pricing range -- see
    # quotation_service.py), and mirrored from the linked quotation's own
    # status by api/routes/quotations.py when that quotation is
    # rejected/won/lost/no_response.
    QUOTED = "quoted"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class QuotationStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    WON = "won"
    LOST = "lost"
    NO_RESPONSE = "no_response"
    # Added for the Phase C review queue dashboard, not in the original
    # CLAUDE.md list. REJECTED covers a human rejecting a draft before it's
    # ever sent (distinct from LOST, which is a sent quotation the customer
    # turned down). NEEDS_MANUAL_PRICING covers a draft whose capacity was
    # outside price_capacity()'s verified range -- see quotation_service.py,
    # which already refuses to fabricate a price for these -- so a reviewer
    # can attach a note while pricing is worked out by hand, without the row
    # pretending to still be an untouched draft.
    REJECTED = "rejected"
    NEEDS_MANUAL_PRICING = "needs_manual_pricing"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(Text)
    # Salutation for contact_person (Mr/Ms/Mrs/Dr), kept separate rather than
    # baked into contact_person -- letting a human pick it explicitly avoids
    # the template/generator ever guessing a title from a name. None/"" means
    # no title was selected.
    contact_title: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    enquiries: Mapped[list["Enquiry"]] = relationship(back_populates="customer")


class Enquiry(Base):
    __tablename__ = "enquiries"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    source: Mapped[EnquirySource] = mapped_column(
        Enum(
            EnquirySource,
            name="enquiry_source",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    product_type: Mapped[ProductType] = mapped_column(
        Enum(
            ProductType,
            name="product_type",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProductType.STP,
    )
    capacity_cum_day: Mapped[float | None] = mapped_column(Float)
    raw_message: Mapped[str | None] = mapped_column(Text)
    # Added for the Phase C "Complete" form on needs_review enquiries --
    # fields a human fills in by hand when Gemini's extraction couldn't
    # determine them from the raw email text. Nullable/free text: these are
    # notes for a human reviewer, not structured data anything else parses.
    requirement_details: Mapped[str | None] = mapped_column(Text)
    expected_timeline: Mapped[str | None] = mapped_column(Text)
    budget_range: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EnquiryStatus] = mapped_column(
        Enum(
            EnquiryStatus,
            name="enquiry_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EnquiryStatus.NEW,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    customer: Mapped["Customer | None"] = relationship(back_populates="enquiries")
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="enquiry")


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    enquiry_id: Mapped[int] = mapped_column(ForeignKey("enquiries.id"), nullable=False)
    capacity_cum_day: Mapped[float] = mapped_column(Float, nullable=False)
    price_total: Mapped[float | None] = mapped_column(Float)
    in_verified_range: Mapped[bool] = mapped_column(nullable=False)
    docx_path: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    annexure_docx_path: Mapped[str | None] = mapped_column(Text)
    annexure_pdf_path: Mapped[str | None] = mapped_column(Text)
    # Added for the Phase C review queue's "Price manually" action -- a
    # free-text note a human attaches when the capacity fell outside
    # price_capacity()'s verified range (see NEEDS_MANUAL_PRICING above).
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[QuotationStatus] = mapped_column(
        Enum(
            QuotationStatus,
            name="quotation_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=QuotationStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Added for the review queue's "Mark as sent manually" action -- the
    # business owner sometimes sends the quotation himself (custom email
    # body, PDFs attached by hand) instead of using approve-and-send. That
    # action reuses status=SENT/sent_at so the rest of the system (won/lost
    # follow-up, dashboards) treats it identically to a Postmark send, but
    # sent_manually distinguishes the two so the review queue can show how
    # it actually went out, and no email is ever sent through Postmark for
    # this path. `notes` holds the required explanation (e.g. "sent
    # manually on 2026-08-01, confirmed by phone").
    sent_manually: Mapped[bool] = mapped_column(nullable=False, default=False)

    enquiry: Mapped["Enquiry"] = relationship(back_populates="quotations")
