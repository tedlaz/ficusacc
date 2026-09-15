"""Unit tests for the OLAP cube engine."""

from datetime import date
from decimal import Decimal

from sqlmodel import Session
from werkzeug.datastructures import MultiDict

from app.domain.types import AccountType
from app.infrastructure.database.models import AccountModel, TransactionLineModel, TransactionModel
from app.web import olap


def fact(when, amount, code="62.00", name="Rent", kind=AccountType.EXPENSE, tx=1, posted=True, user="Ted"):
    return olap.Fact(transaction_id=tx, transaction_date=when, amount=Decimal(amount), account_code=code,
                     account_name=name, account_type=kind, is_posted=posted, reference="", user=user)


SPEC = olap.CubeSpec(start=date(2026, 1, 1), end=date(2026, 12, 31))


def test_natural_measure_signs_by_account_type():
    facts = [
        fact(date(2026, 1, 5), "100", code="70.00", name="Sales", kind=AccountType.REVENUE, tx=1),
        fact(date(2026, 1, 5), "-100", code="70.00", name="Sales", kind=AccountType.REVENUE, tx=1),
        fact(date(2026, 1, 6), "40", tx=2),
    ]
    cube = olap.build_cube(facts, olap.CubeSpec(**{**SPEC.__dict__, "rows": ("account_type",),
                                                   "measures": ("natural", "debit", "credit", "transactions")}))
    by_type = {row.members[0].key: row for row in cube.rows}
    revenue = by_type["revenue"].cells[""]
    assert (revenue.debit, revenue.credit, revenue.natural) == (Decimal("100"), Decimal("100"), Decimal("0"))
    expense = by_type["expense"].cells[""]
    assert expense.natural == Decimal("40")
    assert cube.value(cube.total, olap.MEASURES["transactions"]) == Decimal("2")
    assert cube.value(cube.total, olap.MEASURES["debit"]) == Decimal("140")


def test_rows_columns_subtotals_and_chart_axis_swap():
    facts = [
        fact(date(2026, 1, 5), "10", code="62.00", tx=1),
        fact(date(2026, 2, 5), "20", code="62.01", name="Water", tx=2),
        fact(date(2026, 2, 5), "5", code="64.00", name="Fees", tx=3),
    ]
    spec = olap.CubeSpec(**{**SPEC.__dict__, "rows": ("account_group", "account"), "column": "month"})
    cube = olap.build_cube(facts, spec)

    assert [column.key for column in cube.columns] == ["2026-01", "2026-02"]
    levels = [(row.level, row.members[-1].key) for row in cube.rows]
    assert levels == [(0, "62"), (1, "62.00"), (1, "62.01"), (0, "64"), (1, "64.00")]
    group = cube.rows[0]
    assert not group.is_leaf
    assert group.cells[""].debit == Decimal("30")
    assert group.cells["2026-02"].debit == Decimal("20")
    assert cube.column_totals["2026-02"].debit == Decimal("25")

    # Month is time-like, so it becomes the x-axis even though it was chosen as the column.
    chart = cube.chart
    assert [category["key"] for category in chart["categories"]] == ["2026-01", "2026-02"]
    assert [series["key"] for series in chart["series"]] == ["62", "64"]
    assert chart["series"][0]["values"] == ["10", "20"]
    assert chart["series"][1]["values"] == ["0", "5"]


def test_top_n_folds_rest_into_other_and_value_sort():
    facts = [fact(date(2026, 1, 1), str(amount), code=f"62.{index:02d}", name=f"A{index}", tx=index)
             for index, amount in enumerate((5, 50, 20, 1, 7))]
    spec = olap.CubeSpec(**{**SPEC.__dict__, "rows": ("account",), "sort": "value", "limit": 2})
    cube = olap.build_cube(facts, spec)
    assert [row.members[0].label for row in cube.rows] == ["62.01 · A1", "62.02 · A2", olap.OTHER_LABEL]
    assert cube.rows[-1].cells[""].debit == Decimal("13")
    assert cube.total.debit == Decimal("83")


def test_time_dimensions_never_fold_and_chart_caps_series():
    facts = [fact(date(2026, month, 1), "1", code=f"6{month:02d}", tx=month) for month in range(1, 13)]
    spec = olap.CubeSpec(**{**SPEC.__dict__, "rows": ("month",), "column": "account_group", "limit": 3})
    cube = olap.build_cube(facts, spec)
    assert len(cube.rows) == 12
    assert len(cube.columns) == 3 + 1  # top 3 + Λοιπά
    assert cube.columns[-1].key == olap.OTHER_KEY

    spec = olap.CubeSpec(**{**SPEC.__dict__, "rows": ("month",), "column": "account_group"})
    chart = olap.build_cube(facts, spec).chart
    assert len(chart["series"]) == olap.MAX_CHART_SERIES
    assert chart["series"][-1]["key"] == olap.OTHER_KEY


def test_spec_from_args_sanitises_input():
    args = MultiDict([("row_dim", "month"), ("row_dim", "bogus"), ("row_dim", "month"), ("row_dim", "account"),
                      ("col_dim", "account"), ("measure", "nope"), ("chart_type", "pie"), ("limit", "x"),
                      ("account_type", "asset"), ("account_type", "zzz"), ("posted_only", "0")])
    spec = olap.CubeSpec.from_args(args, date(2026, 1, 1), date(2026, 1, 31))
    assert spec.rows == ("month", "account")
    assert spec.column is None  # already used as a row
    assert spec.measures == ("natural",)
    assert spec.chart == "bar"
    assert spec.limit == 0
    assert spec.account_types == ("asset",)
    assert spec.posted_only is False


