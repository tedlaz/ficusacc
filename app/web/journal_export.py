"""Plain-text journal export in the `j-normal` ledger format."""

import re
from decimal import Decimal

NEWLINE = "\r\n"
HEADER = "j-normal"
INDENT = "  "
GAP = "  "
COLUMN_SPLIT = re.compile(r"\s{2,}")
# Room for the integer part of 9.999.999,99 - with the ",99" that is a 12-wide amount column.
MIN_INTEGER_WIDTH = 9


class MissingMappingError(Exception):
    """Raised when account codes have no entry in the conversion table."""

    def __init__(self, codes):
        self.codes = sorted(codes)
        super().__init__(f"Λείπουν αντιστοιχίσεις για {len(self.codes)} λογαριασμούς.")


def clean_text(value) -> str:
    return " ".join(str(value or "").split())


def parse_mapping(raw: str) -> dict[str, str]:
    """Read a conversion table of `code<spaces>target account` lines."""
    mapping: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = COLUMN_SPLIT.split(stripped, maxsplit=1)
        if len(parts) < 2:
            parts = stripped.split(None, 1)
        if len(parts) < 2:
            continue
        # A target holding two consecutive spaces would break the column layout downstream.
        code, target = parts[0].strip(), clean_text(parts[1])
        if code and target:
            mapping[code] = target
    return mapping


def format_amount(value: Decimal) -> str:
    """Greek number format, dropping the decimals when the amount is whole."""
    amount = Decimal(value or 0)
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return formatted[:-3] if formatted.endswith(",00") else formatted


def build_account_list(accounts) -> str:
    """Two-column skeleton of the conversion table: app code and account name."""
    rows = sorted(
        ((account.code, clean_text(account.name)) for account in accounts),
        key=lambda row: row[0],
    )
    if not rows:
        return ""
    width = max(len(code) for code, _ in rows)
    return NEWLINE.join(f"{code.ljust(width)}{GAP}{name}" for code, name in rows) + NEWLINE


def posting_code(line, account_map) -> str:
    account = account_map.get(line.account_id)
    return account.code if account else f"#{line.account_id}"


def ordered_postings(transaction, account_map, mapping):
    """Debits first, then credits, each keeping its stored line order."""
    lines = sorted(transaction.lines, key=lambda line: (line.line_order, line.id or 0))
    debits = [line for line in lines if line.amount > 0]
    credits = [line for line in lines if line.amount <= 0]
    return [
        (mapping[posting_code(line, account_map)], Decimal(line.amount))
        for line in debits + credits
    ]


def column_widths(all_postings) -> tuple[int, int]:
    """Account and integer-part widths, measured once over the whole file."""
    priced = [posting for postings in all_postings for posting in postings[:-1]]
    if not priced:
        return 0, MIN_INTEGER_WIDTH
    account_width = max(len(account) for account, _ in priced)
    integer_width = max(
        [MIN_INTEGER_WIDTH]
        + [len(format_amount(amount).partition(",")[0]) for _, amount in priced]
    )
    return account_width, integer_width


def transaction_block(transaction, postings, account_width: int, integer_width: int) -> str:
    """One transaction: header line plus its postings, last amount omitted."""
    header = [transaction.transaction_date.isoformat()]
    reference = clean_text(transaction.reference)
    if reference:
        header.append(f"{{{reference}}}")
    description = clean_text(transaction.description)
    if description:
        header.append(description)

    rendered = [" ".join(header)]
    for account, amount in postings[:-1]:
        integer, _, fraction = format_amount(amount).partition(",")
        padded = integer.rjust(integer_width) + (f",{fraction}" if fraction else "")
        rendered.append(f"{INDENT}{account.ljust(account_width)}{GAP}{padded}")
    for account, _ in postings[-1:]:
        rendered.append(f"{INDENT}{account}")
    return NEWLINE.join(rendered)


def build_journal(transactions, account_map, mapping: dict[str, str]) -> str:
    """Render the whole file, refusing to emit anything when a mapping is missing."""
    missing = {
        code
        for transaction in transactions
        for line in transaction.lines
        if (code := posting_code(line, account_map)) not in mapping
    }
    if missing:
        raise MissingMappingError(missing)

    all_postings = [
        ordered_postings(transaction, account_map, mapping) for transaction in transactions
    ]
    account_width, integer_width = column_widths(all_postings)
    parts = [HEADER, ""]
    for transaction, postings in zip(transactions, all_postings, strict=True):
        parts.append(transaction_block(transaction, postings, account_width, integer_width))
        parts.append("")
    return NEWLINE.join(parts) + NEWLINE
