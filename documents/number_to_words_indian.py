"""
Convert a rupee amount into words using Indian numbering (Lakh/Crore),
the way it needs to appear on a real quotation: e.g. 2144680 ->
"Twenty One Lakh Forty Four Thousand Six Hundred Eighty".

WHY THIS IS HAND-WRITTEN INSTEAD OF USING A LIBRARY:
General-purpose number-to-words libraries default to the Western
grouping (thousand/million/billion), and their Indian-locale support is
inconsistent across versions. Getting this wrong on a real document sent
under the company's name is exactly the kind of small, embarrassing
mistake this project has been built to avoid -- so this is a small,
self-contained, fully tested function instead of an unverified
dependency.
"""

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]


def _two_digit_words(n: int) -> str:
    if n < 20:
        return ONES[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + (f" {ONES[ones]}" if ones else "")


def _three_digit_words(n: int) -> str:
    hundreds, remainder = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{ONES[hundreds]} Hundred")
    if remainder:
        parts.append(_two_digit_words(remainder))
    return " ".join(parts)


def number_to_indian_words(amount: float) -> str:
    """
    Convert a rupee amount to words using Indian grouping:
    ...Crore, Lakh, Thousand, Hundred, then the last two digits.

    Handles a fractional paise part if present (e.g. 1234.50 ->
    "... Rupees ... and Fifty Paise"), though real quotations in this
    project's data are always whole rupees.
    """
    amount = round(float(amount), 2)
    rupees = int(amount)
    paise = round((amount - rupees) * 100)

    if rupees == 0:
        words = "Zero"
    else:
        crore, remainder = divmod(rupees, 10_000_000)
        lakh, remainder = divmod(remainder, 100_000)
        thousand, remainder = divmod(remainder, 1000)
        hundred_and_below = remainder

        parts = []
        if crore:
            parts.append(f"{_two_digit_words(crore) if crore < 100 else _three_digit_words(crore)} Crore")
        if lakh:
            parts.append(f"{_two_digit_words(lakh)} Lakh")
        if thousand:
            parts.append(f"{_two_digit_words(thousand)} Thousand")
        if hundred_and_below:
            parts.append(_three_digit_words(hundred_and_below))

        words = " ".join(parts)

    if paise:
        return f"{words} Rupees and {_two_digit_words(paise)} Paise"
    return words


if __name__ == "__main__":
    # Self-test against real totals from this project's own data, plus
    # known hand-checkable edge cases.
    test_cases = {
        2144680: "Twenty One Lakh Forty Four Thousand Six Hundred Eighty",
        1099467.5: "Ten Lakh Ninety Nine Thousand Four Hundred Sixty Seven Rupees and Fifty Paise",
        4191950: "Forty One Lakh Ninety One Thousand Nine Hundred Fifty",
        100: "One Hundred",
        1000: "One Thousand",
        100000: "One Lakh",
        10000000: "One Crore",
        12345678: "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight",
        0: "Zero",
    }

    passed, failed = 0, 0
    for amount, expected in test_cases.items():
        result = number_to_indian_words(amount)
        if result == expected:
            print(f"PASS: {amount} -> {result}")
            passed += 1
        else:
            print(f"FAIL: {amount} -> got '{result}', expected '{expected}'")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
