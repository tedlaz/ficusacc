"""Server-side PDF rendering for financial reports using fpdf2."""

import functools
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

from app.domain.types import ACCOUNT_TYPE_LABELS
from app.web.pdf_charts import draw_chart


FONT_CANDIDATES = (
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/noto/NotoSans-Regular.ttf", "/usr/share/fonts/noto/NotoSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ("/usr/share/fonts/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)


def _fontconfig_match(pattern: str) -> Path | None:
    """Ask fontconfig (Linux/macOS) for a TrueType file matching the pattern."""
    try:
        result = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True,
                                timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    path = Path(result.stdout.strip())
    return path if path.suffix.lower() == ".ttf" and path.exists() else None


@functools.cache
def find_fonts() -> tuple[Path, Path]:
    """Locate a Unicode (Greek-capable) regular/bold TTF pair, preferring well-known paths."""
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            return Path(regular), Path(bold)
    for family in ("DejaVu Sans", "Noto Sans", "Liberation Sans", "sans-serif"):
        regular = _fontconfig_match(f"{family}:lang=el")
        bold = _fontconfig_match(f"{family}:bold:lang=el")
        if regular and bold:
            return regular, bold
    raise RuntimeError("Δεν βρέθηκε Unicode γραμματοσειρά για τη δημιουργία PDF.")


class ReportPDF(FPDF):
    def __init__(self, title: str, company_name: str, orientation: str = "P"):
        super().__init__(orientation=orientation, unit="mm", format="A4")
        regular_font, bold_font = find_fonts()
        self.add_font("Report", style="", fname=str(regular_font))
        self.add_font("Report", style="B", fname=str(bold_font))
        self.report_title = title
        self.company_name = company_name
        self.set_margins(10, 18, 10)
        self.set_auto_page_break(auto=True, margin=14)
        self.alias_nb_pages()

    def header(self):
        self.set_font("Report", "B", 13)
        self.set_text_color(23, 42, 49)
        self.cell(0, 6, self.report_title, align="L")
        self.ln(6)
        self.set_font("Report", "", 8)
        self.set_text_color(90, 102, 96)
        self.cell(0, 5, self.company_name, align="L")
        self.ln(7)
        self.set_draw_color(198, 205, 199)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-10)
        self.set_font("Report", "", 7)
        self.set_text_color(105, 115, 108)
        generated = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.cell(0, 5, f"Δημιουργήθηκε {generated} · Σελίδα {self.page_no()}/{{nb}}", align="C")


def money(value, currency: str) -> str:
    amount = Decimal(value or 0)
    formatted = f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{formatted} {'€' if currency.upper() == 'EUR' else currency}"


def short_text(value, width: float) -> str:
    text = str(value or "")
    max_chars = max(int(width / 2.05), 4)
    return text if len(text) <= max_chars else f"{text[: max_chars - 1]}…"


def add_table(pdf, headers, rows, widths, aligns=None):
    aligns = aligns or ["L"] * len(headers)
    row_height = 6.5

    def draw_header():
        pdf.set_font("Report", "B", 7)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(31, 92, 72)
        for header, width, align in zip(headers, widths, aligns, strict=True):
            pdf.cell(width, row_height, short_text(header, width), border=1, align=align, fill=True)
        pdf.ln(row_height)

    draw_header()
    for row in rows:
        if pdf.get_y() + row_height > pdf.page_break_trigger:
            pdf.add_page()
            draw_header()
        values = row["values"] if isinstance(row, dict) else row
        is_summary = isinstance(row, dict) and row.get("summary", False)
        pdf.set_font("Report", "B" if is_summary else "", 7)
        pdf.set_text_color(23, 33, 29)
        pdf.set_fill_color(239, 243, 237) if is_summary else pdf.set_fill_color(255, 255, 255)
        for value, width, align in zip(values, widths, aligns, strict=True):
            pdf.cell(
                width,
                row_height,
                short_text(value, width),
                border=1,
                align=align,
                fill=is_summary,
            )
        pdf.ln(row_height)


def add_period(pdf, text: str):
    pdf.set_font("Report", "", 8)
    pdf.set_text_color(90, 102, 96)
    pdf.cell(0, 5, text)
    pdf.ln(8)


def build_report_pdf(kind: str, data: dict, company) -> tuple[bytes, str]:
    builders = {
        "trial_balance": build_trial_balance,
        "balance_sheet": build_balance_sheet,
        "income_statement": build_income_statement,
        "general_ledger": build_general_ledger,
        "journal": build_journal,
        "olap": build_olap,
    }
    if kind not in builders:
        raise ValueError(f"Unknown report type: {kind}")
    pdf, filename = builders[kind](data, company)
    return bytes(pdf.output()), filename


def build_trial_balance(data, company):
    report_date = data["as_of_date"]
    pdf = ReportPDF("Ισοζύγιο", company.name)
    pdf.add_page()
    add_period(pdf, f"Έως {report_date:%d/%m/%Y}")
    rows = []
    for item in data["accounts"]:
        rows.append(
            {
                "summary": item.is_summary,
                "values": (
                    item.account.code,
                    item.account.name,
                    ACCOUNT_TYPE_LABELS[item.account.account_type.value],
                    money(item.debit_total, company.currency),
                    money(item.credit_total, company.currency),
                    money(item.balance, company.currency),
                ),
            }
        )
    rows.append(
        {
            "summary": True,
            "values": (
                "",
                "Σύνολο",
                "",
                money(data["total_debits"], company.currency),
                money(data["total_credits"], company.currency),
                money(data["total_debits"] - data["total_credits"], company.currency),
            ),
        }
    )
    add_table(pdf, ("Κωδικός", "Λογαριασμός", "Τύπος", "Χρέωση", "Πίστωση", "Υπόλοιπο"), rows,
              (22, 58, 24, 29, 29, 28), ("L", "L", "L", "R", "R", "R"))
    return pdf, f"isozygio-{report_date.isoformat()}.pdf"


def add_account_section(pdf, title, items, total_label, total, company, absolute=False):
    pdf.set_font("Report", "B", 10)
    pdf.set_text_color(23, 42, 49)
    pdf.cell(0, 7, title)
    pdf.ln(7)
    rows = [
        (item.account.code, item.account.name, money(abs(item.balance) if absolute else item.balance, company.currency))
        for item in items
    ]
    rows.append({"summary": True, "values": ("", total_label, money(total, company.currency))})
    add_table(pdf, ("Κωδικός", "Λογαριασμός", "Ποσό"), rows, (30, 115, 45), ("L", "L", "R"))
    pdf.ln(7)


def build_balance_sheet(data, company):
    report_date = data["as_of_date"]
    pdf = ReportPDF("Ισολογισμός", company.name)
    pdf.add_page()
    add_period(pdf, f"Έως {report_date:%d/%m/%Y}")
    add_account_section(pdf, "Ενεργητικό", data["assets"], "Σύνολο ενεργητικού", data["total_assets"], company)
    add_account_section(pdf, "Υποχρεώσεις", data["liabilities"], "Σύνολο υποχρεώσεων", data["total_liabilities"], company, absolute=True)
    add_account_section(pdf, "Καθαρή θέση", data["equity"], "Σύνολο καθαρής θέσης", data["total_equity"], company, absolute=True)
    return pdf, f"isologismos-{report_date.isoformat()}.pdf"


def build_income_statement(data, company):
    pdf = ReportPDF("Αποτελέσματα χρήσης", company.name)
    pdf.add_page()
    add_period(pdf, f"{data['start_date']:%d/%m/%Y} έως {data['end_date']:%d/%m/%Y}")
    add_account_section(pdf, "Έσοδα", data["revenues"], "Σύνολο εσόδων", data["total_revenue"], company, absolute=True)
    add_account_section(pdf, "Έξοδα", data["expenses"], "Σύνολο εξόδων", data["total_expenses"], company)
    pdf.set_font("Report", "B", 11)
    pdf.cell(145, 9, "Καθαρό αποτέλεσμα", border=1)
    pdf.cell(45, 9, money(data["net_income"], company.currency), border=1, align="R")
    return pdf, f"apotelesmata-{data['start_date'].isoformat()}-{data['end_date'].isoformat()}.pdf"


def build_general_ledger(data, company):
    account = data["account"]
    pdf = ReportPDF(f"Καρτέλα {account.code} · {account.name}", company.name)
    pdf.add_page()
    add_period(pdf, f"Τρέχον υπόλοιπο: {money(data['current_balance'], company.currency)}")
    rows = []
    for entry in data["entries"]:
        line = entry["line"]
        transaction = entry["transaction"]
        rows.append(
            (
                transaction.transaction_date.strftime("%d/%m/%Y"),
                transaction.description,
                transaction.reference or "—",
                money(line.amount, company.currency) if line.amount > 0 else "—",
                money(abs(line.amount), company.currency) if line.amount < 0 else "—",
                money(entry["balance"], company.currency),
            )
        )
    add_table(pdf, ("Ημερομηνία", "Περιγραφή", "Σχετικό", "Χρέωση", "Πίστωση", "Υπόλοιπο"), rows,
              (24, 52, 25, 29, 29, 31), ("L", "L", "L", "R", "R", "R"))
    return pdf, f"kartela-{account.code}.pdf"


def build_journal(data, company):
    pdf = ReportPDF("Ημερολόγιο", company.name)
    pdf.add_page()
    add_period(pdf, f"{data['start_date']:%d/%m/%Y} έως {data['end_date']:%d/%m/%Y}")
    for entry in data["entries"]:
        add_journal_article(pdf, entry, company)
    return pdf, f"imerologio-{data['start_date'].isoformat()}-{data['end_date'].isoformat()}.pdf"


def add_journal_article(pdf, entry, company):
    article_title, rows = journal_article_content(entry, company)
    row_height = 6.5
    widths = (112, 39, 39)
    required_height = 14 + min(len(rows), 3) * row_height
    if pdf.get_y() + required_height > pdf.page_break_trigger:
        pdf.add_page()

    pdf.set_font("Report", "B", 8)
    pdf.set_text_color(23, 42, 49)
    pdf.set_fill_color(223, 229, 221)
    pdf.cell(190, 8, short_text(article_title, 190), border=1, fill=True)
    pdf.ln(8)

    def draw_columns():
        pdf.set_font("Report", "B", 7)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(31, 92, 72)
        for heading, width, align in zip(
            ("Λογαριασμός", "Χρέωση", "Πίστωση"),
            widths,
            ("L", "R", "R"),
            strict=True,
        ):
            pdf.cell(width, row_height, heading, border=1, align=align, fill=True)
        pdf.ln(row_height)

    draw_columns()
    for account, debit, credit in rows:
        if pdf.get_y() + row_height > pdf.page_break_trigger:
            pdf.add_page()
            pdf.set_font("Report", "B", 8)
            pdf.set_text_color(23, 42, 49)
            pdf.set_fill_color(223, 229, 221)
            pdf.cell(190, 8, short_text(f"{article_title} · συνέχεια", 190), border=1, fill=True)
            pdf.ln(8)
            draw_columns()
        pdf.set_font("Report", "", 7)
        pdf.set_text_color(23, 33, 29)
        pdf.cell(widths[0], row_height, short_text(account, widths[0]), border=1)
        pdf.cell(widths[1], row_height, debit, border=1, align="R")
        pdf.cell(widths[2], row_height, credit, border=1, align="R")
        pdf.ln(row_height)
    pdf.ln(4)


def journal_article_content(entry, company):
    """Return one journal heading and account-only rows for PDF rendering."""
    transaction = entry["transaction"]
    status = "Οριστική" if transaction.is_posted else "Πρόχειρη"
    reference = f" · Σχετικό: {transaction.reference}" if transaction.reference else ""
    title = (
        f"{transaction.transaction_date:%d/%m/%Y} · {transaction.description}"
        f"{reference} · {status}"
    )
    rows = [
        (f"{account.code} · {account.name}", money(amount, company.currency), "—")
        for account, amount in entry["debits"]
    ]
    rows.extend(
        (f"{account.code} · {account.name}", "—", money(amount, company.currency))
        for account, amount in entry["credits"]
    )
    return title, rows


def build_olap(cube, company):
    """Pivot table of an OLAP cube; landscape so wide column dimensions fit."""
    from app.web.olap import cube_rows_as_table  # local import: olap imports the DB models

    spec = cube.spec
    pdf = ReportPDF("Κύβος OLAP", company.name, orientation="L")
    pdf.add_page()
    slices = " × ".join(dimension.label for dimension in cube.row_dimensions)
    if cube.column_dimension:
        slices += f" ανά {cube.column_dimension.label}"
    add_period(pdf, f"{spec.start:%d/%m/%Y} έως {spec.end:%d/%m/%Y} · {slices}")

    if not cube.is_empty:
        chart = cube.chart
        pdf.set_font("Report", "B", 8)
        pdf.set_text_color(23, 42, 49)
        caption = f"{chart['measure']['label']} ανά {chart['axis_label']}"
        if cube.column_dimension is None and len(chart["series"]) > 1:
            caption = f"{' · '.join(series['label'] for series in chart['series'])} ανά {chart['axis_label']}"
        elif chart["type"] == "heatmap":
            caption += f" · γραμμές: {chart['series_label']}"
        elif len(chart["series"]) > 1:
            caption += f" · χρώμα: {chart['series_label']}"
        pdf.cell(0, 5, caption)
        pdf.ln(6)
        usable_width = pdf.w - pdf.l_margin - pdf.r_margin
        draw_chart(pdf, chart, company.currency, pdf.l_margin, pdf.get_y(), usable_width, 78)

    headers, rows = cube_rows_as_table(cube)
    label_columns = len(cube.row_dimensions)
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    value_columns = len(headers) - label_columns
    label_width = min(48, usable * 0.4 / label_columns)
    value_width = (usable - label_width * label_columns) / max(value_columns, 1)
    widths = [label_width] * label_columns + [value_width] * value_columns
    aligns = ["L"] * label_columns + ["R"] * value_columns

    def fmt(measure, raw):
        return money(raw, company.currency) if measure.kind == "money" else f"{Decimal(raw):.0f}"

    measures = cube.measures
    body = []
    for index, row in enumerate(rows):
        is_total = index == len(rows) - 1
        values = list(row[:label_columns])
        for offset, raw in enumerate(row[label_columns:]):
            values.append(fmt(measures[offset % len(measures)], raw))
        summary = is_total or (index < len(cube.rows) and not cube.rows[index].is_leaf)
        body.append({"summary": summary, "values": values})
    add_table(pdf, headers, body, widths, aligns)
    return pdf, f"olap-{spec.start.isoformat()}-{spec.end.isoformat()}.pdf"
