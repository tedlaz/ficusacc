"""Unit tests for the plain-text journal import (parser and account resolver)."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.types import AccountType
from app.web.journal_export import format_amount
from app.web.journal_import import (
    AccountResolver,
    ExistingAccount,
    ResolveError,
    balances_by_code,
    balances_from_text,
    parse_amount,
    parse_chart,
    parse_journal,
    read_mapping,
    render_plan,
)

SAMPLE = """j-normal\r
\r
2021-01-04 {433043041} Ενοίκιο Μακρής ΙΑΝΟΥΑΡΙΟΣ 2021\r
  Εξοδα.Κων.Σπουδές.Σπίτι.Ενοίκιο  150,00\r
  Εξοδα.Τραπεζικά.Προμήθειες         1,00\r
  Ταμείο.Τράπεζες.Winbank\r
\r
# a comment line\r
@ 2021-01-31 Ταμείο.Τράπεζες.Winbank 1.000,00\r
2021-12-08 Πόπη γαστροσκόπιση\r
  Εξοδα.Υγεία.Γιατροί       410\r
  Ταμείο.Τράπεζες.Winbank  -160  # Αμοιβή Ευρωκλινικής\r
  Ταμείο.Μετρητά.Τσέπη     -250#Αμοιβή γιατρού\r
   \r
2020-04-29 MyMarket\r
  Εξοδα.Φαγητό.Τρόφιμα     1.187,49\r
  Ταμείο.Μετρητά.Κουπόνια -170,00\r
  Ταμείο.Τράπεζες.Αττικής\r
"""


@pytest.mark.parametrize(
    "raw, expected",
    [("1.800", "1800.00"), ("9,6", "9.60"), ("-2.000", "-2000.00"), ("13.000,00", "13000.00"),
     ("20", "20.00"), ("-902,46", "-902.46")],
)
def test_parse_amount_reads_greek_notation(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("value", ["37673.11", "1800", "0.5", "-24.58"])
def test_parse_amount_inverts_format_amount(value):
    assert parse_amount(format_amount(Decimal(value))) == Decimal(value)


@pytest.mark.parametrize("raw", ["12,,50", "1,2,3", "abc", "1.00.0"])
def test_parse_amount_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_parse_journal_sample():
    transactions, errors = parse_journal(SAMPLE, "2021")
    assert errors == []
    assert [t.date for t in transactions] == [date(2021, 1, 4), date(2021, 12, 8), date(2020, 4, 29)]

    first = transactions[0]
    assert first.reference == "433043041"
    assert first.description == "Ενοίκιο Μακρής ΙΑΝΟΥΑΡΙΟΣ 2021"
    assert first.source == "2021:3"
    assert first.tag == "book_ted:2021:3"
    assert [(l.account, l.amount) for l in first.lines] == [
        ("Εξοδα.Κων.Σπουδές.Σπίτι.Ενοίκιο", Decimal("150.00")),
        ("Εξοδα.Τραπεζικά.Προμήθειες", Decimal("1.00")),
        ("Ταμείο.Τράπεζες.Winbank", Decimal("-151.00")),
    ]

    second = transactions[1]
    assert second.reference == ""
    assert [l.comment for l in second.lines] == ["", "Αμοιβή Ευρωκλινικής", "Αμοιβή γιατρού"]
    assert second.total() == 0

    third = transactions[2]
    assert third.lines[-1].amount == Decimal("-1017.49")


def test_parse_journal_requires_header():
    transactions, errors = parse_journal("2021-01-01 x\n  A 1\n  B\n", "f")
    assert transactions == []
    assert errors == ["f:1: λείπει η επικεφαλίδα j-normal"]


def test_parse_journal_reports_and_skips_bad_transactions():
    text = """j-normal

2023-06-03 two balancing legs
  Εξοδα.Α  10
  Ταμείο.Β
  Εξοδα.Γ  5
  Ταμείο.Δ

2023-13-01 bad date
  Εξοδα.Α  10
  Ταμείο.Β

2023-06-04 unbalanced
  Εξοδα.Α  10
  Ταμείο.Β  -5

2023-06-05 bad amount
  Εξοδα.Α  12,,50
  Ταμείο.Β

2023-06-06 fine
  Εξοδα.Α  10
  Ταμείο.Β
