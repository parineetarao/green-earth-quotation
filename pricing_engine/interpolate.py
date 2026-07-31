"""
Step 4 — Turn "customer wants X cum/day" into a priced bill of quantities.

WHY PER-LINE-ITEM INTERPOLATION, NOT A SINGLE FORMULA:
Early in this project we checked the real data across all 10 known tiers.
It showed two different scaling behaviours living in the same BOQ:
  - Some items (like MBBR media) scale almost perfectly linearly with
    capacity.
  - Most items (pumps, filter press, UF system, MCC panel) keep a FIXED
    quantity but jump to a higher unit rate at certain capacity
    breakpoints, because a bigger job needs a bigger standard equipment
    size, not more units of the small one.
A single "price = a * capacity + b" formula would blur both of these
into an average that matches neither. Instead, this module interpolates
EACH line item separately between the two real nearest known tiers, then
recomputes amount = qty * unit_rate, then sums to a total. This way the
output is always built from real observed numbers, never a guessed curve.

WHAT THIS MODULE DELIBERATELY REFUSES TO DO:
If the requested capacity falls outside the range we have real pricing
data for (below 50, or above 500 -- which includes the 550/600 tiers
that only have a blank quotation template and no cost estimate), this
module does NOT extrapolate a guessed price. It returns a result flagged
as out of range, because inventing a price for a real client quotation
with no backing data is exactly the kind of fabrication this whole
project has been built to avoid.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "stp_boq_data.json"
DIMENSION_DATA_PATH = Path(__file__).resolve().parent / "data" / "stp_dimension_data.json"


@dataclass
class LineItem:
    sr_no: int
    name: str
    specification: str | None
    qty: float
    unit_rate: float
    amount: float


@dataclass
class PricingResult:
    capacity: float
    in_verified_range: bool
    is_exact_known_tier: bool
    based_on_tiers: list[int]  # which real tier(s) this was built from
    line_items: list[LineItem] = field(default_factory=list)
    total: float | None = None
    note: str = ""


@dataclass
class UnitDimension:
    name: str
    quantity: str
    size_m3: float | None       # None means this unit doesn't scale numerically
    size_display: str           # what actually goes on the printed quotation
    material_of_construction: str
    is_interpolated: bool       # False for fixed/qualitative units like "Suitable"


@dataclass
class DimensionResult:
    capacity: float
    in_verified_range: bool
    is_exact_known_tier: bool
    based_on_tiers: list[int]
    units: list[UnitDimension] = field(default_factory=list)
    note: str = ""


def load_tier_data() -> dict:
    """Load the clean JSON produced by extract_excel_data.py (Step 3)."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH} not found. Run extract_excel_data.py first "
            "(Step 3) to generate it from the real Excel files."
        )
    return json.loads(DATA_PATH.read_text())


def load_dimension_data() -> dict:
    """Load the clean JSON produced by extract_docx_dimensions.py."""
    if not DIMENSION_DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DIMENSION_DATA_PATH} not found. Run extract_docx_dimensions.py "
            "first to generate it from the real Word templates."
        )
    return json.loads(DIMENSION_DATA_PATH.read_text())


def _known_capacities(tier_data: dict) -> list[int]:
    """Sorted list of capacities we have REAL priced data for, e.g. [50, 100, ... 500]."""
    return sorted(int(c) for c in tier_data["tiers"].keys())


def _line_items_for_tier(tier_data: dict, capacity: int) -> list[dict]:
    return tier_data["tiers"][str(capacity)]["line_items"]


def _interpolate_value(x0: float, y0: float, x1: float, y1: float, x: float) -> float:
    """Standard linear interpolation between two known points."""
    if x1 == x0:
        return y0
    fraction = (x - x0) / (x1 - x0)
    return y0 + fraction * (y1 - y0)


