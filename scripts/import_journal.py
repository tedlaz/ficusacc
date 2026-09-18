"""Import a `j-normal` text book (rhomeaccount format) into a COPY of the database.

Safety model:
  * Dry run by default: parses, resolves accounts, prints the plan and every error. No writes.
  * `--commit` copies the live database to `--target` (never the live file) and imports there,
    in one transaction, then reconciles the copy against the text; on any failure the copy is
    rolled back and deleted. Adopt the result through the app's Backup -> Restore page.
  * Everything imported is tagged (`book_ted:file:line` in transaction.reference,
    `book_ted: Dotted.Name` in account.description) so re-runs skip it and `--undo` removes it.

    uv run python scripts/import_journal.py --book ~/Documents/book_ted --company SPITI
    uv run python scripts/import_journal.py ... --write-mapping plan.txt
    uv run python scripts/import_journal.py ... --mapping plan.txt --commit
"""


import argparse
import fnmatch
import sqlite3
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func
from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine, select

from app.core.config import settings
from app.infrastructure.database.models import (
    AccountModel,
    CompanyModel,
    TransactionLineModel,
    TransactionModel,
    UserCompanyAccessModel,
    UserModel,
)
from app.web import journal_import as ji

CHART_FILE = "000"
DEFAULT_EXCLUDES = ("y.txt", "journal_*.txt")
RECONCILE_DATES = (date(2024, 7, 16), date(2024, 12, 31), date(2025, 11, 24))


class ImportAbort(Exception):
    pass


def live_database() -> Path:
    url = make_url(settings.DATABASE_URL)
    if url.drivername != "sqlite" or not url.database:
        raise ImportAbort("Υποστηρίζεται μόνο SQLite.")
    return Path(url.database).resolve()


def read_book(book: Path, excludes: list[str]):
    """Chart of the `000` file and every other file (sorted by name) parsed to transactions."""
    chart = ji.parse_chart((book / CHART_FILE).read_text(encoding="utf-8-sig"))
    transactions, errors, per_file = [], [], []
    for path in sorted(p for p in book.iterdir() if p.is_file() and p.name != CHART_FILE):
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in excludes):
            continue
        parsed, file_errors = ji.parse_journal(path.read_text(encoding="utf-8-sig"), path.name)
        transactions.extend(parsed)
        errors.extend(file_errors)
        per_file.append((path.name, len(parsed), len(file_errors)))
    transactions.sort(key=lambda t: (t.date, t.source))
    return chart, transactions, errors, per_file


def resolve_all(resolver: ji.AccountResolver, transactions) -> None:
    """Resolve names in alphabetical order so new codes come out sorted, not in date order."""
    for name in sorted({line.account for t in transactions for line in t.lines}):
        resolver.resolve(name)


def load_existing(db: Session, company_id: int) -> list[ji.ExistingAccount]:
    accounts = db.exec(select(AccountModel).where(AccountModel.company_id == company_id)).all()
    by_id = {account.id: account for account in accounts}
    return [
        ji.ExistingAccount(
            code=a.code,
            name=a.name,
            account_type=a.account_type,
            parent_code=by_id[a.parent_id].code if a.parent_id in by_id else None,
            is_active=a.is_active,
            description=a.description,
        )
        for a in accounts
    ]


def company_and_user(db: Session, company_code: str, email: str | None):
    company = db.exec(select(CompanyModel).where(CompanyModel.code == company_code)).first()
    if company is None:
        raise ImportAbort(f"Δεν βρέθηκε εταιρεία με κωδικό {company_code!r}.")
    query = select(UserModel).join(
        UserCompanyAccessModel, UserCompanyAccessModel.user_id == UserModel.id
    ).where(UserCompanyAccessModel.company_id == company.id)
    if email:
        query = query.where(UserModel.email == email)
    user = db.exec(query.order_by(UserModel.id)).first()
    if user is None:
        raise ImportAbort("Δεν βρέθηκε χρήστης με πρόσβαση στην εταιρεία.")
    return company, user


def existing_tags(db: Session, company_id: int) -> set[str]:
    rows = db.exec(
        select(TransactionModel.reference).where(
            TransactionModel.company_id == company_id,
            TransactionModel.reference.like(f"%{ji.TAG_PREFIX}%"),  # type: ignore[union-attr]
        )
    ).all()
    return {tag_of(reference) for reference in rows if reference}


