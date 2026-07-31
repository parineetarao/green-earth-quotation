"""
Turns a free-text inbound enquiry email into the structured fields the
rest of the system needs, using the Gemini API's structured-output mode
(response_schema on google-genai) so the result is guaranteed to match
ExtractedEnquiryFields -- no hand-rolled JSON parsing, no chance of the
model wrapping the answer in prose.

Uses Gemini instead of Claude here specifically because of a budget
constraint (no paid Anthropic credits available) -- see CLAUDE.md's tech
stack section. Everything else about this module's contract is
unchanged from the Claude version.

WHY LOW CONFIDENCE / MISSING CAPACITY MEANS "DON'T AUTO-PROCEED":
Per CLAUDE.md, an enquiry whose capacity the model couldn't confidently
extract must land in "needs_review", not silently continue toward a
generated quotation for the wrong capacity. This module only extracts;
the caller (api/routes/enquiries.py) is the one that decides the
resulting enquiry's status from `confidence` and `capacity_cum_day`.
"""

from google import genai
from google.genai import types

from api.schemas import ExtractedEnquiryFields

EXTRACTION_SYSTEM_PROMPT = """\
You extract structured details from an inbound email enquiry sent to an \
environmental engineering firm that builds Sewage Treatment Plants (STPs).

Read the email and return:
- capacity_cum_day: the requested STP capacity in cubic meters per day, as \
a number. null if not stated or not inferable.
- product_type: "STP" if this is a sewage treatment plant enquiry, \
otherwise your best short label (e.g. "ETP") or null if unclear.
- location: the customer's site location/city, or null if not mentioned.
- customer_name: the sending company or person's name, or null if not \
clear from the email content itself.
- confidence: "high" only if capacity_cum_day and product_type are both \
clearly and unambiguously stated in the email. "low" for anything vague, \
implied, or requiring guesswork.

Do not guess a capacity number that isn't actually in the email. If in \
doubt, prefer null and "low" confidence over a fabricated value.\
"""

_REFUSAL_FALLBACK = ExtractedEnquiryFields(
    capacity_cum_day=None,
    product_type=None,
    location=None,
    customer_name=None,
    confidence="low",
)


def extract_enquiry_fields(raw_message: str) -> ExtractedEnquiryFields:
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=raw_message,
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ExtractedEnquiryFields,
        ),
    )

    blocked = response.prompt_feedback is not None and response.prompt_feedback.block_reason is not None
    refused = not response.candidates or response.candidates[0].finish_reason not in (
        types.FinishReason.STOP,
        None,
    )

    if blocked or refused or response.parsed is None:
        return _REFUSAL_FALLBACK

    return response.parsed
