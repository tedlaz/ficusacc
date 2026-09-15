"""Ad-hoc OLAP cube over transaction lines.

A *fact* is one transaction line. Users choose which *dimensions* slice the rows and
columns of a pivot and which *measures* each cell aggregates. Everything is computed in
Python from a single filtered query, which keeps the semantics identical to the other
reports (posted flag, debit = positive amount, credit = negative amount).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from app.domain.types import AccountType
from app.infrastructure.database.models import (
    AccountModel,
    TransactionLineModel,
    TransactionModel,
    UserModel,
)
from app.web.account_tree import code_prefix, prefix_names

ZERO = Decimal(0)
MAX_ROW_DIMENSIONS = 3
MAX_CHART_SERIES = 8
OTHER_KEY = "__other__"
OTHER_LABEL = "Λοιπά"
GREEK_MONTHS = ("Ιαν", "Φεβ", "Μαρ", "Απρ", "Μαι", "Ιουν", "Ιουλ", "Αυγ", "Σεπ", "Οκτ", "Νοε", "Δεκ")
GREEK_WEEKDAYS = ("Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή")
NATURAL_DEBIT_TYPES = {AccountType.ASSET, AccountType.EXPENSE}


@dataclass(frozen=True)
class Fact:
    transaction_id: int
    transaction_date: date
    amount: Decimal
    account_code: str
    account_name: str
    account_type: AccountType
    is_posted: bool
    reference: str
    user: str
    group_name: str | None = None  # names from parent (header) accounts, see account_tree
    subgroup_name: str | None = None


@dataclass(frozen=True, order=True)
class Member:
    """One value of a dimension. Ordering follows ``sort`` so time members stay chronological."""

    sort: tuple
    key: str
    label: str


OTHER = Member(sort=("\uffff",), key=OTHER_KEY, label=OTHER_LABEL)  # sorts last


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    group: str
    member_of: Callable[[Fact], Member]
    ordered: bool = False  # time-like: natural order matters and values are never folded


@dataclass
class Aggregate:
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    natural: Decimal = ZERO
    lines: int = 0
    transaction_ids: set[int] = field(default_factory=set)

    def add(self, fact: Fact) -> None:
        if fact.amount > 0:
            self.debit += fact.amount
        else:
            self.credit -= fact.amount
        self.natural += fact.amount if fact.account_type in NATURAL_DEBIT_TYPES else -fact.amount
        self.lines += 1
        self.transaction_ids.add(fact.transaction_id)


@dataclass(frozen=True)
class Measure:
    key: str
    label: str
    kind: str  # money | count
    value_of: Callable[[Aggregate], Decimal]
    signed: bool = False  # can legitimately be negative (drives diverging colour scales)


def _member_year(fact: Fact) -> Member:
    year = fact.transaction_date.year
    return Member((year,), str(year), str(year))


def _member_quarter(fact: Fact) -> Member:
    year, quarter = fact.transaction_date.year, (fact.transaction_date.month - 1) // 3 + 1
    return Member((year, quarter), f"{year}-Q{quarter}", f"Q{quarter} {year}")


def _member_month(fact: Fact) -> Member:
    year, month = fact.transaction_date.year, fact.transaction_date.month
    return Member((year, month), f"{year}-{month:02d}", f"{GREEK_MONTHS[month - 1]} {year}")


def _member_week(fact: Fact) -> Member:
    year, week, _ = fact.transaction_date.isocalendar()
    return Member((year, week), f"{year}-W{week:02d}", f"Εβδ. {week} {year}")


def _member_weekday(fact: Fact) -> Member:
    weekday = fact.transaction_date.weekday()
    return Member((weekday,), str(weekday), GREEK_WEEKDAYS[weekday])


def _member_day(fact: Fact) -> Member:
    value = fact.transaction_date
    return Member((value.toordinal(),), value.isoformat(), value.strftime("%d/%m/%Y"))


def _member_account_type(fact: Fact) -> Member:
    order = list(AccountType).index(fact.account_type)
    return Member((order,), fact.account_type.value, fact.account_type.label)


def _member_account_group(fact: Fact) -> Member:
    prefix = code_prefix(fact.account_code, 1)
    label = f"{prefix} · {fact.group_name}" if fact.group_name else f"Ομάδα {prefix}"
    return Member((prefix,), prefix, label)


def _member_account_subgroup(fact: Fact) -> Member:
    prefix = code_prefix(fact.account_code, 2)
    label = f"{prefix} · {fact.subgroup_name}" if fact.subgroup_name else f"Υποομάδα {prefix}"
    return Member((prefix,), prefix, label)


def _member_account(fact: Fact) -> Member:
    return Member((fact.account_code,), fact.account_code, f"{fact.account_code} · {fact.account_name}")


def _member_side(fact: Fact) -> Member:
    return Member((0,), "debit", "Χρέωση") if fact.amount > 0 else Member((1,), "credit", "Πίστωση")


def _member_status(fact: Fact) -> Member:
    return Member((0,), "posted", "Οριστικές") if fact.is_posted else Member((1,), "draft", "Πρόχειρες")


def _member_user(fact: Fact) -> Member:
    return Member((fact.user.casefold(),), fact.user, fact.user)


def _member_reference(fact: Fact) -> Member:
    reference = fact.reference or "—"
    return Member((reference.casefold(),), reference, reference)


DIMENSIONS: dict[str, Dimension] = {
    dimension.key: dimension
    for dimension in (
        Dimension("year", "Έτος", "Χρόνος", _member_year, ordered=True),
        Dimension("quarter", "Τρίμηνο", "Χρόνος", _member_quarter, ordered=True),
        Dimension("month", "Μήνας", "Χρόνος", _member_month, ordered=True),
        Dimension("week", "Εβδομάδα", "Χρόνος", _member_week, ordered=True),
        Dimension("weekday", "Ημέρα εβδομάδας", "Χρόνος", _member_weekday, ordered=True),
        Dimension("day", "Ημερομηνία", "Χρόνος", _member_day, ordered=True),
        Dimension("account_type", "Τύπος λογαριασμού", "Λογαριασμοί", _member_account_type),
        Dimension("account_group", "Ομάδα (1ο επίπεδο)", "Λογαριασμοί", _member_account_group),
        Dimension("account_subgroup", "Υποομάδα (2ο επίπεδο)", "Λογαριασμοί", _member_account_subgroup),
        Dimension("account", "Λογαριασμός", "Λογαριασμοί", _member_account),
        Dimension("side", "Χρέωση / Πίστωση", "Εγγραφές", _member_side),
        Dimension("status", "Κατάσταση εγγραφής", "Εγγραφές", _member_status),
        Dimension("user", "Χρήστης καταχώρησης", "Εγγραφές", _member_user),
        Dimension("reference", "Παραστατικό", "Εγγραφές", _member_reference),
    )
}

MEASURES: dict[str, Measure] = {
    measure.key: measure
    for measure in (
        Measure("natural", "Καθαρή κίνηση", "money", lambda a: a.natural, signed=True),
        Measure("debit", "Χρεώσεις", "money", lambda a: a.debit),
        Measure("credit", "Πιστώσεις", "money", lambda a: a.credit),
        Measure("net", "Χρέωση − Πίστωση", "money", lambda a: a.debit - a.credit, signed=True),
        Measure("turnover", "Τζίρος (Χ+Π)", "money", lambda a: a.debit + a.credit),
        Measure("average", "Μέση γραμμή", "money",
                lambda a: (a.debit + a.credit) / a.lines if a.lines else ZERO),
        Measure("lines", "Γραμμές", "count", lambda a: Decimal(a.lines)),
        Measure("transactions", "Εγγραφές", "count", lambda a: Decimal(len(a.transaction_ids))),
    )
}

CHART_TYPES = {
    "bar": "Ράβδοι",
    "stacked": "Στοίβα",
    "stacked100": "Στοίβα 100%",
    "line": "Γραμμές",
    "area": "Περιοχή",
    "donut": "Δακτύλιος",
    "heatmap": "Θερμικός χάρτης",
}

DIMENSION_GROUPS = ("Χρόνος", "Λογαριασμοί", "Εγγραφές")


@dataclass(frozen=True)
class CubeSpec:
    start: date
    end: date
    rows: tuple[str, ...] = ("month",)
    column: str | None = None
    measures: tuple[str, ...] = ("natural",)
    chart: str = "bar"
    sort: str = "natural"  # natural | value
    limit: int = 0  # top-N rows per level, 0 = unlimited
    posted_only: bool = True
    account_types: tuple[str, ...] = ()
    code_prefix: str = ""

    @classmethod
    def from_args(cls, args: Any, start: date, end: date) -> CubeSpec:
        rows = tuple(dict.fromkeys(
            key for key in args.getlist("row_dim") if key in DIMENSIONS
        ))[:MAX_ROW_DIMENSIONS] or ("month",)
        column = args.get("col_dim") or None
        if column not in DIMENSIONS or column in rows:
            column = None
        measures = tuple(dict.fromkeys(
            key for key in args.getlist("measure") if key in MEASURES
        )) or ("natural",)
        chart = args.get("chart_type") or "bar"
        if chart not in CHART_TYPES:
            chart = "bar"
        try:
            limit = max(int(args.get("limit") or 0), 0)
        except ValueError:
            limit = 0
        account_types = tuple(
            key for key in args.getlist("account_type") if key in AccountType._value2member_map_
        )
        return cls(
            start=start, end=end, rows=rows, column=column, measures=measures, chart=chart,
            sort="value" if args.get("sort") == "value" else "natural", limit=limit,
            posted_only=args.get("posted_only", "1") != "0", account_types=account_types,
            code_prefix=(args.get("code_prefix") or "").strip(),
        )


def load_facts(db: Session, company_id: int, spec: CubeSpec) -> list[Fact]:
    statement = (
        select(TransactionLineModel, TransactionModel, AccountModel, UserModel)
        .join(TransactionModel, TransactionLineModel.transaction_id == TransactionModel.id)
        .join(AccountModel, TransactionLineModel.account_id == AccountModel.id)
        .join(UserModel, TransactionModel.created_by_id == UserModel.id)
        .where(
            TransactionModel.company_id == company_id,
            TransactionModel.transaction_date >= spec.start,
            TransactionModel.transaction_date <= spec.end,
        )
    )
    if spec.posted_only:
        statement = statement.where(TransactionModel.is_posted == True)  # noqa: E712
    if spec.account_types:
        statement = statement.where(AccountModel.account_type.in_(spec.account_types))
    if spec.code_prefix:
        statement = statement.where(AccountModel.code.startswith(spec.code_prefix))
    rows = db.exec(statement).all()
    # Header accounts may sit outside the type/prefix filters, so name prefixes from the whole chart.
    names = prefix_names(db.exec(select(AccountModel).where(AccountModel.company_id == company_id)).all()) if rows else {}
    return [
        Fact(
            transaction_id=transaction.id,
            transaction_date=transaction.transaction_date,
            amount=Decimal(line.amount),
            account_code=account.code,
            account_name=account.name,
            account_type=AccountType(account.account_type),
            is_posted=transaction.is_posted,
            reference=transaction.reference or "",
            user=user.full_name,
            group_name=names.get(code_prefix(account.code, 1)),
            subgroup_name=names.get(code_prefix(account.code, 2)),
        )
        for line, transaction, account, user in rows
    ]


@dataclass
class PivotRow:
    members: tuple[Member, ...]
    level: int
    is_leaf: bool
    cells: dict[str, Aggregate]  # column member key -> aggregate ("" = row total)


@dataclass
class Cube:
    spec: CubeSpec
    row_dimensions: list[Dimension]
    column_dimension: Dimension | None
    measures: list[Measure]
    columns: list[Member]
    rows: list[PivotRow]
    total: Aggregate
    column_totals: dict[str, Aggregate]
    fact_count: int
    chart: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return self.fact_count == 0

    def value(self, aggregate: Aggregate | None, measure: Measure) -> Decimal:
        return measure.value_of(aggregate) if aggregate else ZERO


def _rank(children: Iterable[Member], totals: dict[Member, Aggregate], measure: Measure,
          spec: CubeSpec, ordered: bool, fold: bool = False) -> tuple[list[Member], set[Member]]:
    """Order members and, when folding, pick the ones beyond top-N; time dimensions never fold."""
    members = list(children)
    if spec.sort == "value" and not ordered:
        members.sort(key=lambda member: abs(measure.value_of(totals[member])), reverse=True)
    else:
        members.sort()
    if fold and spec.limit and not ordered and len(members) > spec.limit:
        keep = members if spec.sort == "value" else sorted(
            members, key=lambda member: abs(measure.value_of(totals[member])), reverse=True
        )
        folded = set(keep[spec.limit:])
        return [member for member in members if member not in folded], folded
    return members, set()


def build_cube(facts: list[Fact], spec: CubeSpec) -> Cube:
    row_dimensions = [DIMENSIONS[key] for key in spec.rows]
    column_dimension = DIMENSIONS[spec.column] if spec.column else None
    measures = [MEASURES[key] for key in spec.measures]
    primary = measures[0]

    # 1. Classify every fact once.
    classified: list[tuple[tuple[Member, ...], Member | None, Fact]] = [
        (
            tuple(dimension.member_of(fact) for dimension in row_dimensions),
            column_dimension.member_of(fact) if column_dimension else None,
            fact,
        )
        for fact in facts
    ]

    # 2. Fold row members level by level (top-N per parent) so subtotals stay consistent.
    for depth, dimension in enumerate(row_dimensions):
        totals: dict[tuple[Member, ...], Aggregate] = {}
        for path, _, fact in classified:
            totals.setdefault(path[: depth + 1], Aggregate()).add(fact)
        replacements: dict[tuple[Member, ...], Member] = {}
        parents = {path[:depth] for path in totals}
        for parent in parents:
            children = {path[depth]: aggregate for path, aggregate in totals.items() if path[:depth] == parent}
            _, folded = _rank(children, children, primary, spec, dimension.ordered, fold=True)
            for member in folded:
                replacements[parent + (member,)] = OTHER
        if replacements:
            classified = [
                (
                    path[:depth] + (replacements.get(path[: depth + 1], path[depth]),) + path[depth + 1:],
                    column,
                    fact,
                )
                for path, column, fact in classified
            ]

    if column_dimension is not None and spec.limit and not column_dimension.ordered:
        totals = {}
        for _, column, fact in classified:
            totals.setdefault(column, Aggregate()).add(fact)
        _, folded = _rank(totals, totals, primary, spec, ordered=False, fold=True)
        if folded:
            classified = [
                (path, OTHER if column in folded else column, fact) for path, column, fact in classified
            ]

    # 3. Aggregate cells for every prefix of the row path (gives subtotals for free).
    cells: dict[tuple[Member, ...], dict[str, Aggregate]] = {}
    column_totals: dict[Member, Aggregate] = {}
    for path, column, fact in classified:
        for depth in range(len(path) + 1):
            row_cells = cells.setdefault(path[:depth], {})
            row_cells.setdefault("", Aggregate()).add(fact)
            if column is not None:
                row_cells.setdefault(column.key, Aggregate()).add(fact)
        if column is not None:
            column_totals.setdefault(column, Aggregate()).add(fact)

    column_members, _ = _rank(
        column_totals, column_totals, primary, spec, column_dimension.ordered if column_dimension else True
    )

    # 4. Walk the row tree depth-first, sorting siblings per the spec.
    children_of: dict[tuple[Member, ...], set[Member]] = {}
    for prefix in cells:
        if prefix:
            children_of.setdefault(prefix[:-1], set()).add(prefix[-1])

    rows: list[PivotRow] = []

    def walk(prefix: tuple[Member, ...]) -> None:
        depth = len(prefix)
        if depth == len(row_dimensions):
            return
        siblings = children_of.get(prefix, set())
        totals = {member: cells[prefix + (member,)][""] for member in siblings}
        ordered_members, _ = _rank(siblings, totals, primary, spec, row_dimensions[depth].ordered)
        for member in ordered_members:
            path = prefix + (member,)
            rows.append(PivotRow(members=path, level=depth, is_leaf=depth == len(row_dimensions) - 1,
                                 cells=cells[path]))
            walk(path)

    walk(())

    total = cells.get((), {}).get("", Aggregate())
    cube = Cube(
        spec=spec,
        row_dimensions=row_dimensions,
        column_dimension=column_dimension,
        measures=measures,
        columns=column_members,
        rows=rows,
        total=total,
        column_totals={member.key: aggregate for member, aggregate in column_totals.items()},
        fact_count=len(facts),
        chart={},
    )
    cube.chart = chart_payload(cube)
    return cube


def _series_payload(label: str, key: str, values: list[Decimal]) -> dict[str, Any]:
    return {"key": key, "label": label, "values": [str(value) for value in values]}


def chart_payload(cube: Cube) -> dict[str, Any]:
    """Categories × series for the primary measure.

    Row dimension 1 supplies the categories and the column dimension the series, unless the
    column dimension is time-like and the row one is not: time always runs along the x-axis
    so the reader never has to compare "months" as colours. Without a column dimension every
    selected measure of the primary kind becomes a series.
    """
    primary = cube.measures[0]
    top_rows = [row for row in cube.rows if row.level == 0]
    row_dimension = cube.row_dimensions[0]
    column_dimension = cube.column_dimension

    if column_dimension is None:
        categories = [row.members[0] for row in top_rows]
        same_kind = [measure for measure in cube.measures if measure.kind == primary.kind]
        series = [
            _series_payload(measure.label, measure.key,
                            [cube.value(row.cells.get(""), measure) for row in top_rows])
            for measure in same_kind
        ]
        axis_label, series_label = row_dimension.label, "Μέγεθος"
    else:
        swap = column_dimension.ordered and not row_dimension.ordered
        if swap:
            categories = cube.columns
            series_members = [row.members[0] for row in top_rows]
            axis_label, series_label = column_dimension.label, row_dimension.label

            def value_at(series_member: Member, category: Member) -> Decimal:
                row = next(row for row in top_rows if row.members[0] == series_member)
                return cube.value(row.cells.get(category.key), primary)
        else:
            categories = [row.members[0] for row in top_rows]
            series_members = cube.columns
            axis_label, series_label = row_dimension.label, column_dimension.label

            def value_at(series_member: Member, category: Member) -> Decimal:
                row = next(row for row in top_rows if row.members[0] == category)
                return cube.value(row.cells.get(series_member.key), primary)

        totals = {
            member: sum((abs(value_at(member, category)) for category in categories), ZERO)
            for member in series_members
        }
        ordered = sorted(series_members, key=lambda member: totals[member], reverse=True)
        kept = ordered[: MAX_CHART_SERIES - 1] if len(ordered) > MAX_CHART_SERIES else ordered
        folded = [member for member in ordered if member not in kept]
        kept = [member for member in series_members if member in kept]  # keep natural order
        series = [
            _series_payload(member.label, member.key, [value_at(member, category) for category in categories])
            for member in kept
        ]
        if folded:
            series.append(_series_payload(OTHER_LABEL, OTHER_KEY, [
                sum((value_at(member, category) for member in folded), ZERO) for category in categories
            ]))

    return {
        "type": cube.spec.chart,
        "measure": {"key": primary.key, "label": primary.label, "kind": primary.kind, "signed": primary.signed},
        "axis_label": axis_label,
        "series_label": series_label,
        "categories": [{"key": member.key, "label": member.label} for member in categories],
        "series": series,
    }


def cube_rows_as_table(cube: Cube) -> tuple[list[str], list[list[str]]]:
    """Flat header + rows (raw decimal strings) for CSV/PDF export."""
    headers = [dimension.label for dimension in cube.row_dimensions]
    columns = cube.columns if cube.column_dimension else []
    for column in columns:
        headers += [f"{column.label} · {measure.label}" for measure in cube.measures]
    headers += [f"Σύνολο · {measure.label}" if columns else measure.label for measure in cube.measures]

    body: list[list[str]] = []
    for row in cube.rows:
        labels = [member.label for member in row.members]
        labels += [""] * (len(cube.row_dimensions) - len(labels))
        values: list[str] = []
        for column in columns:
            values += [f"{cube.value(row.cells.get(column.key), measure):.2f}" for measure in cube.measures]
        values += [f"{cube.value(row.cells.get(''), measure):.2f}" for measure in cube.measures]
        body.append(labels + values)

    totals = ["Σύνολο"] + [""] * (len(cube.row_dimensions) - 1)
    for column in columns:
        totals += [f"{cube.value(cube.column_totals.get(column.key), measure):.2f}" for measure in cube.measures]
    totals += [f"{cube.value(cube.total, measure):.2f}" for measure in cube.measures]
    body.append(totals)
    return headers, body


def olap_cube(db: Session, company_id: int, spec: CubeSpec) -> Cube:
    return build_cube(load_facts(db, company_id, spec), spec)
