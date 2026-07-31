"""
Step 5 — Prove interpolate.py is correct BEFORE trusting it with a real
customer-facing quotation.

Run with:
    pytest pricing_engine/tests/test_interpolate.py -v
"""

import sys
from pathlib import Path

# Make pricing_engine importable when running pytest from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpolate import (  # noqa: E402
    price_capacity,
    load_tier_data,
    size_capacity,
    load_dimension_data,
)

# Real totals taken directly from the company's own Excel files.
# If these ever fail, something is wrong with the extraction or the
# interpolation logic -- these numbers are ground truth, not estimates.
KNOWN_REAL_TOTALS = {
    50: 1099467.5,
    100: 1518580,
    150: 1970780,
    200: 2144680,
    250: 2322900,
    300: 2846237.5,
    350: 2930887.5,
    400: 3440037.5,
    450: 3602547.5,
    500: 4191950,
}


def test_exact_known_tiers_match_real_totals_exactly():
    """
    For every capacity we have real data for, the engine must return
    EXACTLY that real number -- not an approximation, not a value run
    through interpolation math that could introduce drift.
    """
    tier_data = load_tier_data()
    for capacity, expected_total in KNOWN_REAL_TOTALS.items():
        result = price_capacity(capacity, tier_data)
        assert result.is_exact_known_tier is True
        assert result.total == expected_total, (
            f"{capacity} cum/day: expected real total {expected_total}, "
            f"got {result.total}"
        )


def test_exact_known_tier_has_29_line_items():
    """Sanity check: every real tier has all 29 real BOQ line items, none dropped."""
    tier_data = load_tier_data()
    result = price_capacity(200, tier_data)
    assert len(result.line_items) == 29


def test_interpolated_capacity_falls_between_its_two_neighbours():
    """
    A capacity between two known tiers (e.g. 275, between 250 and 300)
    should produce a total that sits between those two real totals --
    proof the interpolation isn't producing a nonsensical result.
    """
    tier_data = load_tier_data()
    result = price_capacity(275, tier_data)

    assert result.in_verified_range is True
    assert result.is_exact_known_tier is False
    assert result.based_on_tiers == [250, 300]
    assert KNOWN_REAL_TOTALS[250] < result.total < KNOWN_REAL_TOTALS[300]


def test_interpolation_is_roughly_midpoint_for_a_midpoint_capacity():
    """
    275 is exactly halfway between 250 and 300, so its total should be
    close to the midpoint of those two real totals (not exactly equal,
    since each line item interpolates independently, but close).
    """
    tier_data = load_tier_data()
    result = price_capacity(275, tier_data)
    expected_midpoint = (KNOWN_REAL_TOTALS[250] + KNOWN_REAL_TOTALS[300]) / 2

    # Allow a small tolerance since per-item interpolation isn't
    # mathematically identical to interpolating the total directly.
    assert abs(result.total - expected_midpoint) < 5000


def test_capacity_above_max_known_tier_is_refused_not_guessed():
    """
    550 cum/day has a quotation template but NO real cost estimate.
    The engine must refuse to invent a price for it.
    """
    tier_data = load_tier_data()
    result = price_capacity(550, tier_data)

    assert result.in_verified_range is False
    assert result.total is None
    assert result.line_items == []
    assert "outside the verified pricing range" in result.note


def test_capacity_below_min_known_tier_is_refused_not_guessed():
    """Same refusal behaviour below the smallest real tier (50)."""
    tier_data = load_tier_data()
    result = price_capacity(30, tier_data)

    assert result.in_verified_range is False
    assert result.total is None


def test_capacity_exactly_at_boundary_is_accepted():
    """500 is the largest tier WITH real data -- must be treated as in-range."""
    tier_data = load_tier_data()
    result = price_capacity(500, tier_data)

    assert result.in_verified_range is True
    assert result.is_exact_known_tier is True


# ---------------------------------------------------------------------
# Dimension (civil unit) tests -- same guarantees, different data source
# ---------------------------------------------------------------------

# Real Aeration Tank sizes taken directly from the Word templates
KNOWN_AERATION_TANK_M3 = {
    50: 23, 100: 43, 150: 65, 200: 87, 250: 120,
    300: 130, 350: 160, 400: 170, 450: 190, 500: 215,
}


def test_exact_known_tier_dimensions_match_real_documents():
    """Every priced tier's exact dimensions must match the real Word template, unaltered."""
    dimension_data = load_dimension_data()
    for capacity, expected_size in KNOWN_AERATION_TANK_M3.items():
        result = size_capacity(capacity, dimension_data)
        assert result.is_exact_known_tier is True
        aeration_tank = next(u for u in result.units if u.name == "Aeration Tank")
        assert aeration_tank.size_m3 == expected_size


def test_exact_known_tier_has_12_units():
    dimension_data = load_dimension_data()
    result = size_capacity(200, dimension_data)
    assert len(result.units) == 12


def test_dimension_interpolation_falls_between_neighbours():
    """275 should give an Aeration Tank size between the real 250 and 300 values."""
    dimension_data = load_dimension_data()
    result = size_capacity(275, dimension_data)
    aeration_tank = next(u for u in result.units if u.name == "Aeration Tank")

    assert KNOWN_AERATION_TANK_M3[250] < aeration_tank.size_m3 < KNOWN_AERATION_TANK_M3[300]
    assert aeration_tank.is_interpolated is True


def test_non_numeric_units_are_never_interpolated_or_invented():
    """
    "Foundation for Blower..." is "Suitable" in every real tier, never a
    number. The engine must never turn this into a fabricated size, even
    for an interpolated capacity.
    """
    dimension_data = load_dimension_data()
    result = size_capacity(275, dimension_data)
    foundation = next(u for u in result.units if "Foundation" in u.name)

    assert foundation.size_m3 is None
    assert foundation.is_interpolated is False
    assert foundation.size_display == "Suitable"


def test_dimension_capacity_out_of_range_is_refused_not_guessed():
    dimension_data = load_dimension_data()
    result = size_capacity(550, dimension_data)

    assert result.in_verified_range is False
    assert result.units == []