def tag_of(reference: str) -> str:
    """The `book_ted:file:line` part of a stored reference."""
    index = reference.find(ji.TAG_PREFIX)
    return reference[index:] if index >= 0 else ""


def reference_for(transaction: ji.ParsedTransaction) -> str:
    return f"{transaction.reference} {transaction.tag}".strip() if transaction.reference else transaction.tag


def write_accounts(db: Session, company_id: int, resolver: ji.AccountResolver) -> dict[str, int]:
    """Create the planned accounts (parents first) and return code -> id for the whole chart."""
    ids = {
        a.code: a.id
        for a in db.exec(select(AccountModel).where(AccountModel.company_id == company_id)).all()
    }
    for planned in resolver.created:  # creation order already puts parents first
        parent_id = ids.get(planned.parent_code) if planned.parent_code else None
        account = AccountModel(
            company_id=company_id,
            code=planned.code,
            name=planned.name,
            account_type=planned.account_type,
            parent_id=parent_id,
            is_active=planned.is_active,
            description=f"{ji.ACCOUNT_TAG_PREFIX}{planned.dotted}",
        )
        db.add(account)
        db.flush()
        ids[planned.code] = account.id
    return ids


def write_transactions(db, company_id, user_id, transactions, resolver, ids, skip: set[str]) -> int:
    imported = 0
    for transaction in transactions:
        if transaction.tag in skip:
            continue
        row = TransactionModel(
            company_id=company_id,
            transaction_date=transaction.date,
            description=transaction.description or "-",
            reference=reference_for(transaction)[:100],
            is_posted=True,
            created_by_id=user_id,
        )
        db.add(row)
        db.flush()
        for order, line in enumerate(transaction.lines):
            db.add(
                TransactionLineModel(
                    transaction_id=row.id,
                    account_id=ids[resolver.resolve(line.account)],
                    amount=line.amount,
                    description=line.comment or None,
                    line_order=order,
                )
            )
        imported += 1
    db.flush()
    return imported


def db_balances(db: Session, company_id: int, until: date) -> dict[str, Decimal]:
    """Code -> net amount of TAGGED transactions dated on or before `until`."""
    rows = db.exec(
        select(AccountModel.code, func.sum(TransactionLineModel.amount))
        .join(TransactionLineModel, TransactionLineModel.account_id == AccountModel.id)
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(
            TransactionModel.company_id == company_id,
            TransactionModel.transaction_date <= until,
            TransactionModel.reference.like(f"%{ji.TAG_PREFIX}%"),  # type: ignore[union-attr]
        )
        .group_by(AccountModel.code)
    ).all()
    return {code: Decimal(str(total)).quantize(Decimal("0.01")) for code, total in rows}


def reconcile(db, company_id, transactions, resolver, original_counts) -> list[str]:
    """Differences between the copy and the text; empty means the import is faithful."""
    problems = []
    for until in RECONCILE_DATES:
        expected = ji.balances_by_code(ji.balances_from_text(transactions, until), resolver.resolved)
        actual = db_balances(db, company_id, until)
        for code in sorted(set(expected) | set(actual)):
            want, got = expected.get(code, Decimal(0)), actual.get(code, Decimal(0))
            if want != got:
                problems.append(f"{until}: {code} κείμενο {want} != βάση {got}")
    unbalanced = db.exec(
        select(TransactionLineModel.transaction_id)
        .join(TransactionModel, TransactionModel.id == TransactionLineModel.transaction_id)
        .where(
            TransactionModel.company_id == company_id,
            TransactionModel.reference.like(f"%{ji.TAG_PREFIX}%"),  # type: ignore[union-attr]
        )
        .group_by(TransactionLineModel.transaction_id)
        # SQLite sums REAL values, so a balanced entry can come back as 1e-13; compare in cents.
        .having(func.round(func.sum(TransactionLineModel.amount), 2) != 0)
    ).all()
    if unbalanced:
        problems.append(f"{len(unbalanced)} εγγραφές δεν ισοσκελίζουν: {unbalanced[:5]}")
    untouched = untagged_counts(db, company_id)
    if untouched != original_counts:
        problems.append(f"Οι προϋπάρχουσες εγγραφές άλλαξαν: {original_counts} -> {untouched}")
    return problems


