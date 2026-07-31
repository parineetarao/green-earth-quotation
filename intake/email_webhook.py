"""
Parses Postmark's inbound-email webhook payload into the plain fields the
rest of the system needs: who sent it, and what they wrote.

WHY POSTMARK SPECIFICALLY:
CLAUDE.md lists "Postmark or Mailgun" as acceptable inbound providers
without picking one. Postmark's inbound webhook is a single JSON POST
(no multipart form parsing needed), which is the simpler of the two to
parse -- so this project uses it. If the business ends up on Mailgun
instead, only this file needs to change: the FastAPI route and the
Claude extraction step both consume the plain ParsedInboundEmail this
produces, not Postmark's payload shape directly.

Real Postmark inbound payloads carry many more fields than modeled below
(attachments, headers, spam scores, ...) -- only the ones this project
actually uses are declared, and the rest are ignored rather than
rejected.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


class PostmarkFromFull(BaseModel):
    model_config = ConfigDict(extra="ignore")

    Email: str
    Name: str = ""


class PostmarkInboundPayload(BaseModel):
    """Shape of Postmark's inbound webhook POST body, trimmed to what we use."""

    model_config = ConfigDict(extra="ignore")

    FromFull: PostmarkFromFull
    Subject: str = ""
    TextBody: str = ""
    StrippedTextReply: str = ""


@dataclass
class ParsedInboundEmail:
    sender_email: str
    sender_name: str
    subject: str
    raw_message: str


def parse_inbound_email(payload: PostmarkInboundPayload) -> ParsedInboundEmail:
    """
    Prefer StrippedTextReply (Postmark's best-effort "just the new reply,
    quoted history stripped out") when present, since that's the actual
    enquiry text. Fall back to the full TextBody for a first-contact email,
    which has no quoted history to strip and so has no StrippedTextReply.
    """
    raw_message = payload.StrippedTextReply.strip() or payload.TextBody.strip()

    return ParsedInboundEmail(
        sender_email=payload.FromFull.Email,
        sender_name=payload.FromFull.Name or payload.FromFull.Email,
        subject=payload.Subject,
        raw_message=raw_message,
    )