def test_load_facts_applies_filters(app, seeded):
    user_id, company_id = seeded
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Cash", account_type="asset")
        rent = AccountModel(company_id=company_id, code="62.00", name="Rent", account_type="expense")
        db.add_all([cash, rent])
        db.flush()
        for when, posted in ((date(2026, 3, 1), True), (date(2026, 3, 2), False), (date(2025, 1, 1), True)):
            transaction = TransactionModel(company_id=company_id, created_by_id=user_id, transaction_date=when,
                                           description="t", is_posted=posted)
            db.add(transaction)
            db.flush()
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=rent.id, amount=Decimal("10")))
            db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash.id, amount=Decimal("-10")))
        db.commit()

        base = olap.CubeSpec(start=date(2026, 1, 1), end=date(2026, 12, 31))
        assert len(olap.load_facts(db, company_id, base)) == 2
        assert len(olap.load_facts(db, company_id, olap.CubeSpec(**{**base.__dict__, "posted_only": False}))) == 4
        assert len(olap.load_facts(db, company_id, olap.CubeSpec(**{**base.__dict__, "code_prefix": "62"}))) == 1
        expenses = olap.CubeSpec(**{**base.__dict__, "account_types": ("expense",)})
        facts = olap.load_facts(db, company_id, expenses)
        assert [item.user for item in facts] == ["Test Admin"]


def test_table_export_shape():
    facts = [fact(date(2026, 1, 5), "10", tx=1), fact(date(2026, 2, 5), "-4", tx=2)]
    spec = olap.CubeSpec(**{**SPEC.__dict__, "rows": ("month",), "column": "side", "measures": ("debit", "credit")})
    headers, rows = olap.cube_rows_as_table(olap.build_cube(facts, spec))
    assert headers == ["Μήνας", "Χρέωση · Χρεώσεις", "Χρέωση · Πιστώσεις", "Πίστωση · Χρεώσεις",
                       "Πίστωση · Πιστώσεις", "Σύνολο · Χρεώσεις", "Σύνολο · Πιστώσεις"]
    assert rows[0] == ["Ιαν 2026", "10.00", "0.00", "0.00", "0.00", "10.00", "0.00"]
    assert rows[-1] == ["Σύνολο", "10.00", "0.00", "0.00", "4.00", "10.00", "4.00"]


def test_pdf_embeds_a_chart_for_every_chart_type():
    import pytest

    from app.web import olap as olap_module
    from app.web.pdf_reports import build_report_pdf, find_fonts

    try:
        find_fonts()
    except RuntimeError:
        pytest.skip("no Unicode TTF font available for PDF rendering")

    class Company:
        name = "Δοκιμή"
        currency = "EUR"

    facts = [fact(date(2026, 1 + index % 6, 3), str((index + 1) * 11 * (-1 if index % 5 == 0 else 1)),
                  code=f"6{index % 4}.0{index % 3}", name=f"A{index}", tx=index) for index in range(30)]
    for chart in olap_module.CHART_TYPES:
        spec = olap.CubeSpec(**{**SPEC.__dict__, "rows": ("account_group", "account"), "column": "month",
                                "measures": ("natural", "lines"), "chart": chart, "limit": 3})
        content, filename = build_report_pdf("olap", olap.build_cube(facts, spec), Company())
        assert content.startswith(b"%PDF") and filename.endswith(".pdf"), chart


def test_group_labels_use_parent_names_when_present():
    plain = fact(date(2026, 1, 1), "1", code="64.00.01")
    assert olap.DIMENSIONS["account_group"].member_of(plain).label == "Ομάδα 64"
    assert olap.DIMENSIONS["account_subgroup"].member_of(plain).label == "Υποομάδα 64.00"
    named = olap.Fact(**{**plain.__dict__, "group_name": "Διάφορα έξοδα", "subgroup_name": "Έξοδα μεταφορών"})
    group = olap.DIMENSIONS["account_group"].member_of(named)
    assert (group.key, group.label) == ("64", "64 · Διάφορα έξοδα")
    assert olap.DIMENSIONS["account_subgroup"].member_of(named).label == "64.00 · Έξοδα μεταφορών"


def test_cube_names_groups_from_header_accounts(app, seeded):
    user_id, company_id = seeded
    with Session(app.extensions["sqlmodel_engine"]) as db:
        header = AccountModel(company_id=company_id, code="64", name="Διάφορα έξοδα", account_type="expense",
                              is_active=False)
        db.add(header)
        db.flush()
        sub = AccountModel(company_id=company_id, code="64.00", name="Έξοδα μεταφορών", account_type="expense",
                           parent_id=header.id)
        cash = AccountModel(company_id=company_id, code="38.00", name="Ταμείο", account_type="asset")
        db.add_all([sub, cash])
        db.flush()
        leaf = AccountModel(company_id=company_id, code="64.00.01", name="Ταξί", account_type="expense",
                            parent_id=sub.id)
        db.add(leaf)
        db.flush()
        transaction = TransactionModel(company_id=company_id, created_by_id=user_id, transaction_date=date(2026, 3, 1),
                                       description="t", is_posted=True)
        db.add(transaction)
        db.flush()
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=leaf.id, amount=Decimal("30")))
        db.add(TransactionLineModel(transaction_id=transaction.id, account_id=cash.id, amount=Decimal("-30")))
        db.commit()

        spec = olap.CubeSpec(start=date(2026, 1, 1), end=date(2026, 12, 31),
                             rows=("account_group", "account_subgroup"), account_types=("expense",))
        cube = olap.olap_cube(db, company_id, spec)
    assert [row.members[-1].label for row in cube.rows] == ["64 · Διάφορα έξοδα", "64.00 · Έξοδα μεταφορών"]