def untagged_counts(db: Session, company_id: int) -> tuple[int, int, Decimal]:
    """(transactions, lines, sum of absolute amounts) of everything NOT imported by this tool."""
    row = db.exec(
        select(
            func.count(func.distinct(TransactionModel.id)),
            func.count(TransactionLineModel.id),
            func.coalesce(func.sum(func.abs(TransactionLineModel.amount)), 0),
        )
        .join(TransactionLineModel, TransactionLineModel.transaction_id == TransactionModel.id)
        .where(
            TransactionModel.company_id == company_id,
            ~TransactionModel.reference.like(f"%{ji.TAG_PREFIX}%") | TransactionModel.reference.is_(None),  # type: ignore[union-attr]
        )
    ).one()
    return row[0], row[1], Decimal(str(row[2])).quantize(Decimal("0.01"))


def print_report(per_file, errors, resolver, transactions, mapping_path: Path | None):
    print("Αρχεία:")
    for name, count, errs in per_file:
        print(f"  {name:<12} {count:>5} εγγραφές" + (f"  {errs} σφάλματα" if errs else ""))
    print(f"Σύνολο: {len(transactions)} εγγραφές, {len(errors)} σφάλματα")
    for error in errors:
        print(f"  ! {error}")
    print(f"Λογαριασμοί: {len(resolver.resolved)} στο κείμενο, {len(resolver.created)} νέοι")
    if mapping_path:
        mapping_path.write_text(ji.render_plan(resolver), encoding="utf-8")
        print(f"Το σχέδιο αντιστοίχισης γράφτηκε στο {mapping_path}")
    else:
        print(ji.render_plan(resolver), end="")


def copy_database(source: Path, target: Path, live: Path) -> bool:
    """Copy `source` to `target`; an existing target is reused (re-runs). Returns whether copied."""
    if target.resolve() in (source, live):
        raise ImportAbort("Ο στόχος είναι η ζωντανή/αρχική βάση· η εισαγωγή γίνεται μόνο σε αντίγραφο.")
    if target.exists():
        print(f"Το {target} υπάρχει· η εισαγωγή συνεχίζει σε αυτό.")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return True


def undo(target: Path, company_code: str) -> None:
    if target.resolve() == live_database():
        raise ImportAbort("Το --undo δεν τρέχει στη ζωντανή βάση.")
    engine = create_engine(f"sqlite:///{target}")
    with Session(engine) as db:
        company = db.exec(select(CompanyModel).where(CompanyModel.code == company_code)).first()
        if company is None:
            raise ImportAbort(f"Δεν βρέθηκε εταιρεία {company_code!r}.")
        tagged = db.exec(
            select(TransactionModel).where(
                TransactionModel.company_id == company.id,
                TransactionModel.reference.like(f"%{ji.TAG_PREFIX}%"),  # type: ignore[union-attr]
            )
        ).all()
        for transaction in tagged:
            db.delete(transaction)
        db.flush()
        accounts = db.exec(
            select(AccountModel).where(
                AccountModel.company_id == company.id,
                AccountModel.description.like(f"{ji.ACCOUNT_TAG_PREFIX}%"),  # type: ignore[union-attr]
            )
        ).all()
        used = set(db.exec(select(TransactionLineModel.account_id).distinct()).all())
        all_accounts = db.exec(
            select(AccountModel).where(AccountModel.company_id == company.id)
        ).all()
        parents_in_use = {a.parent_id for a in all_accounts if a.parent_id is not None}
        removed = 0
        # Deepest first so children go before their parents; keep anything still referenced.
        for account in sorted(accounts, key=lambda a: -len(a.code)):
            if account.id in used or account.id in parents_in_use:
                continue
            parents_in_use.discard(account.parent_id)
            db.delete(account)
            removed += 1
        db.commit()
    print(f"Αφαιρέθηκαν {len(tagged)} εγγραφές και {removed} λογαριασμοί από το {target}")


