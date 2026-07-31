"""
Sends the approved quotation PDF to the customer via Postmark's Send API.

This is deliberately the ONLY module in the whole system that emails a
real customer, called from exactly one place:
POST /quotations/{id}/approve-and-send. Per CLAUDE.md's non-negotiables,
nothing else may trigger this -- every quotation must sit in "draft"
until a human explicitly approves it.
"""

import base64
import os
from pathlib import Path

import requests

POSTMARK_SEND_URL = "https://api.postmarkapp.com/email"


def send_quotation_email(
    to_email: str,
    customer_name: str,
    pdf_path: Path,
    annexure_pdf_path: Path | None = None,
) -> None:
    """
    Raises a clear RuntimeError on any failure -- this is a real email to
    a real customer, so a silent failure here would be worse than a loud
    one that stops the "approve and send" action from falsely reporting
    success.
    """
    api_token = os.environ.get("POSTMARK_API_KEY")
    from_email = os.environ.get("POSTMARK_FROM_EMAIL")
    if not api_token or not from_email:
        raise RuntimeError(
            "POSTMARK_API_KEY and POSTMARK_FROM_EMAIL must both be set to send "
            "a quotation email. Check your .env."
        )

    attachments = [_encode_attachment(pdf_path)]
    if annexure_pdf_path is not None:
        attachments.append(_encode_attachment(annexure_pdf_path))

    payload = {
        "From": from_email,
        "To": to_email,
        "Subject": "Your STP Quotation from Green Earth Engineers & Consultants",
        "TextBody": (
            f"Dear {customer_name},\n\n"
            "Please find attached your Sewage Treatment Plant quotation, "
            "including the price bid annexure.\n\n"
            "Regards,\nGreen Earth Engineers & Consultants"
        ),
        "Attachments": attachments,
        "MessageStream": "outbound",
    }

    response = requests.post(
        POSTMARK_SEND_URL,
        json=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": api_token,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Postmark send failed ({response.status_code}): {response.text}"
        )


def _encode_attachment(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- nothing to attach.")
    return {
        "Name": path.name,
        "Content": base64.standard_b64encode(path.read_bytes()).decode("ascii"),
        "ContentType": "application/pdf",
    }
