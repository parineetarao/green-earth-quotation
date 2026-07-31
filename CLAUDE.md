# Green Earth Quotation System — Project Brief for Claude Code

## What this project is

An internal tool for Green Earth Engineers & Consultants (a real, 30+ year
old Mumbai environmental engineering firm) that automates generating
Sewage Treatment Plant (STP) quotations, and tracks customers/enquiries/
quotations end to end. Built by a final-year AI/DS student as an
internship deliverable — every part of this must be understandable and
explainable by the developer, not just working code they can't defend.

## What's already built and PROVEN — do not rebuild or second-guess this

Everything in `pricing_engine/` and `documents/` is complete, tested
against the real company's Excel/Word source files, and verified working
on the developer's own machine. Treat this as ground truth:

- `pricing_engine/extract_excel_data.py` — extracts real BOQ pricing
  across 10 real STP capacity tiers (50-500 cum/day) from the company's
  actual Excel cost estimates into `pricing_engine/data/stp_boq_data.json`
- `pricing_engine/extract_docx_dimensions.py` — extracts real civil unit
  dimensions (12 units per tier) from the company's actual Word
  quotation templates into `pricing_engine/data/stp_dimension_data.json`
- `pricing_engine/interpolate.py` — the core pricing/sizing logic.
  `price_capacity(capacity)` and `size_capacity(capacity)` are the two
  functions everything else should call. Both:
  - Return exact real data if the capacity matches a known tier
  - Interpolate PER LINE ITEM / PER UNIT between the two nearest known
    tiers if the capacity falls between them (NOT a single formula on
    the total — this was deliberately chosen after finding the real
    data has mixed linear/step-function scaling behaviour)
  - REFUSE to return a price/size (return `in_verified_range: False`,
    no fabricated number) if the capacity is outside 50-500 cum/day
  - Fully tested — 12 passing tests in `pricing_engine/tests/test_interpolate.py`
- `documents/tag_word_template.py` — produced the tagged docxtpl
  template at `documents/templates/stp_quotation_template.docx`
- `documents/generate_docx.py` — `build_quotation_context()` and
  `generate_quotation_docx()` render a real filled quotation letter
- `documents/generate_boq_annexure.py` — generates the separate Annexure
  IV price sheet (the real company documents never embed the BOQ table
  inside the letter — confirmed by inspecting all 50 tables in the real
  Word file — so this is intentionally a second document, not a bug)
- `documents/number_to_words_indian.py` — converts a price to words using
  real Indian numbering (Lakh/Crore), hand-written and tested rather than
  trusting an unverified library's locale support
- `documents/convert_to_pdf.py` — converts a .docx to PDF via LibreOffice
  headless (`soffice` must be installed and on PATH)

**Do not modify the interpolation logic, the pricing math, or the price
formatting to "clean it up" or "make it more general."** The current
approach was chosen deliberately after analyzing the real data and
finding simple formulas don't match reality. If something here looks
odd, ask before changing it.

## CRITICAL non-negotiables — these override any instinct to simplify

1. **This is STP-only right now.** There is NO real ETP (Effluent
   Treatment Plant) pricing/template data yet — the business owner is
   sourcing this and will provide it later. Build every part of the
   schema and API assuming a `product_type` field exists (values:
   currently only `"STP"` is valid), so ETP can be added later without a
   rebuild — but do NOT invent placeholder ETP pricing logic, templates,
   or data. If asked to "support ETP," the correct action is to add the
   schema/routing hook, not fabricated pricing.
2. **Never auto-send anything to a real customer.** Every quotation,
   whether generated from a website form or an emailed enquiry, must
   land in a "Draft" status in a review queue and wait for an explicit
   human approval action before an email/PDF goes to a customer. No
   exceptions, no "if confidence is high" shortcuts.
3. **Never fabricate a price or dimension.** If `price_capacity()` or
   `size_capacity()` returns `in_verified_range: False`, the system must
   show this clearly to the reviewing human as "outside verified data,
   needs manual pricing" — never silently extrapolate, never hide the
   flag, never round to the nearest known tier without saying so.
4. **Historical real quotations may arrive later** from the business
   owner. When they do, they are for VALIDATING the pricing engine
   against real-world negotiated prices, not for silently retraining
   or changing the interpolation logic. Build a simple, obvious place
   (a `notes` field or a `data/historical_quotations/` folder) to drop
   these in later — don't build any automated ingestion for this now.

## Tech stack — Python only, deliberately

The developer's core language is Python (AI/DS/ML student), does not
want to write or maintain JavaScript/TypeScript backend code, and needs
to understand and defend every part of this in an internship review.

- **Backend API**: FastAPI
- **Database**: PostgreSQL, hosted on Supabase (free tier)
- **ORM**: SQLAlchemy (synchronous, not async — keep it simple)
- **Admin dashboard**: Streamlit — NOT a hand-built React app. Every
  screen (review queue, customer list, enquiry list, dashboard) should
  be a Streamlit page.