def run(args) -> int:
    book = Path(args.book).expanduser()
    if not (book / CHART_FILE).is_file():
        raise ImportAbort(f"Το {book} δεν περιέχει αρχείο {CHART_FILE}.")
    chart, transactions, errors, per_file = read_book(book, args.exclude)
    mapping = ji.read_mapping(Path(args.mapping).read_text(encoding="utf-8-sig")) if args.mapping else {}

    live = live_database()
    source = Path(args.source).resolve() if args.source else live
    if not source.is_file():
        raise ImportAbort(f"Δεν βρέθηκε η βάση {source}.")
    if not args.commit:
        engine = create_engine(f"sqlite:///{source}")
        with Session(engine) as db:
            company, _ = company_and_user(db, args.company, args.user)
            resolver = ji.AccountResolver(load_existing(db, company.id), mapping, chart)
            resolve_all(resolver, transactions)
            skip = existing_tags(db, company.id)
        print_report(per_file, errors, resolver, transactions, args.write_mapping)
        if skip:
            print(f"Ήδη εισηγμένες στη ζωντανή βάση: {len(skip)} (θα παραλειφθούν)")
        print("\nΔοκιμαστική εκτέλεση· τίποτα δεν γράφτηκε. Για εισαγωγή σε αντίγραφο: --commit")
        return 1 if errors else 0

    if errors and not args.skip_errors:
        for error in errors:
            print(f"  ! {error}")
        raise ImportAbort(f"{len(errors)} σφάλματα ανάλυσης· διορθώστε τα ή δώστε --skip-errors.")

    target = Path(args.target) if args.target else live.parent / f"import_{datetime.now(UTC):%Y%m%d_%H%M%S}.db"
    created_copy = copy_database(source, target, live)
    engine = create_engine(f"sqlite:///{target}")
    try:
        with Session(engine) as db:
            company, user = company_and_user(db, args.company, args.user)
            original_counts = untagged_counts(db, company.id)
            resolver = ji.AccountResolver(load_existing(db, company.id), mapping, chart)
            resolve_all(resolver, transactions)
            skip = existing_tags(db, company.id)
            ids = write_accounts(db, company.id, resolver)
            imported = write_transactions(db, company.id, user.id, transactions, resolver, ids, skip)
            problems = reconcile(db, company.id, transactions, resolver, original_counts)
            if problems:
                db.rollback()
                for problem in problems[:50]:
                    print(f"  ! {problem}")
                raise ImportAbort(f"Η συμφωνία απέτυχε ({len(problems)} διαφορές)· τίποτα δεν γράφτηκε.")
            db.commit()
    except BaseException:
        engine.dispose()
        if created_copy:
            target.unlink(missing_ok=True)
        raise
    engine.dispose()
    print_report(per_file, errors, resolver, transactions, args.write_mapping)
    print(f"\nΕισήχθησαν {imported} εγγραφές ({len(skip)} ήδη υπήρχαν), {len(resolver.created)} νέοι λογαριασμοί.")
    print(f"Η συμφωνία με το κείμενο πέρασε για {', '.join(str(d) for d in RECONCILE_DATES)}.")
    print(f"Η αρχική βάση {source} δεν άλλαξε. Αποτέλεσμα: {target}")
    print("Προεπισκόπηση:")
    print(f"  DATABASE_URL=sqlite:///{target} uv run flask --app app.main run --port 5001")
    print("Υιοθέτηση: αντιγράψτε το αρχείο στο φάκελο backups και κάντε Επαναφορά από τη σελίδα Αντίγραφα.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--book", required=True, help="Φάκελος με το 000 και τα ημερολόγια")
    parser.add_argument("--company", required=True, help="Κωδικός εταιρείας (π.χ. SPITI)")
    parser.add_argument("--mapping", help="Αρχείο αντιστοίχισης `Dotted.Name  code`")
    parser.add_argument("--exclude", action="append", default=list(DEFAULT_EXCLUDES), metavar="GLOB")
    parser.add_argument("--user", help="Email χρήστη που θα φαίνεται δημιουργός")
    parser.add_argument("--write-mapping", type=Path, help="Γράψε το σχέδιο αντιστοίχισης εδώ")
    parser.add_argument("--commit", action="store_true", help="Εισαγωγή σε αντίγραφο της βάσης")
    parser.add_argument("--source", help="Βάση αφετηρίας αντί της ζωντανής (π.χ. backup παραγωγής)")
    parser.add_argument("--target", help="Πού να γραφτεί το αντίγραφο (ποτέ η ζωντανή βάση)")
    parser.add_argument("--skip-errors", action="store_true", help="Συνέχισε παρά τα σφάλματα ανάλυσης")
    parser.add_argument("--undo", action="store_true", help="Αφαίρεσε ό,τι εισήχθη από το --target")
    args = parser.parse_args(argv)
    try:
        if args.undo:
            if not args.target:
                raise ImportAbort("Το --undo χρειάζεται --target.")
            undo(Path(args.target), args.company)
            return 0
        return run(args)
    except ImportAbort as error:
        print(f"Διακοπή: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
