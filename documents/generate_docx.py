"""
Step 7 — Generate a real, filled STP quotation letter from the tagged
template, using the proven pricing_engine outputs.

WHY docxtpl:
It renders Jinja2-style {{ tags }} inside a real .docx file while keeping
all of Word's formatting intact -- unlike editing raw XML by hand, this
respects fonts, spacing, headers/footers exactly as the original template
had them.

NOTE ON THE ANNEXURE IV BOQ:
As established when we inspected the real documents, the 29-line BOQ was
never embedded inside this Word letter -- it's a separate priced sheet.
generate_boq_annexure.py (a sibling script) produces that from the same
pricing_engine data. This script produces ONLY the cover letter.
"""

import sys
from datetime import date
from pathlib import Path

from docxtpl import DocxTemplate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pricing_engine"))
from interpolate import price_capacity, size_capacity, load_tier_data, load_dimension_data  # noqa: E402
from number_to_words_indian import number_to_indian_words  # noqa: E402

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "stp_quotation_template.docx"


def build_quotation_context(
    capacity: float,
    customer_name: str,
    attn_name: str,
    ref_no: str,
    completion_weeks_min: int,
    completion_weeks_max: int,
    quotation_date: date | None = None,
) -> dict:
    """
    Assemble everything the template's {{ tags }} need, pulling real
    numbers from the already-tested pricing_engine -- this function does
    NO pricing or dimension math of its own, on purpose, so there is only
    one place in the whole project where that logic lives.
    """
    pricing_result = price_capacity(capacity, load_tier_data())
    dimension_result = size_capacity(capacity, load_dimension_data())

    if not pricing_result.in_verified_range:
        raise ValueError(
            f"Cannot generate a quotation for {capacity} cum/day: {pricing_result.note}"
        )

    context = {
        "customer_name": customer_name,
        "attn_name": attn_name,
        "ref_no": ref_no,
        "quotation_date": (quotation_date or date.today()).strftime("%d/%m/%Y"),
        "capacity": int(capacity) if float(capacity).is_integer() else capacity,
        "price_number": f"{pricing_result.total:,.0f}",
        "price_words": number_to_indian_words(pricing_result.total),
        "completion_weeks_min": completion_weeks_min,
        "completion_weeks_max": completion_weeks_max,
    }

    # unit_0_size .. unit_11_size, matching the tagged template exactly
    for i, unit in enumerate(dimension_result.units):
        context[f"unit_{i}_size"] = unit.size_display

    return context, pricing_result, dimension_result


def generate_quotation_docx(context: dict, output_path: Path) -> None:
    doc = DocxTemplate(str(TEMPLATE_PATH))
    doc.render(context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


if __name__ == "__main__":
    import traceback

    try:
        print("Starting generate_docx.py...", flush=True)
        print(f"Looking for template at: {TEMPLATE_PATH}", flush=True)
        print(f"Template exists: {TEMPLATE_PATH.exists()}", flush=True)

        # Manual smoke test: generate a real quotation for a capacity we have
        # exact real data for (200), so the output can be checked against the
        # real original document.
        context, pricing_result, dimension_result = build_quotation_context(
            capacity=200,
            customer_name="Test Industries Pvt. Ltd.",
            attn_name="Rajesh Sharma",
            # NOTE: ref_no is intentionally a placeholder that must be
            # supplied per-quotation by the reviewing human -- there is
            # no single correct default. Ask the business owner what the
            # real ref-numbering convention should be for STP jobs
            # specifically before this goes near a real client.
            ref_no="GEEC/SAT/C2/Q4/STP/001/26-27",
            completion_weeks_min=8,
            completion_weeks_max=10,
        )

        print("Context that will fill the template:", flush=True)
        for key, value in context.items():
            print(f"  {key}: {value}", flush=True)

        output_path = Path(__file__).resolve().parent.parent / "storage" / "generated_quotations" / "test_quotation_200.docx"

        print(f"\nRendering to: {output_path}", flush=True)
        generate_quotation_docx(context, output_path)
        print(f"\nSUCCESS. Generated: {output_path}", flush=True)

    except Exception:
        print("\n--- FAILED. Full error below ---", flush=True)
        traceback.print_exc()
        sys.exit(1)