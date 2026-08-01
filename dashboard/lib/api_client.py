"""
Thin HTTP client for the FastAPI backend (api/main.py) -- every dashboard
page goes through here rather than touching the database directly, so the
dashboard only ever sees what the API is willing to expose (see
api/schemas.py's note on why the wire schemas are kept separate from the
DB models).

API_BASE_URL points at a locally running `uvicorn api.main:app` during
development; Phase D deployment repoints it at the hosted API instead.
"""

import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
_TIMEOUT = 15


class APIError(Exception):
    """Raised for anything -- network failure or a non-2xx response -- a page should st.error() and stop."""


def _request(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_BASE_URL}{path}", timeout=_TIMEOUT, **kwargs)
    except requests.exceptions.RequestException as error:
        raise APIError(
            f"Couldn't reach the API at {API_BASE_URL} ({error.__class__.__name__}). "
            "Is the FastAPI server running?"
        ) from error

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise APIError(f"{response.status_code}: {detail}")

    if response.status_code == 204 or not response.content:
        return None
    return response.json()


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=10, show_spinner=False)
def list_customers(search: str | None = None) -> list[dict]:
    params = {"search": search} if search else {}
    return _request("GET", "/customers", params=params)


def get_customer(customer_id: int) -> dict:
    return _request("GET", f"/customers/{customer_id}")


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------


@st.cache_data(ttl=10, show_spinner=False)
def list_enquiries(status: str | None = None) -> list[dict]:
    params = {"status": status} if status else {}
    return _request("GET", "/enquiries", params=params)


def create_enquiry(payload: dict) -> dict:
    result = _request("POST", "/enquiries", json=payload)
    list_enquiries.clear()
    list_customers.clear()
    return result


def generate_quotation(
    enquiry_id: int,
    ref_no: str,
    completion_weeks_min: int,
    completion_weeks_max: int,
    attn_name: str | None = None,
) -> dict:
    result = _request(
        "POST",
        f"/enquiries/{enquiry_id}/generate-quotation",
        json={
            "ref_no": ref_no,
            "completion_weeks_min": completion_weeks_min,
            "completion_weeks_max": completion_weeks_max,
            "attn_name": attn_name,
        },
    )
    list_enquiries.clear()
    list_quotations.clear()
    return result


def complete_enquiry(enquiry_id: int, payload: dict) -> dict:
    result = _request("PATCH", f"/enquiries/{enquiry_id}/complete", json=payload)
    list_enquiries.clear()
    list_customers.clear()
    return result


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------


@st.cache_data(ttl=10, show_spinner=False)
def list_quotations(status: str | None = None) -> list[dict]:
    params = {"status": status} if status else {}
    return _request("GET", "/quotations", params=params)


def approve_and_send(quotation_id: int) -> dict:
    result = _request("POST", f"/quotations/{quotation_id}/approve-and-send")
    list_quotations.clear()
    list_enquiries.clear()
    return result


def reject_quotation(quotation_id: int) -> dict:
    result = _request("POST", f"/quotations/{quotation_id}/reject")
    list_quotations.clear()
    list_enquiries.clear()
    return result


def manual_pricing_note(quotation_id: int, note: str) -> dict:
    result = _request(
        "POST", f"/quotations/{quotation_id}/manual-pricing", json={"note": note}
    )
    list_quotations.clear()
    list_enquiries.clear()
    return result


def _fetch_document(path: str) -> bytes | None:
    """
    Returns the raw PDF bytes, or None if the API says no document exists
    (404 -- e.g. the capacity was outside the verified pricing range, so
    quotation_service.py never generated one). Goes over HTTP rather than
    reading quotation.pdf_path directly off disk, since that path is on
    whatever machine runs the API -- this keeps working once the dashboard
    and API are deployed on separate hosts (Phase D).
    """
    try:
        response = requests.get(f"{API_BASE_URL}{path}", timeout=_TIMEOUT)
    except requests.exceptions.RequestException as error:
        raise APIError(
            f"Couldn't reach the API at {API_BASE_URL} ({error.__class__.__name__})."
        ) from error
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise APIError(f"{response.status_code}: {response.text}")
    return response.content


@st.cache_data(ttl=300, show_spinner=False)
def get_quotation_letter(quotation_id: int) -> bytes | None:
    return _fetch_document(f"/quotations/{quotation_id}/letter")


@st.cache_data(ttl=300, show_spinner=False)
def get_quotation_annexure(quotation_id: int) -> bytes | None:
    return _fetch_document(f"/quotations/{quotation_id}/annexure")


def update_quotation_status(quotation_id: int, status: str) -> dict:
    result = _request("PATCH", f"/quotations/{quotation_id}/status", json={"status": status})
    list_quotations.clear()
    list_enquiries.clear()
    return result


def clear_all_caches() -> None:
    list_customers.clear()
    list_enquiries.clear()
    list_quotations.clear()