def price_capacity(capacity: float, tier_data: dict | None = None) -> PricingResult:
    """
    The main entry point. Given a target capacity in cum/day, return a
    priced bill of quantities.

    Three cases, handled explicitly rather than papered over:
      1. Capacity exactly matches a known tier -> return that tier's real
         data untouched, no interpolation math at all (avoids introducing
         floating-point drift into a number we already know exactly).
      2. Capacity falls between two known tiers -> interpolate per line
         item.
      3. Capacity falls outside the known range (< 50 or > 500) -> refuse
         to guess, return a clearly flagged result with no total.
    """
    if tier_data is None:
        tier_data = load_tier_data()

    known = _known_capacities(tier_data)
    min_known, max_known = known[0], known[-1]

    # Case 3: outside verified range -- refuse to fabricate a price
    if capacity < min_known or capacity > max_known:
        return PricingResult(
            capacity=capacity,
            in_verified_range=False,
            is_exact_known_tier=False,
            based_on_tiers=[],
            line_items=[],
            total=None,
            note=(
                f"{capacity} cum/day is outside the verified pricing range "
                f"({min_known}-{max_known} cum/day). This includes the "
                f"unpriced 550/600 tiers. Needs manual pricing review, not "
                f"an automated guess."
            ),
        )

    # Case 1: exact known tier -- return the real data as-is
    if capacity in known:
        raw_items = _line_items_for_tier(tier_data, int(capacity))
        items = [LineItem(**item) for item in raw_items]
        return PricingResult(
            capacity=capacity,
            in_verified_range=True,
            is_exact_known_tier=True,
            based_on_tiers=[int(capacity)],
            line_items=items,
            total=tier_data["tiers"][str(int(capacity))]["total"],
            note="Exact match to a real priced tier, no interpolation applied.",
        )

    # Case 2: between two known tiers -- interpolate per line item
    lower_tier = max(c for c in known if c < capacity)
    upper_tier = min(c for c in known if c > capacity)

    lower_items = _line_items_for_tier(tier_data, lower_tier)
    upper_items = _line_items_for_tier(tier_data, upper_tier)

    interpolated_items = []
    running_total = 0.0

    # Line items are matched by position (sr_no), not by name string
    # matching, since all 10 real sheets confirmed to have the same 29
    # items in the same order.
    for lower_item, upper_item in zip(lower_items, upper_items):
        qty = _interpolate_value(lower_tier, lower_item["qty"], upper_tier, upper_item["qty"], capacity)
        unit_rate = _interpolate_value(
            lower_tier, lower_item["unit_rate"], upper_tier, upper_item["unit_rate"], capacity
        )
        amount = qty * unit_rate
        running_total += amount

        interpolated_items.append(
            LineItem(
                sr_no=lower_item["sr_no"],
                name=lower_item["name"],
                specification=lower_item["specification"],
                qty=round(qty, 2),
                unit_rate=round(unit_rate, 2),
                amount=round(amount, 2),
            )
        )

    return PricingResult(
        capacity=capacity,
        in_verified_range=True,
        is_exact_known_tier=False,
        based_on_tiers=[lower_tier, upper_tier],
        line_items=interpolated_items,
        total=round(running_total, 2),
        note=f"Interpolated between real {lower_tier} and {upper_tier} cum/day tiers.",
    )


