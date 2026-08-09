"""Unit tests for PDF report presentation structures."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.web.pdf_reports import journal_article_content


def test_journal_article_groups_description_above_account_rows():
    transaction = SimpleNamespace(
        transaction_date=date(2026, 1, 15),
        description="Αγορά αναλωσίμων",
        reference="INV-15",
        is_posted=True,
    )
    debit_account = SimpleNamespace(code="64.00.01", name="Αναλώσιμα")
    credit_account = SimpleNamespace(code="50.00.01", name="Προμηθευτής")
    company = SimpleNamespace(currency="EUR")
    entry = {
        "transaction": transaction,
        "debits": [(debit_account, Decimal("100"))],
        "credits": [(credit_account, Decimal("100"))],
    }

    title, rows = journal_article_content(entry, company)

    assert title == "15/01/2026 · Αγορά αναλωσίμων · Σχετικό: INV-15 · Οριστική"
    assert rows == [
        ("64.00.01 · Αναλώσιμα", "100,00 €", "—"),
        ("50.00.01 · Προμηθευτής", "—", "100,00 €"),
    ]
    assert all(transaction.description not in cell for row in rows for cell in row)
