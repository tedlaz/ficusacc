"""Unit tests for the plain-text journal export."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.web.journal_export import (
    MissingMappingError,
    build_account_list,
    build_journal,
    format_amount,
    parse_mapping,
)

SAMPLE_MAPPING = {
    "38.00.00": "Ταμείο.Μετρητά",
    "33.90.01": "Χρεώστες.1-Νικολόπουλος",
    "33.90.02": "Χρεώστες.2-Καλυβιώτη",
    "33.90.03": "Χρεώστες.3-Ντούλης",
    "33.90.04": "Χρεώστες.4-Αχλάδη",
    "33.90.05": "Χρεώστες.5-Λάζαρος",
    "70.00.00": "Εσοδα.Κοινόχρηστα",
}


def account(account_id: int, code: str, name: str = "Λογαριασμός"):
    return SimpleNamespace(id=account_id, code=code, name=name)


def line(account_id: int, amount: str, order: int):
    return SimpleNamespace(id=order + 1, account_id=account_id, amount=Decimal(amount),
                           line_order=order)


def test_parse_mapping_reads_the_real_conversion_file():
    raw = Path("metatropi.txt").read_text(encoding="utf-8-sig")

    assert parse_mapping(raw) == SAMPLE_MAPPING


def test_parse_mapping_skips_blanks_and_comments():
    raw = "# σχόλιο\n\n38.00.00  Ταμείο.Μετρητά\n70.00.00\tΕσοδα.Κοινόχρηστα\n"

    assert parse_mapping(raw) == {
        "38.00.00": "Ταμείο.Μετρητά",
        "70.00.00": "Εσοδα.Κοινόχρηστα",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("72.00", "72"),
        ("1500.00", "1.500"),
        ("37673.11", "37.673,11"),
        ("122.40", "122,40"),
        ("-95.40", "-95,40"),
    ],
)
def test_format_amount_uses_greek_notation_without_whole_decimals(value, expected):
    assert format_amount(Decimal(value)) == expected


def squeeze(text: str) -> list[str]:
    """Sample content with the column padding collapsed, so layout is ignored."""
    return [" ".join(line.split()) for line in text.split("\r\n")]


def test_build_journal_matches_the_reference_sample_block():
    accounts = {
        1: account(1, "33.90.01"),
        2: account(2, "33.90.02"),
        3: account(3, "33.90.03"),
        4: account(4, "33.90.04"),
        5: account(5, "33.90.05"),
        6: account(6, "70.00.00"),
    }
    transaction = SimpleNamespace(
        transaction_date=date(2022, 1, 19),
        reference="110",
        description="Για αγορά 500 λίτρα πετρέλαιο θέρμανσης",
        lines=[
            line(1, "122.40", 0),
            line(2, "95.40", 1),
            line(3, "145.80", 2),
            line(4, "72.00", 3),
            line(5, "164.40", 4),
            line(6, "-600.00", 5),
        ],
    )

    output = build_journal([transaction], accounts, SAMPLE_MAPPING)

    # Same content as the reference sample, ignoring its per-transaction padding.
    with Path("metatropi_example.txt").open(encoding="utf-8", newline="") as handle:
        sample = handle.read()
    assert squeeze(output) == squeeze(f"j-normal\r\n\r\n{sample.split('\r\n\r\n')[-2]}\r\n\r\n")
    # Columns are reserved file-wide: 23 for the longest account, 9 for the integer part.
    assert output.split("\r\n")[3:5] == [
        "  Χρεώστες.1-Νικολόπουλος        122,40",
        "  Χρεώστες.2-Καλυβιώτη            95,40",
    ]


def test_build_journal_omits_only_the_last_amount_and_signs_extra_credits():
    accounts = {1: account(1, "38.00.00"), 2: account(2, "33.90.01"), 3: account(3, "33.90.02")}
    transaction = SimpleNamespace(
        transaction_date=date(2026, 3, 4),
        reference=None,
        description="Δύο πιστώσεις",
        lines=[line(1, "100.00", 0), line(2, "-40.00", 1), line(3, "-60.00", 2)],
    )

    output = build_journal([transaction], accounts, SAMPLE_MAPPING)

    assert output.split("\r\n")[2:6] == [
        "2026-03-04 Δύο πιστώσεις",
        "  Ταμείο.Μετρητά                 100",
        "  Χρεώστες.1-Νικολόπουλος        -40",
        "  Χρεώστες.2-Καλυβιώτη",
    ]


def test_build_journal_refuses_when_an_account_has_no_mapping():
    accounts = {1: account(1, "38.00.00"), 2: account(2, "64.03.01")}
    transaction = SimpleNamespace(
        transaction_date=date(2026, 3, 4),
        reference=None,
        description="Αγορά",
        lines=[line(2, "50.00", 0), line(1, "-50.00", 1)],
    )

    with pytest.raises(MissingMappingError) as error:
        build_journal([transaction], accounts, SAMPLE_MAPPING)

    assert error.value.codes == ["64.03.01"]


def test_build_account_list_aligns_uneven_codes_and_round_trips():
    accounts = [
        account(1, "38.00.00", "Ταμείο μετρητά"),
        account(2, "33.00", "Απαιτήσεις  κοινοχρήστων "),
        account(3, "70.00.00", "Έσοδα κοινοχρήστων"),
    ]

    output = build_account_list(accounts)

    assert output.split("\r\n")[:3] == [
        "33.00     Απαιτήσεις κοινοχρήστων",
        "38.00.00  Ταμείο μετρητά",
        "70.00.00  Έσοδα κοινοχρήστων",
    ]
    assert parse_mapping(output) == {
        "33.00": "Απαιτήσεις κοινοχρήστων",
        "38.00.00": "Ταμείο μετρητά",
        "70.00.00": "Έσοδα κοινοχρήστων",
    }
