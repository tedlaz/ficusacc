"""Plain-text journal import from the `j-normal` ledger format (the inverse of journal_export).

Pure Python: no Flask, no session. The parser follows the grammar of the rhomeaccount viewer
(`core/src/parser_text.rs`), the resolver turns dotted account names into codes of this app's
chart, and the balance helpers let the CLI reconcile the database against the text after import.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.domain.types import AccountType
from app.web import account_tree
from app.web.journal_export import parse_mapping

JOURNAL_HEADERS = {"j-open", "j-normal", "j-close"}
SEPARATOR = "."
TAG_PREFIX = "book_ted:"
ACCOUNT_TAG_PREFIX = "book_ted: "
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
REFERENCE_RE = re.compile(r"\{([^}]*)\}")
AMOUNT_RE = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")

# Category keywords of the `000` chart file -> account types of this app.
CATEGORY_TYPES = {
    "ejoda": AccountType.EXPENSE,
    "esoda": AccountType.REVENUE,
    "pagia": AccountType.ASSET,
    "apothemata": AccountType.ASSET,
    "apaitiseis": AccountType.ASSET,
    "kefalaio": AccountType.EQUITY,
    "ypoxreoseis": AccountType.LIABILITY,
    "anorgana": AccountType.EXPENSE,
    "fpa": AccountType.ASSET,
}

# Where an unmapped root class lands in the SPITI chart; (code, header name, type).
ROOT_DEFAULTS = {
    "Εξοδα": ("64", "ΕΞΟΔΑ", AccountType.EXPENSE),
    "Εσοδα": ("73", "ΕΣΟΔΑ", AccountType.REVENUE),
    "Ταμείο": ("38", "ΜΕΤΡΗΤΑ", AccountType.ASSET),
    "Χρεώστες": ("33", "ΧΡΕΩΣΤΕΣ", AccountType.ASSET),
    "Πάγια": ("12", "ΠΑΓΙΑ", AccountType.ASSET),
    "Πιστωτές": ("50.01", "ΠΙΣΤΩΤΕΣ", AccountType.LIABILITY),
}


@dataclass
class ParsedLine:
    account: str
    amount: Decimal | None  # None until the balancing leg is filled in
    comment: str = ""


@dataclass
class ParsedTransaction:
    source: str  # "file:line" of the header
    date: date
    description: str
    reference: str
    lines: list[ParsedLine] = field(default_factory=list)

    @property
    def tag(self) -> str:
        return f"{TAG_PREFIX}{self.source}"

    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines if line.amount is not None), Decimal(0))


def parse_amount(raw: str) -> Decimal:
    """Greek notation to Decimal: `1.800,50` -> 1800.50, `9,6` -> 9.6, `-2.000` -> -2000."""
    text = raw.strip()
    if not AMOUNT_RE.match(text):
        raise ValueError(f"Μη έγκυρο ποσό: {raw!r}")
    try:
        return Decimal(text.replace(".", "").replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise ValueError(f"Μη έγκυρο ποσό: {raw!r}") from error


def parse_chart(text: str) -> dict[str, AccountType]:
    """Root class -> account type from the `> root category` lines of the `000` file."""
    chart: dict[str, AccountType] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0] == ">":
            if parts[2] not in CATEGORY_TYPES:
                raise ValueError(f"Άγνωστη κατηγορία {parts[2]!r} για {parts[1]}")
            chart[parts[1]] = CATEGORY_TYPES[parts[2]]
    return chart


def _split_detail(raw: str) -> tuple[str, str | None, str]:
    """`  Account  amount # comment` -> (account, amount text or None, comment)."""
    body, _, comment = raw.partition("#")
    tokens = body.split()
    account = tokens[0] if tokens else ""
    amount = tokens[1] if len(tokens) > 1 else None
    return account, amount, " ".join(comment.split())


def _finish(transaction: ParsedTransaction | None, errors: list[str], out: list[ParsedTransaction]):
    if transaction is None:
        return
    if len(transaction.lines) < 2:
        errors.append(f"{transaction.source}: λιγότερες από 2 γραμμές")
        return
    balancing = [line for line in transaction.lines if line.amount is None]
    if len(balancing) > 1:
        errors.append(f"{transaction.source}: περισσότερες από μία γραμμές χωρίς ποσό")
        return
    if balancing:
        balancing[0].amount = -transaction.total()
    if transaction.total() != 0:
        errors.append(f"{transaction.source}: δεν ισοσκελίζει ({transaction.total()})")
        return
    out.append(transaction)


def parse_journal(text: str, source_name: str) -> tuple[list[ParsedTransaction], list[str]]:
    """Parse one journal file; errors carry `file:line` and skip only the affected transaction."""
    transactions: list[ParsedTransaction] = []
    errors: list[str] = []
    lines = text.replace("\r", "").split("\n")
    header_seen = False
    current: ParsedTransaction | None = None
    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not header_seen:
            if not stripped:
                continue
            if stripped not in JOURNAL_HEADERS:
                return [], [f"{source_name}:{number}: λείπει η επικεφαλίδα j-normal"]
            header_seen = True
            continue
        if len(stripped) < 4 or stripped.startswith(("#", "@")):
            continue
        where = f"{source_name}:{number}"
        if DATE_RE.match(raw):
            _finish(current, errors, transactions)
            current = None
            date_text, _, rest = raw.partition(" ")
            try:
                when = date.fromisoformat(date_text)
            except ValueError:
                errors.append(f"{where}: μη έγκυρη ημερομηνία {date_text!r}")
                continue
            reference = ""
            match = REFERENCE_RE.search(rest)
            if match:
                reference = match.group(1).strip()
                rest = rest[: match.start()] + rest[match.end():]
            current = ParsedTransaction(where, when, " ".join(rest.split()), reference)
        elif raw.startswith("  "):
            if current is None:
                errors.append(f"{where}: γραμμή χωρίς εγγραφή")
                continue
            account, amount_text, comment = _split_detail(raw)
            if not account:
                continue
            amount = None
            if amount_text is not None:
                try:
                    amount = parse_amount(amount_text)
                except ValueError:
                    errors.append(f"{where}: μη έγκυρο ποσό {amount_text!r}")
                    current = None
                    continue
            current.lines.append(ParsedLine(account, amount, comment))
        else:
            errors.append(f"{where}: μη αναγνωρίσιμη γραμμή")
    _finish(current, errors, transactions)
    return transactions, errors


# Account resolution


@dataclass
class ExistingAccount:
    code: str
    name: str
    account_type: AccountType
    parent_code: str | None
    is_active: bool
    description: str | None = None


@dataclass
class PlannedAccount:
    code: str
    name: str
    account_type: AccountType
    parent_code: str | None
    is_active: bool
    dotted: str  # the source dotted name (full path for leaves, prefix for headers)


class ResolveError(Exception):
    pass


class AccountResolver:
    """Map dotted ledger names to codes, creating what the mapping does not cover.

    Resolution order for a dotted name: an account already tagged with it (re-runs), an exact
    mapping line, a `Prefix.*` mapping line (folds every descendant onto one code), the longest
    mapped prefix, then the root default. Unmapped tail segments are allocated under that
    anchor: intermediate segments as inactive headers, the leaf active.
    """

    def __init__(self, existing: list[ExistingAccount], mapping: dict[str, str],
                 chart: dict[str, AccountType]):
        self.by_code: dict[str, ExistingAccount | PlannedAccount] = {a.code: a for a in existing}
        self.mapping = mapping
        self.chart = chart
        self.tagged: dict[str, str] = {
            a.description[len(ACCOUNT_TAG_PREFIX):]: a.code
            for a in existing
            if a.description and a.description.startswith(ACCOUNT_TAG_PREFIX)
        }
        self.created: list[PlannedAccount] = []
        self.resolved: dict[str, str] = {}
        for dotted, code in mapping.items():
            if code not in self.by_code:
                raise ResolveError(f"Η αντιστοίχιση {dotted} -> {code} δείχνει σε ανύπαρκτο κωδικό")

    def resolve(self, dotted: str) -> str:
        if dotted in self.resolved:
            return self.resolved[dotted]
        if dotted in self.tagged:
            code = self.tagged[dotted]
        elif dotted in self.mapping:
            code = self.mapping[dotted]
        elif (folded := self._folded(dotted)) is not None:
            code = folded
        else:
            code = self._allocate(dotted)
        self.resolved[dotted] = code
        return code

    def _folded(self, dotted: str) -> str | None:
        segments = dotted.split(SEPARATOR)
        for depth in range(len(segments) - 1, 0, -1):
            wildcard = SEPARATOR.join(segments[:depth]) + SEPARATOR + "*"
            if wildcard in self.mapping:
                return self.mapping[wildcard]
        return None

    def _anchor(self, dotted: str) -> tuple[str, list[str]]:
        """Nearest mapped/tagged/default ancestor and the segments still to allocate."""
        segments = dotted.split(SEPARATOR)
        for depth in range(len(segments) - 1, 0, -1):
            prefix = SEPARATOR.join(segments[:depth])
            if prefix in self.tagged:
                return self.tagged[prefix], segments[depth:]
            if prefix in self.mapping:
                return self.mapping[prefix], segments[depth:]
        root = segments[0]
        if root not in ROOT_DEFAULTS:
            raise ResolveError(f"Άγνωστη ρίζα λογαριασμού {root!r} ({dotted})")
        code, name, kind = ROOT_DEFAULTS[root]
        if code not in self.by_code:
            parent = next(
                (
                    account_tree.code_prefix(code, depth)
                    for depth in range(account_tree.code_depth(code) - 1, 0, -1)
                    if account_tree.code_prefix(code, depth) in self.by_code
                ),
                None,
            )
            self._create(code, name, kind, parent, False, root)
        return code, segments[1:]

    def _allocate(self, dotted: str) -> str:
        anchor, tail = self._anchor(dotted)
        kind = self._type_for(dotted, anchor)
        parent = anchor
        walked = dotted.split(SEPARATOR)[: len(dotted.split(SEPARATOR)) - len(tail)]
        for index, segment in enumerate(tail):
            walked.append(segment)
            path = SEPARATOR.join(walked)
            is_leaf = index == len(tail) - 1
            if path in self.tagged:
                parent = self.tagged[path]
                continue
            code = self._next_code(parent)
            self._create(code, segment, kind, parent, is_leaf, path)
            parent = code
        return parent

    def _type_for(self, dotted: str, anchor: str) -> AccountType:
        root = dotted.split(SEPARATOR)[0]
        if root in self.chart:
            return self.chart[root]
        if root in ROOT_DEFAULTS:
            return ROOT_DEFAULTS[root][2]
        return self.by_code[anchor].account_type

    def _next_code(self, parent: str) -> str:
        depth = account_tree.code_depth(parent) + 1
        used = [
            int(code.split(SEPARATOR)[-1])
            for code in self.by_code
            if account_tree.code_depth(code) == depth
            and account_tree.code_prefix(code, depth - 1) == parent
            and code.split(SEPARATOR)[-1].isdigit()
        ]
        suffix = max(used, default=0) + 1
        if suffix > 99:
            raise ResolveError(f"Δεν χωρούν άλλοι λογαριασμοί κάτω από {parent}")
        return f"{parent}{SEPARATOR}{suffix:02d}"

    def _create(self, code, name, kind, parent_code, is_active, dotted) -> PlannedAccount:
        planned = PlannedAccount(code, name, kind, parent_code, is_active, dotted)
        self.by_code[code] = planned
        self.tagged[dotted] = code
        self.created.append(planned)
        return planned


def read_mapping(text: str) -> dict[str, str]:
    """`Dotted.Name  code` lines; trailing `# ...` comments (as render_plan writes) are dropped."""
    return parse_mapping("\n".join(line.partition("#")[0] for line in text.splitlines()))


def render_plan(resolver: AccountResolver) -> str:
    """Mapping-file syntax (`Dotted.Name  code`) with a NEW marker in a trailing comment."""
    rows = sorted(resolver.resolved.items())
    if not rows:
        return ""
    width = max(len(dotted) for dotted, _ in rows)
    new_codes = {planned.code for planned in resolver.created}
    lines = []
    for dotted, code in rows:
        marker = "  # NEW" if code in new_codes else ""
        lines.append(f"{dotted.ljust(width)}  {code}{marker}")
    return "\n".join(lines) + "\n"


# Reconciliation helpers


def balances_from_text(transactions: list[ParsedTransaction], until: date) -> dict[str, Decimal]:
    """Dotted account -> net amount (debits positive) of everything dated on or before `until`."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for transaction in transactions:
        if transaction.date > until:
            continue
        for line in transaction.lines:
            totals[line.account] += line.amount or Decimal(0)
    return dict(totals)


def balances_by_code(balances: dict[str, Decimal], resolved: dict[str, str]) -> dict[str, Decimal]:
    """Fold dotted balances onto the app codes they resolve to (several names may share one)."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for dotted, amount in balances.items():
        totals[resolved[dotted]] += amount
    return dict(totals)
