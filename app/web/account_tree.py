"""Account hierarchy helpers: dotted-code prefixes and the parent_id chain.

Reports group accounts by code prefix ("64", "64.00"). A header account linked as the parent
of its children names that prefix, so reports read "64 · Διάφορα έξοδα" instead of "Ομάδα 64".
Pure Python (no Flask, no session) so it can be shared by olap.py and reports.py.
"""

from __future__ import annotations

from collections.abc import Iterable


def code_prefix(code: str, depth: int) -> str:
    return ".".join(code.split(".")[:depth])


def code_depth(code: str) -> int:
    return len(code.split("."))


def ancestors(account, by_id: dict) -> list:
    """Parent chain nearest-first; stops on a missing parent or a cycle."""
    chain = []
    seen = {account.id}
    current = by_id.get(account.parent_id) if account.parent_id is not None else None
    while current is not None and current.id not in seen:
        chain.append(current)
        seen.add(current.id)
        current = by_id.get(current.parent_id) if current.parent_id is not None else None
    return chain


def prefix_names(accounts: Iterable) -> dict[str, str]:
    """Map every code prefix to a display name.

    An account names its own code; an ancestor also names the descendant's prefix at the
    ancestor's own depth (a one-segment parent is a level-1 group), so the parent's name wins
    even if its code is not the exact prefix. Inactive headers still count. Accounts are
    processed in code order so the result is deterministic when the data is inconsistent.
    """
    ordered = sorted(accounts, key=lambda account: account.code)
    by_id = {account.id: account for account in ordered}
    names = {account.code: account.name for account in ordered}
    for account in ordered:
        depth = code_depth(account.code)
        for ancestor in ancestors(account, by_id):
            names[ancestor.code] = ancestor.name
            level = code_depth(ancestor.code)
            if level < depth:
                names[code_prefix(account.code, level)] = ancestor.name
    return names


def suggest_parent(code: str, accounts: Iterable, exclude_id: int | None = None):
    """The existing account with the longest exact dotted prefix of ``code`` ("64.00" before "64")."""
    by_code = {account.code: account for account in accounts if account.id != exclude_id}
    for depth in range(code_depth(code) - 1, 0, -1):
        candidate = by_code.get(code_prefix(code, depth))
        if candidate is not None:
            return candidate
    return None


def link_parents_by_prefix(accounts: list) -> int:
    """Fill in ``parent_id`` for accounts that have none; returns how many were linked."""
    linked = 0
    for account in accounts:
        if account.parent_id is not None:
            continue
        parent = suggest_parent(account.code, accounts, exclude_id=account.id)
        if parent is not None and parent.id is not None:
            account.parent_id = parent.id
            linked += 1
    return linked