def size_capacity(capacity: float, dimension_data: dict | None = None) -> DimensionResult:
    """
    Sibling function to price_capacity, but for civil unit dimensions
    (tank sizes etc.) instead of BOQ pricing. Deliberately mirrors the
    same three cases -- exact tier / interpolate between two known tiers /
    refuse if out of range -- so the two are easy to reason about together.

    IMPORTANT DIFFERENCE FROM PRICING: not every unit has a numeric size
    even in the real source documents (e.g. "Foundation for Blower..." is
    always "Suitable", not a number; several tanks have a blank size at
    every tier). For those units, interpolation is skipped and the value
    is carried through unchanged from the lower known tier -- there is
    nothing to interpolate, and guessing a number here would be fabricating
    a civil dimension that could end up on a real construction drawing.
    """
    if dimension_data is None:
        dimension_data = load_dimension_data()

    known = sorted(int(c) for c in dimension_data["tiers"].keys())
    min_known, max_known = known[0], known[-1]

    if capacity < min_known or capacity > max_known:
        return DimensionResult(
            capacity=capacity,
            in_verified_range=False,
            is_exact_known_tier=False,
            based_on_tiers=[],
            units=[],
            note=(
                f"{capacity} cum/day is outside the verified dimension data range "
                f"({min_known}-{max_known} cum/day). Needs manual civil design "
                f"review, not an automated guess."
            ),
        )

    if capacity in known:
        raw_units = dimension_data["tiers"][str(int(capacity))]
        units = [
            UnitDimension(
                name=u["name"],
                quantity=u["quantity"],
                size_m3=u["size"]["numeric_m3"],
                size_display=u["size"]["raw"],
                material_of_construction=u["material_of_construction"],
                is_interpolated=False,
            )
            for u in raw_units
        ]
        return DimensionResult(
            capacity=capacity,
            in_verified_range=True,
            is_exact_known_tier=True,
            based_on_tiers=[int(capacity)],
            units=units,
            note="Exact match to a real tier's dimensions, no interpolation applied.",
        )

    lower_tier = max(c for c in known if c < capacity)
    upper_tier = min(c for c in known if c > capacity)
    lower_units = dimension_data["tiers"][str(lower_tier)]
    upper_units = dimension_data["tiers"][str(upper_tier)]

    interpolated_units = []
    for lower_unit, upper_unit in zip(lower_units, upper_units):
        lower_size = lower_unit["size"]
        upper_size = upper_unit["size"]

        if lower_size["is_numeric"] and upper_size["is_numeric"]:
            size_m3 = _interpolate_value(
                lower_tier, lower_size["numeric_m3"], upper_tier, upper_size["numeric_m3"], capacity
            )
            size_m3 = round(size_m3, 1)
            interpolated_units.append(
                UnitDimension(
                    name=lower_unit["name"],
                    quantity=lower_unit["quantity"],
                    size_m3=size_m3,
                    size_display=f"{size_m3} m3",
                    material_of_construction=lower_unit["material_of_construction"],
                    is_interpolated=True,
                )
            )
        else:
            # Non-numeric in the real data (e.g. "Suitable", or blank) --
            # carry through unchanged rather than inventing a number.
            interpolated_units.append(
                UnitDimension(
                    name=lower_unit["name"],
                    quantity=lower_unit["quantity"],
                    size_m3=None,
                    size_display=lower_size["raw"],
                    material_of_construction=lower_unit["material_of_construction"],
                    is_interpolated=False,
                )
            )

    return DimensionResult(
        capacity=capacity,
        in_verified_range=True,
        is_exact_known_tier=False,
        based_on_tiers=[lower_tier, upper_tier],
        units=interpolated_units,
        note=f"Interpolated between real {lower_tier} and {upper_tier} cum/day tier dimensions.",
    )


if __name__ == "__main__":
    # Quick manual check when running this file directly
    for test_capacity in [200, 275, 500, 550, 30]:
        result = price_capacity(test_capacity)
        print(f"\ncapacity={result.capacity}  in_range={result.in_verified_range}  "
              f"exact_tier={result.is_exact_known_tier}  based_on={result.based_on_tiers}")
        print(f"  total = {result.total}")
        print(f"  note: {result.note}")

    print("\n--- dimensions ---")
    for test_capacity in [200, 275]:
        dim_result = size_capacity(test_capacity)
        print(f"\ncapacity={dim_result.capacity}  based_on={dim_result.based_on_tiers}")
        for unit in dim_result.units:
            print(f"  {unit.name}: {unit.size_display}  (interpolated={unit.is_interpolated})")