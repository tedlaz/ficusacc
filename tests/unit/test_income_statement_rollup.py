from datetime import date
from decimal import Decimal

from app.domain.types import AccountType
from app.infrastructure.database.models import AccountModel
from app.web import reports


def test_income_statement_hides_zero_and_rolls_up_parents(monkeypatch):
    parent = AccountModel(id=1, company_id=1, code="64", name="Έξοδα", account_type=AccountType.EXPENSE)
    child = AccountModel(id=2, company_id=1, code="64.00", name="Ενοίκια", account_type=AccountType.EXPENSE, parent_id=1)
    idle = AccountModel(id=3, company_id=1, code="64.01", name="Άδειος", account_type=AccountType.EXPENSE, parent_id=1)

    class Line:
        account_id, amount = 2, Decimal("100")

    class Txn:
        is_posted, lines = True, [Line()]

    class DB:
        def exec(self, _):
            return self

        def all(self):
            return [parent, child, idle]

    monkeypatch.setattr(reports, "transactions_between", lambda *a: [Txn()])
    data = reports.income_statement(DB(), 1, date(2026, 1, 1), date(2026, 1, 31))
    assert [(x.account.code, x.balance, x.is_summary, x.level) for x in data["expenses"]] == [
        ("64", Decimal("100"), True, 0), ("64.00", Decimal("100"), False, 1)]
    assert data["total_expenses"] == Decimal("100")
