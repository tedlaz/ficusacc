"""Unit tests for report calculations."""

from datetime import date, timedelta
from decimal import Decimal

from sqlmodel import Session

from app.infrastructure.database.models import AccountModel, TransactionLineModel, TransactionModel
from app.web import reports
from app.web.routes import nice_ceiling, stream_chart_data


def _post(db, company_id, user_id, when, debit, credit, amount, posted=True):
    transaction = TransactionModel(company_id=company_id, created_by_id=user_id, transaction_date=when,
                                   description="t", is_posted=posted)
    db.add(transaction)
    db.flush()
    db.add(TransactionLineModel(transaction_id=transaction.id, account_id=debit.id, amount=amount, line_order=0))
    db.add(TransactionLineModel(transaction_id=transaction.id, account_id=credit.id, amount=-amount, line_order=1))


def test_monthly_flows_window_signs_and_netting(app, seeded):
    user_id, company_id = seeded
    today = date.today()
    this_month = today.replace(day=1)
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Cash", account_type="asset")
        bank = AccountModel(company_id=company_id, code="38.03", name="Bank", account_type="asset")
        sales = AccountModel(company_id=company_id, code="70.00", name="Sales", account_type="revenue")
        rent = AccountModel(company_id=company_id, code="62.00", name="Rent", account_type="expense")
        db.add_all([cash, bank, sales, rent])
        db.flush()
        _post(db, company_id, user_id, this_month, cash, sales, Decimal("100"))
        _post(db, company_id, user_id, this_month, rent, cash, Decimal("40"))
        _post(db, company_id, user_id, this_month, bank, cash, Decimal("30"))          # transfer: no flow
        _post(db, company_id, user_id, this_month, cash, sales, Decimal("999"), posted=False)
        _post(db, company_id, user_id, reports.month_start(today, -13) + timedelta(days=2), cash, sales, Decimal("5"))
        _post(db, company_id, user_id, reports.month_start(today, -11), cash, sales, Decimal("7"))
        db.commit()

        result = reports.monthly_flows(db, company_id, today)

    assert len(result) == 12
    assert result[0].month == reports.month_start(today, -11)
    assert result[-1].month == this_month
    assert (result[-1].revenue, result[-1].expenses, result[-1].net) == (Decimal("100"), Decimal("40"), Decimal("60"))
    assert (result[-1].cash_in, result[-1].cash_out) == (Decimal("100"), Decimal("40"))
    assert result[0].revenue == Decimal("7")
    assert sum((item.revenue for item in result), Decimal("0")) == Decimal("107")


def test_nice_ceiling():
    assert nice_ceiling(Decimal("0")) == Decimal("1")
    assert nice_ceiling(Decimal("7")) == Decimal("7.5")
    assert nice_ceiling(Decimal("840.50")) == Decimal("1000")
    assert nice_ceiling(Decimal("1234")) == Decimal("1500")
    assert nice_ceiling(Decimal("1500")) == Decimal("1500")
    assert nice_ceiling(Decimal("0.4")) == Decimal("0.4")


def test_money_streams_merges_tail_and_balances_columns(app, seeded):
    user_id, company_id = seeded
    today = date.today()
    day = today.replace(day=1) + timedelta(days=2)
    with Session(app.extensions["sqlmodel_engine"]) as db:
        cash = AccountModel(company_id=company_id, code="38.00", name="Cash", account_type="asset")
        sales = AccountModel(company_id=company_id, code="70.00", name="Sales", account_type="revenue")
        expenses = [AccountModel(company_id=company_id, code=f"6{i}.00", name=f"Exp{i}", account_type="expense")
                    for i in range(10)]
        db.add_all([cash, sales, *expenses])
        db.flush()
        _post(db, company_id, user_id, day, cash, sales, Decimal("100"))
        for index, account in enumerate(expenses):
            _post(db, company_id, user_id, day, account, cash, Decimal(100 - index))       # 100, 99, ... 91
        _post(db, company_id, user_id, day, expenses[0], cash, Decimal("5"), posted=False)
        _post(db, company_id, user_id, reports.month_start(today, -12), expenses[0], cash, Decimal("1000"))
        db.commit()
        streams = reports.money_streams(db, company_id, today)

    targets = streams["targets"]
    assert [node.kind for node in targets] == ["expense"] * 8 + ["other"]
    assert targets[0].amount == Decimal("100")
    assert targets[-1].label == "Λοιπά έξοδα"
    assert targets[-1].amount == Decimal("92") + Decimal("91")
    assert targets[-1].detail == ["68.00 · Exp8", "69.00 · Exp9"]
    assert streams["total_expenses"] == Decimal(sum(range(91, 101)))
    assert streams["sources"][-1].kind == "deficit"
    assert streams["sources"][-1].amount == streams["total_expenses"] - Decimal("100")
    assert streams["total"] == streams["total_expenses"]

    chart = stream_chart_data(streams)
    left = sum(item["h"] for item in chart["sources"])
    right = sum(item["h"] for item in chart["targets"])
    assert abs(left - right) < 0.1  # both columns use one scale, so node heights sum equally
    assert all(item["y"] >= 24 and item["y"] + item["h"] <= chart["height"] - 24 for item in chart["targets"])
    assert len(chart["links"]) == len(chart["sources"]) + len(chart["targets"])
    assert all(link["path"].startswith("M ") and link["path"].endswith(" Z") for link in chart["links"])
    assert abs(chart["band"]["h"] - right) < 0.1


def test_page_window_keeps_ends_and_neighbours():
    from app.web.routes import page_window

    assert page_window(1, 1) == [1]
    assert page_window(1, 5) == [1, 2, 3, 4, 5]
    assert page_window(1, 20) == [1, 2, 3, None, 20]
    assert page_window(10, 20) == [1, None, 8, 9, 10, 11, 12, None, 20]
    assert page_window(4, 20) == [1, 2, 3, 4, 5, 6, None, 20]  # a one-page gap is shown as the page
    assert page_window(20, 20) == [1, None, 18, 19, 20]