- **Email intake**: Postmark or Mailgun inbound webhook -> FastAPI endpoint
- **Free-text enquiry extraction**: Google Gemini API (`google-genai`
  SDK), structured JSON output via `response_schema`. Originally spec'd
  as the Anthropic Claude API, but switched to Gemini because there's no
  budget for paid Anthropic credits right now and Google issues a free
  API key; the extraction contract (system prompt, output schema,
  low-confidence-on-refusal handling) is unchanged, only the provider
  underneath `api/services/email_extraction.py` differs. Uses the pinned
  `gemini-3.1-flash-lite` -- `gemini-2.5-pro` and the entire
  `gemini-2.0-flash*` family return `limit: 0` on this free-tier key
  (permanent, not a rate-limit blip), and `gemini-2.5-flash`/
  `gemini-2.5-flash-lite` are "no longer available to new users."
  Deliberately pinned rather than using the `gemini-flash-latest` alias:
  a `-latest` alias is Google's floating pointer to whatever model they
  currently default to, and it can get silently repointed with no
  version bump or changelog -- for a system whose design hinges on
  trusting the `confidence` field to gate auto-processing (see
  CRITICAL non-negotiable #2), an unannounced model swap changing
  extraction/confidence calibration underneath us is a real risk, not
  a theoretical one. If `gemini-3.1-flash-lite` is ever deprecated,
  `gemini-3.5-flash-lite` is a confirmed-working free-tier fallback
  (also verified against both a clear and an ambiguous test email) --
  it was skipped as the default only because its GA release is newer
  and has less of a track record.
- **Auth**: simple email+password (Supabase Auth or a lightweight
  Streamlit auth package) — this is a 1-3 person internal tool, not
  enterprise software. Do not over-build this.
- **Hosting**: Render or Railway for the API, Streamlit Community Cloud
  (or same host) for the dashboard

Do NOT introduce Node.js, Express, Next.js, or any JS backend code for
any part of this system. The ONLY existing JS/TS code in this project is
the separate, already-built public website (a different, unrelated
Lovable-built React app) — do not touch that codebase as part of this
work, beyond potentially adding one fetch call in its existing Request-a-
Quote form to POST to this new API, if/when asked.

## What to build, in order

### Phase A — Database schema
Three core tables:
- `customers` (id, name, contact_person, phone, email, industry, location, created_at)
- `enquiries` (id, customer_id FK, source ["website_form"|"email"|"manual"],
  product_type ["STP"], capacity_cum_day, raw_message, status
  ["new"|"needs_review"|"quoted"|"closed_won"|"closed_lost"], created_at)
  -- status values updated in Phase C: "processed" was replaced by
  "quoted"/"closed_won"/"closed_lost" so the Enquiries dashboard page can
  show an enquiry's outcome, not just "a quotation exists". See
  `database/models.py`'s `EnquiryStatus` docstring for the exact
  transitions.
- `quotations` (id, enquiry_id FK, capacity_cum_day, price_total,
  in_verified_range (bool), docx_path, pdf_path, notes, status
  ["draft"|"sent"|"won"|"lost"|"no_response"|"rejected"|"needs_manual_pricing"],
  created_at, sent_at)
  -- "rejected" and "needs_manual_pricing" (plus the `notes` column) were
  added in Phase C for the Review Queue's Reject and Price-manually
  actions -- see `database/models.py`'s `QuotationStatus` docstring.

Write this as SQLAlchemy models in `database/models.py`, plus a
`database/session.py` that connects to the Supabase Postgres instance
using an environment variable `DATABASE_URL` (never hardcode credentials).

### Phase B — FastAPI backend
Routes needed:
- `POST /enquiries` — create an enquiry (called by the website form directly)
- `POST /enquiries/from-email` — webhook endpoint for inbound email
  (Postmark/Mailgun format), runs the Gemini extraction step, creates
  an enquiry
- `POST /enquiries/{id}/generate-quotation` — calls
  `pricing_engine.interpolate.price_capacity` /`size_capacity`,
  `documents.generate_docx`, `documents.generate_boq_annexure`,
  `documents.convert_to_pdf` in sequence, creates a `quotations` row
  with status "draft"
- `POST /quotations/{id}/approve-and-send` — marks status "sent", emails
  the PDF to the customer (only endpoint that actually sends anything —
  must require an explicit call, never triggered automatically)
- `PATCH /quotations/{id}/status` — update to won/lost/no_response
- `GET /customers`, `GET /customers/{id}`, `GET /enquiries`, `GET /quotations` — list/detail views for the dashboard to call

For the Gemini extraction step specifically: prompt Gemini to return
STRICT JSON with fields `capacity_cum_day` (number or null),
`product_type` (string or null), `location` (string or null),
`customer_name` (string or null), and `confidence` ("high"|"low"). If
`capacity_cum_day` is null or confidence is "low", the enquiry should be
created with status "needs_review" and NOT auto-proceed to quotation
generation.

### Phase C — Streamlit dashboard
Pages, using Streamlit's multipage app structure (`dashboard/pages/`):
1. **Review queue** — lists all "draft" quotations, shows the PDF
   inline (or a download link), a clear badge if `in_verified_range` is
   False, Approve/Reject buttons
2. **Customers** — searchable table, click into a customer to see every
   quotation ever sent to them
3. **Enquiries** — list with status filter, including "needs_review"
   ones that need a human to fill in missing details manually
4. **Summary** — simple counts: enquiries this month, win rate, quotations
   by status — plain SQL aggregation, no ML

### Phase D — Deployment
- API + Postgres to Render or Railway, env vars for `DATABASE_URL`,
  `GEMINI_API_KEY`, email service API key
- Streamlit dashboard to Streamlit Community Cloud, pointed at the
  deployed API's URL
- Basic password protection on the dashboard before this is considered done

## How to work

- Work phase by phase (A, then B, then C, then D). Don't jump ahead.
- After each phase, explain in plain terms what was built and why, so
  the developer can genuinely follow along — they will be asked to
  defend this project.
- If something about the existing `pricing_engine`/`documents` code is
  unclear, read the actual code and its docstrings first — they're
  heavily commented specifically to explain the real-world data quirks
  behind each decision.
- Prefer boring, standard, well-documented approaches over clever ones.
  This needs to be maintainable by a solo developer under time pressure,
  not impressive.