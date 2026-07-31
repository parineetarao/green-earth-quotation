"""
End-to-end tests for the FastAPI routes, against an in-memory sqlite
database (via dependency override on get_db) rather than the real
Supabase instance -- same reasoning as database/tests/test_models.py.

Claude extraction and Postmark sending are monkeypatched out: neither
needs a real network call to prove the *routing and status-transition*
logic is correct, and running them for real would require live API keys
in CI. The one deliberately NOT mocked is quotation generation for a
known real capacity (200 cum/day) -- that exercises the real
pricing_engine + documents pipeline (including a real LibreOffice
docx->pdf conversion) end-to-end, which is the whole point of Phase B.

Run with:
    pytest api/tests/test_api.py -v
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from database.models import Base  # noqa: E402
from database.session import get_db  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db: Session = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from api.main import app

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_enquiry_creates_customer_and_enquiry(client):
    response = client.post(
        "/enquiries",
        json={
            "customer_name": "Acme Textiles",
            "email": "ops@acme.example",
            "capacity_cum_day": 200,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["product_type"] == "STP"
    assert body["status"] == "new"
    assert body["source"] == "website_form"
    assert body["customer_id"] is not None


def test_create_enquiry_reuses_existing_customer_by_email(client):
    first = client.post(
        "/enquiries",
        json={"customer_name": "Green Valley Dyes", "email": "same@customer.example"},
    ).json()
    second = client.post(
        "/enquiries",
        json={"customer_name": "Green Valley Dyes Pvt Ltd", "email": "same@customer.example"},
    ).json()

    assert first["customer_id"] == second["customer_id"]
    assert len(client.get("/customers").json()) == 1


def test_get_customer_not_found(client):
    response = client.get("/customers/9999")
    assert response.status_code == 404


def test_list_enquiries_filters_by_status(client):
    # /enquiries (the website-form path) always creates status="new" --
    # needs_review only ever comes from the email extraction path, tested
    # separately below. This just confirms the status query filter itself
    # works and doesn't return enquiries of other statuses.
    first_id = client.post("/enquiries", json={"customer_name": "A", "capacity_cum_day": 100}).json()["id"]
    second_id = client.post("/enquiries", json={"customer_name": "B", "capacity_cum_day": 150}).json()["id"]

    all_new = client.get("/enquiries", params={"status": "new"}).json()
    assert all(e["status"] == "new" for e in all_new)
    ids = {e["id"] for e in all_new}
    assert {first_id, second_id} <= ids

    assert client.get("/enquiries", params={"status": "needs_review"}).json() == []


def test_from_email_needs_review_when_capacity_missing(client, monkeypatch):
    from api.schemas import ExtractedEnquiryFields

    def fake_extract(raw_message: str) -> ExtractedEnquiryFields:
        return ExtractedEnquiryFields(
            capacity_cum_day=None,
            product_type=None,
            location=None,
            customer_name=None,
            confidence="low",
        )

    monkeypatch.setattr("api.routes.enquiries.extract_enquiry_fields", fake_extract)

    response = client.post(
        "/enquiries/from-email",
        json={
            "FromFull": {"Email": "vague@customer.example", "Name": "Vague Customer"},
            "Subject": "Need a plant",
            "TextBody": "Hi, we need something for our factory.",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "needs_review"


def test_from_email_new_when_high_confidence(client, monkeypatch):
    from api.schemas import ExtractedEnquiryFields

    def fake_extract(raw_message: str) -> ExtractedEnquiryFields:
        return ExtractedEnquiryFields(
            capacity_cum_day=200,
            product_type="STP",
            location="Pune",
            customer_name="Clear Corp",
            confidence="high",
        )

    monkeypatch.setattr("api.routes.enquiries.extract_enquiry_fields", fake_extract)

    response = client.post(
        "/enquiries/from-email",
        json={
            "FromFull": {"Email": "clear@customer.example", "Name": "Clear Corp"},
            "Subject": "STP for 200 cum/day",
            "TextBody": "We need a 200 cum/day STP plant at our Pune facility.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "new"
    assert body["capacity_cum_day"] == 200


def test_generate_quotation_out_of_verified_range(client):
    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "Out Of Range Co", "capacity_cum_day": 1000},
    ).json()

    response = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/001", "completion_weeks_min": 8, "completion_weeks_max": 10},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["in_verified_range"] is False
    assert body["price_total"] is None
    assert body["docx_path"] is None
    assert body["status"] == "draft"


def test_generate_quotation_without_customer_id_fails(client):
    # capacity_cum_day missing entirely -> generate_quotation should refuse
    enquiry = client.post(
        "/enquiries", json={"customer_name": "No Capacity Co", "capacity_cum_day": None}
    ).json()

    response = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/002", "completion_weeks_min": 8, "completion_weeks_max": 10},
    )
    assert response.status_code == 400


def test_generate_quotation_real_pipeline_for_known_tier(client):
    """
    The one test that runs the REAL pricing_engine + documents pipeline
    (including a real LibreOffice conversion) for a capacity with a known
    real total, per pricing_engine/tests/test_interpolate.py.
    """
    enquiry = client.post(
        "/enquiries",
        json={
            "customer_name": "Real Pipeline Test Co",
            "contact_person": "Rajesh Sharma",
            "capacity_cum_day": 200,
        },
    ).json()

    response = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={
            "ref_no": "GEEC/TEST/001",
            "completion_weeks_min": 8,
            "completion_weeks_max": 10,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["in_verified_range"] is True
    assert body["price_total"] == 2144680
    assert body["docx_path"] and Path(body["docx_path"]).exists()
    assert body["pdf_path"] and Path(body["pdf_path"]).exists()
    assert body["annexure_docx_path"] and Path(body["annexure_docx_path"]).exists()
    assert body["annexure_pdf_path"] and Path(body["annexure_pdf_path"]).exists()

    # The review queue must be able to fetch the actual PDFs before a human
    # approves/sends -- reviewing the real document is the point of the queue.
    letter_response = client.get(f"/quotations/{body['id']}/letter")
    assert letter_response.status_code == 200
    assert letter_response.headers["content-type"] == "application/pdf"
    assert letter_response.content == Path(body["pdf_path"]).read_bytes()

    annexure_response = client.get(f"/quotations/{body['id']}/annexure")
    assert annexure_response.status_code == 200
    assert annexure_response.headers["content-type"] == "application/pdf"
    assert annexure_response.content == Path(body["annexure_pdf_path"]).read_bytes()

    # cleanup the generated files so repeated test runs don't pile up storage
    for key in ("docx_path", "pdf_path", "annexure_docx_path", "annexure_pdf_path"):
        Path(body[key]).unlink(missing_ok=True)

    enquiry_after = client.get("/enquiries").json()
    matching = [e for e in enquiry_after if e["id"] == enquiry["id"]]
    assert matching[0]["status"] == "quoted"


def test_quotation_documents_404_when_out_of_verified_range(client):
    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "No Document Co", "capacity_cum_day": 1000},
    ).json()
    quotation = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/010", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()
    assert quotation["in_verified_range"] is False

    assert client.get(f"/quotations/{quotation['id']}/letter").status_code == 404
    assert client.get(f"/quotations/{quotation['id']}/annexure").status_code == 404


def test_quotation_documents_404_for_unknown_quotation(client):
    assert client.get("/quotations/999999/letter").status_code == 404
    assert client.get("/quotations/999999/annexure").status_code == 404


def test_approve_and_send_requires_draft_status(client, monkeypatch):
    monkeypatch.setattr("api.routes.quotations.send_quotation_email", lambda **kwargs: None)

    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "Never Priced Co", "email": "x@y.example", "capacity_cum_day": 1000},
    ).json()
    quotation = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/003", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()

    # Out-of-range quotation has no PDF -- approve-and-send must refuse.
    response = client.post(f"/quotations/{quotation['id']}/approve-and-send")
    assert response.status_code == 400


def test_patch_status_requires_sent(client):
    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "Draft Only Co", "capacity_cum_day": 1000},
    ).json()
    quotation = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/004", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()

    response = client.patch(f"/quotations/{quotation['id']}/status", json={"status": "won"})
    assert response.status_code == 400


def test_reject_quotation_sends_enquiry_back_to_new(client):
    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "Reject Test Co", "capacity_cum_day": 200},
    ).json()
    quotation = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/005", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()
    assert client.get("/enquiries").json()[0]["status"] == "quoted"

    response = client.post(f"/quotations/{quotation['id']}/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    matching = [e for e in client.get("/enquiries").json() if e["id"] == enquiry["id"]]
    assert matching[0]["status"] == "new"

    # cleanup generated files
    for key in ("docx_path", "pdf_path", "annexure_docx_path", "annexure_pdf_path"):
        path = quotation.get(key)
        if path:
            Path(path).unlink(missing_ok=True)

    # a rejected quotation can't be rejected again
    assert client.post(f"/quotations/{quotation['id']}/reject").status_code == 400


def test_manual_pricing_note_for_out_of_range_quotation(client):
    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "Manual Pricing Co", "capacity_cum_day": 1000},
    ).json()
    quotation = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/006", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()
    assert quotation["in_verified_range"] is False
    assert client.get("/enquiries").json()[0]["status"] == "needs_review"

    response = client.post(
        f"/quotations/{quotation['id']}/manual-pricing",
        json={"note": "Sent to the civil team for a custom estimate."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_manual_pricing"
    assert body["notes"] == "Sent to the civil team for a custom estimate."


def test_manual_pricing_rejected_for_already_verified_quotation(client):
    enquiry = client.post(
        "/enquiries",
        json={"customer_name": "Already Priced Co", "capacity_cum_day": 200},
    ).json()
    quotation = client.post(
        f"/enquiries/{enquiry['id']}/generate-quotation",
        json={"ref_no": "TEST/007", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()

    response = client.post(
        f"/quotations/{quotation['id']}/manual-pricing", json={"note": "Shouldn't be allowed."}
    )
    assert response.status_code == 400

    for key in ("docx_path", "pdf_path", "annexure_docx_path", "annexure_pdf_path"):
        path = quotation.get(key)
        if path:
            Path(path).unlink(missing_ok=True)


def test_complete_enquiry_fills_gaps_and_returns_to_new(client, monkeypatch):
    from api.schemas import ExtractedEnquiryFields

    def fake_extract(raw_message: str) -> ExtractedEnquiryFields:
        return ExtractedEnquiryFields(
            capacity_cum_day=None,
            product_type=None,
            location=None,
            customer_name=None,
            confidence="low",
        )

    monkeypatch.setattr("api.routes.enquiries.extract_enquiry_fields", fake_extract)

    enquiry = client.post(
        "/enquiries/from-email",
        json={
            "FromFull": {"Email": "unclear@customer.example", "Name": ""},
            "Subject": "STP enquiry",
            "TextBody": "hi we might need something, not sure of size yet",
        },
    ).json()
    assert enquiry["status"] == "needs_review"

    response = client.patch(
        f"/enquiries/{enquiry['id']}/complete",
        json={
            "customer_name": "Filled In By Hand Co",
            "email": "unclear@customer.example",
            "capacity_cum_day": 300,
            "requirement_details": "Needs an STP for a new bottling plant.",
            "expected_timeline": "Within 3 months",
            "budget_range": "20,00,000 - 30,00,000",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "new"
    assert body["capacity_cum_day"] == 300
    assert body["requirement_details"] == "Needs an STP for a new bottling plant."
    assert body["customer_id"] is not None


def test_quotation_won_and_lost_mirror_onto_enquiry(client, monkeypatch):
    monkeypatch.setattr("api.routes.quotations.send_quotation_email", lambda **kwargs: None)

    # Won case
    enquiry_won = client.post(
        "/enquiries",
        json={"customer_name": "Winner Co", "email": "winner@example.com", "capacity_cum_day": 200},
    ).json()
    quotation_won = client.post(
        f"/enquiries/{enquiry_won['id']}/generate-quotation",
        json={"ref_no": "TEST/008", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()
    client.post(f"/quotations/{quotation_won['id']}/approve-and-send")
    client.patch(f"/quotations/{quotation_won['id']}/status", json={"status": "won"})

    matching = [e for e in client.get("/enquiries").json() if e["id"] == enquiry_won["id"]]
    assert matching[0]["status"] == "closed_won"

    # Lost case
    enquiry_lost = client.post(
        "/enquiries",
        json={"customer_name": "Loser Co", "email": "loser@example.com", "capacity_cum_day": 200},
    ).json()
    quotation_lost = client.post(
        f"/enquiries/{enquiry_lost['id']}/generate-quotation",
        json={"ref_no": "TEST/009", "completion_weeks_min": 8, "completion_weeks_max": 10},
    ).json()
    client.post(f"/quotations/{quotation_lost['id']}/approve-and-send")
    client.patch(f"/quotations/{quotation_lost['id']}/status", json={"status": "lost"})

    matching = [e for e in client.get("/enquiries").json() if e["id"] == enquiry_lost["id"]]
    assert matching[0]["status"] == "closed_lost"

    for quotation in (quotation_won, quotation_lost):
        for key in ("docx_path", "pdf_path", "annexure_docx_path", "annexure_pdf_path"):
            path = quotation.get(key)
            if path:
                Path(path).unlink(missing_ok=True)