"""
    transactions, errors = parse_journal(text, "202306")
    assert [t.description for t in transactions] == ["fine"]
    assert errors == [
        "202306:3: περισσότερες από μία γραμμές χωρίς ποσό",
        "202306:9: μη έγκυρη ημερομηνία '2023-13-01'",
        "202306:10: γραμμή χωρίς εγγραφή",
        "202306:11: γραμμή χωρίς εγγραφή",
        "202306:13: δεν ισοσκελίζει (5.00)",
        "202306:18: μη έγκυρο ποσό '12,,50'",
        "202306:19: γραμμή χωρίς εγγραφή",
    ]


def test_parse_chart_maps_categories_to_account_types():
    chart = parse_chart("@ Ted\n\n> Εξοδα        ejoda\n> Ταμείο  apaitiseis\n> Πιστωτές ypoxreoseis\n+ Εξοδα.Α\n")
    assert chart == {
        "Εξοδα": AccountType.EXPENSE,
        "Ταμείο": AccountType.ASSET,
        "Πιστωτές": AccountType.LIABILITY,
    }
    with pytest.raises(ValueError):
        parse_chart("> Εξοδα  whatever\n")


# Resolver


def existing(code, name, kind=AccountType.EXPENSE, parent=None, active=True, description=None):
    return ExistingAccount(code, name, kind, parent, active, description)


SPITI = [
    existing("33", "ΧΡΕΩΣΤΕΣ", AccountType.ASSET, active=False),
    existing("33.01", "Χρεώστες κοινόχρηστα", AccountType.ASSET, "33"),
    existing("38", "ΜΕΤΡΗΤΑ", AccountType.ASSET, active=False),
    existing("38.00", "ΤΑΜΕΙΟ", AccountType.ASSET, "38", active=False),
    existing("38.00.00", "Ταμείο μετρητά", AccountType.ASSET, "38.00"),
    existing("50", "ΥΠΟΧΡΕΩΣΕΙΣ", AccountType.LIABILITY, active=False),
    existing("64", "ΕΞΟΔΑ", active=False),
    existing("64.10", "ΥΓΕΙΑ", parent="64", active=False),
    existing("64.10.02", "Οδοντίατροι", parent="64.10"),
    existing("64.11", "ΔΙΑΤΡΟΦΗ", parent="64", active=False),
    existing("64.11.04", "Φαγητό έξω", parent="64.11"),
    existing("73", "ΕΣΟΔΑ", AccountType.REVENUE, active=False),
]
CHART = {"Εξοδα": AccountType.EXPENSE, "Εσοδα": AccountType.REVENUE, "Ταμείο": AccountType.ASSET,
         "Χρεώστες": AccountType.ASSET, "Πάγια": AccountType.ASSET, "Πιστωτές": AccountType.LIABILITY}


def test_exact_mapping_uses_existing_code_without_creating():
    resolver = AccountResolver(SPITI, {"Ταμείο.Μετρητά.Τσέπη": "38.00.00"}, CHART)
    assert resolver.resolve("Ταμείο.Μετρητά.Τσέπη") == "38.00.00"
    assert resolver.created == []


def test_mapping_to_unknown_code_is_an_error():
    with pytest.raises(ResolveError):
        AccountResolver(SPITI, {"Ταμείο.Μετρητά.Τσέπη": "99.99"}, CHART)


def test_wildcard_mapping_folds_descendants_onto_one_code():
    resolver = AccountResolver(SPITI, {"Εξοδα.Υγεία.Οδοντίατροι.*": "64.10.02"}, CHART)
    assert resolver.resolve("Εξοδα.Υγεία.Οδοντίατροι.Κορίνα") == "64.10.02"
    assert resolver.resolve("Εξοδα.Υγεία.Οδοντίατροι.Εφη") == "64.10.02"
    assert resolver.created == []


def test_prefix_mapping_allocates_children_under_that_code():
    resolver = AccountResolver(SPITI, {"Εξοδα.Φαγητό": "64.11"}, CHART)
    assert resolver.resolve("Εξοδα.Φαγητό.Γλυκά") == "64.11.05"  # next after the existing 64.11.04
    assert resolver.resolve("Εξοδα.Φαγητό.Delivery") == "64.11.06"
    planned = {p.code: p for p in resolver.created}
    assert planned["64.11.05"].name == "Γλυκά"
    assert planned["64.11.05"].parent_code == "64.11"
    assert planned["64.11.05"].is_active is True
    assert planned["64.11.05"].dotted == "Εξοδα.Φαγητό.Γλυκά"
    assert planned["64.11.05"].account_type == AccountType.EXPENSE


def test_unmapped_name_creates_headers_under_the_root_default():
    resolver = AccountResolver(SPITI, {}, CHART)
    assert resolver.resolve("Εξοδα.Κων.Σπουδές.Σπίτι.Ενοίκιο") == "64.12.01.01.01"
    assert resolver.resolve("Εξοδα.Κων.Σπουδές.Σπίτι.ΔΕΗ") == "64.12.01.01.02"
    assert resolver.resolve("Εξοδα.Κων.Βιβλία") == "64.12.02"
    codes = [(p.code, p.name, p.is_active, p.parent_code) for p in resolver.created]
    assert codes == [
        ("64.12", "Κων", False, "64"),
        ("64.12.01", "Σπουδές", False, "64.12"),
        ("64.12.01.01", "Σπίτι", False, "64.12.01"),
        ("64.12.01.01.01", "Ενοίκιο", True, "64.12.01.01"),
        ("64.12.01.01.02", "ΔΕΗ", True, "64.12.01.01"),
        ("64.12.02", "Βιβλία", True, "64.12"),
    ]
    assert all(len(code) <= 20 for code, *_ in codes)


def test_missing_root_header_is_created_with_the_right_type():
    resolver = AccountResolver(SPITI, {}, CHART)
    assert resolver.resolve("Πάγια.Αυτοκίνητα.Yaris") == "12.01.01"
    assert resolver.resolve("Πιστωτές.Βούλα.ΠρόστιμοΕφορίας") == "50.01.01.01"
    by_code = {p.code: p for p in resolver.created}
    assert by_code["12"].name == "ΠΑΓΙΑ" and by_code["12"].account_type == AccountType.ASSET
    assert by_code["12"].parent_code is None and by_code["12"].is_active is False
    assert by_code["50.01"].parent_code == "50"
    assert by_code["50.01.01.01"].account_type == AccountType.LIABILITY


def test_unknown_root_is_an_error():
    with pytest.raises(ResolveError):
        AccountResolver(SPITI, {}, CHART).resolve("Λοιπά.Κάτι")


def test_tagged_accounts_make_reruns_idempotent():
    tagged = SPITI + [
        existing("64.12", "Κων", parent="64", active=False, description="book_ted: Εξοδα.Κων"),
        existing("64.12.03", "Βιβλία", parent="64.12", description="book_ted: Εξοδα.Κων.Βιβλία"),
    ]
    resolver = AccountResolver(tagged, {}, CHART)
    assert resolver.resolve("Εξοδα.Κων.Βιβλία") == "64.12.03"
    assert resolver.resolve("Εξοδα.Κων.Δώρα") == "64.12.04"
    assert [p.code for p in resolver.created] == ["64.12.04"]


def test_render_plan_is_readable_back_as_a_mapping():
    resolver = AccountResolver(SPITI, {"Ταμείο.Μετρητά.Τσέπη": "38.00.00"}, CHART)
    resolver.resolve("Ταμείο.Μετρητά.Τσέπη")
    resolver.resolve("Εξοδα.Δώρα.Χαρά")
    text = render_plan(resolver)
    assert text.splitlines() == [
        "Εξοδα.Δώρα.Χαρά       64.12.01  # NEW",
        "Ταμείο.Μετρητά.Τσέπη  38.00.00",
    ]
    assert read_mapping(text) == {"Εξοδα.Δώρα.Χαρά": "64.12.01", "Ταμείο.Μετρητά.Τσέπη": "38.00.00"}


def test_balances_from_text_fold_onto_codes():
    transactions, _ = parse_journal(SAMPLE, "2021")
    totals = balances_from_text(transactions, date(2021, 6, 30))
    assert totals["Ταμείο.Τράπεζες.Winbank"] == Decimal("-151.00")
    assert totals["Ταμείο.Τράπεζες.Αττικής"] == Decimal("-1017.49")
    assert "Εξοδα.Υγεία.Γιατροί" not in totals  # dated after the cut-off
    resolved = {name: "38.01" if name.startswith("Ταμείο") else "64.99" for name in totals}
    folded = balances_by_code(totals, resolved)
    assert folded["38.01"] == Decimal("-151.00") - Decimal("1017.49") - Decimal("170.00")
    assert folded["64.99"] == Decimal("151.00") + Decimal("1187.49")
