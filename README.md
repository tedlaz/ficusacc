# HomeAccounting

Πολυεταιρική εφαρμογή διπλογραφικής λογιστικής με Flask, Jinja templates, HTMX και SQLite.

## Λειτουργίες

- Εγγραφή, είσοδος και ασφαλή server-side sessions
- Πολλαπλές εταιρείες, ρόλοι και δικαιώματα πρόσβασης
- Λογιστικό σχέδιο με ιεραρχία και CSV import/export
- Ισοσκελισμένες λογιστικές εγγραφές, post/unpost και αντιγραφή
- Ισοζύγιο, ισολογισμός, αποτελέσματα χρήσης, καρτέλα και ημερολόγιο
- Server-side PDF export με `fpdf2` και ελληνική Unicode υποστήριξη
- Διαχείριση χρηστών και αλλαγή κωδικού
- SQLite backup, download και restore
- Responsive server-rendered HTML interface

## Ανάπτυξη

Απαιτούνται Python 3.12+ και `uv`.

```bash
uv sync
uv run flask --app app.main run --debug
```

Η εφαρμογή ανοίγει στο `http://127.0.0.1:5000`. Οι πίνακες δημιουργούνται αυτόματα στην πρώτη εκκίνηση.

Για να καταγραφεί μία υπάρχουσα βάση στο Alembic χωρίς αλλαγή schema:

```bash
uv run alembic upgrade head
```

Προαιρετικά demo δεδομένα:

```bash
uv run python scripts/seed.py
```

## Tests

```bash
uv run pytest
uv run ruff check app tests scripts
```

## Docker

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose up --build
```

Η εφαρμογή είναι διαθέσιμη στο `http://localhost:8013`. Η βάση διατηρείται στο `./database` και τα αντίγραφα στο `./backups`.

Για deployment πίσω από HTTPS reverse proxy ορίστε `SESSION_COOKIE_SECURE=true`. Το container
εκτελεί αυτόματα `alembic upgrade head` πριν ξεκινήσει το Waitress και τρέχει ως UID/GID 1000.
Οι κατάλογοι `./database` και `./backups` πρέπει να είναι εγγράψιμοι από αυτόν τον χρήστη.
Για διαφορετικό host UID/GID ορίστε `APP_UID` και `APP_GID` πριν το build.

## Ρυθμίσεις

```env
APP_NAME=HomeAccounting
DEBUG=false
DATABASE_URL=sqlite:///./accounting.db
BACKUP_DIR=./backups
SECRET_KEY=replace-with-a-long-random-value
```
