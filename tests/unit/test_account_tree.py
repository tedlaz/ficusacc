"""Unit tests for account hierarchy helpers (pure objects, no database)."""

from app.infrastructure.database.models import AccountModel
from app.web import account_tree


def acc(id, code, name, parent_id=None):
    return AccountModel(id=id, company_id=1, code=code, name=name, account_type="expense", parent_id=parent_id)


def test_prefix_names_from_codes_and_parent_chain():
    accounts = [
        acc(1, "64", "Διάφορα έξοδα"),
        acc(2, "64.00", "Έξοδα μεταφορών", parent_id=1),
        acc(3, "64.00.01", "Ταξί", parent_id=2),
        acc(4, "62.00.01", "Ενοίκιο"),  # no headers at all
    ]
    names = account_tree.prefix_names(accounts)
    assert names["64"] == "Διάφορα έξοδα"
    assert names["64.00"] == "Έξοδα μεταφορών"
    assert names["64.00.01"] == "Ταξί"
    assert "62" not in names and "62.00" not in names


def test_parent_names_prefix_at_its_own_level_even_when_codes_differ():
    accounts = [acc(1, "6400X", "Διάφορα έξοδα"), acc(2, "64.00.01", "Ταξί", parent_id=1)]
    names = account_tree.prefix_names(accounts)
    assert names["64"] == "Διάφορα έξοδα"
    assert "64.00" not in names  # a one-segment parent is a level-1 group, not a subgroup


def test_skipping_a_level_does_not_name_the_missing_subgroup():
    accounts = [acc(1, "38", "Χρηματικά διαθέσιμα"), acc(2, "38.00.01", "Ταμείο", parent_id=1)]
    names = account_tree.prefix_names(accounts)
    assert names["38"] == "Χρηματικά διαθέσιμα"
    assert "38.00" not in names


def test_cycles_and_missing_parents_are_harmless():
    a, b = acc(1, "10", "A", parent_id=2), acc(2, "10.00", "B", parent_id=1)
    orphan = acc(3, "20.00.01", "C", parent_id=999)
    names = account_tree.prefix_names([a, b, orphan])
    assert names["10"] == "A" and names["10.00"] == "B"
    assert account_tree.ancestors(orphan, {1: a, 2: b, 3: orphan}) == []


def test_suggest_parent_prefers_the_longest_prefix():
    accounts = [acc(1, "64", "Διάφορα"), acc(2, "64.00", "Μεταφορές"), acc(3, "64.00.01", "Ταξί")]
    assert account_tree.suggest_parent("64.00.01", accounts, exclude_id=3).code == "64.00"
    assert account_tree.suggest_parent("64.01.02", accounts).code == "64"
    assert account_tree.suggest_parent("1000", accounts) is None
    assert account_tree.suggest_parent("64.00", accounts, exclude_id=2).code == "64"


def test_link_parents_by_prefix_is_order_independent():
    accounts = [acc(3, "64.00.01", "Ταξί"), acc(1, "64", "Διάφορα"), acc(2, "64.00", "Μεταφορές")]
    assert account_tree.link_parents_by_prefix(accounts) == 2
    assert {a.code: a.parent_id for a in accounts} == {"64.00.01": 2, "64": None, "64.00": 1}
