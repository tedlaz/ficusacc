"""Vector charts for PDF reports, drawn with fpdf2 primitives.

Mirrors the web renderers in ``static/js/olap.js`` (same palette, same forms) so the printed
report reads like the screen. All coordinates are in millimetres.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from fpdf import FPDF

PALETTE = ((25, 179, 160), (98, 115, 199), (245, 158, 11), (139, 92, 246),
           (240, 112, 95), (59, 130, 246), (236, 72, 153), (15, 138, 122))
OTHER_KEY = "__other__"
OTHER_COLOR = (154, 163, 156)
INK = (23, 33, 29)
MUTED = (109, 118, 111)
GRID = (222, 219, 210)
SURFACE = (255, 255, 255)
SEQUENTIAL = ((251, 240, 220), (168, 92, 14))
DIVERGING = ((201, 75, 59), (230, 227, 220), (37, 99, 184))
NICE_STEPS = (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10)


def money_symbol(currency: str) -> str:
    return "€" if currency.upper() == "EUR" else currency


def compact(value: float, measure: dict[str, Any], currency: str) -> str:
    """1234.5 -> "1,2K €" (money) or "1.235" (count); mirrors the on-screen axis format."""
    number = float(value)
    sign = "−" if number < 0 else ""
    magnitude = abs(number)
    if magnitude >= 1e6:
        text = f"{magnitude / 1e6:.{0 if magnitude >= 1e7 else 1}f}M".replace(".", ",")
    elif magnitude >= 1e3:
        text = f"{magnitude / 1e3:.{0 if magnitude >= 1e4 else 1}f}K".replace(".", ",")
    else:
        text = f"{magnitude:,.0f}".replace(",", ".")
    suffix = f" {money_symbol(currency)}" if measure["kind"] == "money" else ""
    return f"{sign}{text}{suffix}"


def nice_step(span: float, count: int = 5) -> float:
    raw = span / count or 1
    magnitude = 10 ** math.floor(math.log10(raw))
    return next((step * magnitude for step in (1, 2, 2.5, 5, 10) if step * magnitude >= raw), 10 * magnitude)


def nice_ceil(value: float) -> float:
    if value <= 0:
        return 0
    magnitude = 10 ** math.floor(math.log10(value))
    return next(step for step in NICE_STEPS if step * magnitude >= value) * magnitude


def linear_scale(low: float, high: float) -> tuple[float, float, list[float]]:
    """Return (lo, hi, ticks); a small negative tail gets a tight bound instead of a whole step."""
    step = nice_step(max(high, 0) - min(low, 0) or 1)
    hi = math.ceil(high / step) * step if high > 0 else 0
    if low >= 0:
        lo = 0.0
    elif -low < step:
        lo = -nice_ceil(-low)
    else:
        lo = -math.ceil(-low / step) * step
    ticks = [round(value * step, 10) for value in range(int(hi / step) + 1)]
    ticks += [round(-value * step, 10) for value in range(1, int(-lo / step) + 1)]
    if lo < 0 and lo not in ticks:
        ticks.append(lo)
    return lo, hi, ticks


def series_color(series: dict[str, Any], index: int) -> tuple[int, int, int]:
    return OTHER_COLOR if series["key"] == OTHER_KEY else PALETTE[index % len(PALETTE)]


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def luminance(color: tuple[int, int, int]) -> float:
    r, g, b = (channel / 255 for channel in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def truncate(pdf: FPDF, label: str, width: float) -> str:
    if pdf.get_string_width(label) <= width:
        return label
    while label and pdf.get_string_width(f"{label}…") > width:
        label = label[:-1]
    return f"{label}…"


class ChartBox:
    """Plot-area geometry plus the shared axis/label helpers."""

    def __init__(self, pdf: FPDF, chart: dict[str, Any], currency: str, x: float, y: float, w: float, h: float):
        self.pdf, self.chart, self.currency = pdf, chart, currency
        self.x, self.y, self.w, self.h = x, y, w, h
        self.measure = chart["measure"]
        self.categories = chart["categories"]
        self.series = [
            {**item, "numbers": [float(Decimal(value)) for value in item["values"]], "color": series_color(item, index)}
            for index, item in enumerate(chart["series"])
        ]
        self.left = x + 22
        self.right = x + w - 4
        self.top = y + 4
        self.bottom = y + h - 12

    # -- axes -------------------------------------------------------------
    def y_of(self, value: float, lo: float, hi: float) -> float:
        return self.bottom - (value - lo) / ((hi - lo) or 1) * (self.bottom - self.top)

    def draw_axes(self, lo: float, hi: float, ticks: list[float], percent: bool = False) -> None:
        pdf = self.pdf
        pdf.set_font("Report", "", 6.5)
        pdf.set_text_color(*MUTED)
        drawn: list[float] = []
        for tick in sorted(ticks):
            y = self.y_of(tick, lo, hi)
            pdf.set_draw_color(*(INK if tick == 0 and lo < 0 else GRID))
            pdf.set_line_width(0.35 if tick == 0 and lo < 0 else 0.2)
            pdf.line(self.left, y, self.right, y)
            if any(abs(other - y) < 3 for other in drawn):
                continue
            drawn.append(y)
            label = f"{tick:g}%" if percent else compact(tick, self.measure, self.currency)
            pdf.set_xy(self.x, y - 1.6)
            pdf.cell(self.left - self.x - 2, 3.2, label, align="R")

    def draw_category_labels(self, slot: float, baseline: float | None = None) -> None:
        pdf = self.pdf
        pdf.set_font("Report", "", 6.5)
        pdf.set_text_color(*MUTED)
        every = max(1, math.ceil(len(self.categories) / max(int((self.right - self.left) / 16), 1)))
        y = (baseline if baseline is not None else self.bottom) + 1.5
        for index, category in enumerate(self.categories):
            if index % every and index != len(self.categories) - 1:
                continue
            pdf.set_xy(self.left + slot * index, y)
            pdf.cell(slot, 3.5, truncate(pdf, category["label"], slot - 1), align="C")

    def draw_legend(self, items: list[tuple[str, tuple[int, int, int]]]) -> float:
        """Legend row above the plot; returns the height consumed."""
        if len(items) < 2:
            return 0
        pdf = self.pdf
        pdf.set_font("Report", "B", 6.5)
        pdf.set_text_color(*INK)
        x, y = self.x, self.y
        for label, color in items:
            width = pdf.get_string_width(label) + 7
            if x + width > self.x + self.w:
                x, y = self.x, y + 4.5
            pdf.set_fill_color(*color)
            pdf.ellipse(x, y + 0.9, 2.2, 2.2, style="F")
            pdf.set_xy(x + 3, y)
            pdf.cell(width - 3, 4, label)
            x += width + 3
        used = y + 5 - self.y
        self.top += used
        return used

    def direct_label(self, text: str, x: float, y: float, align: str = "C") -> None:
        pdf = self.pdf
        pdf.set_font("Report", "B", 6.5)
        pdf.set_text_color(*INK)
        width = pdf.get_string_width(text) + 1
        left = {"C": x - width / 2, "L": x, "R": x - width}[align]
        pdf.set_xy(max(self.x, min(left, self.x + self.w - width)), y)
        pdf.cell(width, 3, text, align=align)

    # -- forms --------------------------------------------------------------
    def bars(self, mode: str) -> None:
        stacked = mode != "bar"
        percent = mode == "stacked100"
        self.draw_legend([(item["label"], item["color"]) for item in self.series])
        count = len(self.categories)
        slot = (self.right - self.left) / max(count, 1)
        scales, low, high = [], 0.0, 0.0
        for index in range(count):
            values = [item["numbers"][index] for item in self.series]
            total_abs = sum(abs(value) for value in values)
            factor = (100 / total_abs if total_abs else 0) if percent else 1
            scales.append(factor)
            if stacked:
                high = max(high, sum(value for value in values if value > 0) * factor)
                low = min(low, sum(value for value in values if value < 0) * factor)
            else:
                high, low = max(high, *values), min(low, *values)
        if percent:
            lo, hi = (-100.0 if low < 0 else 0.0), (100.0 if high > 0 else 0.0)
            ticks = [float(value) for value in range(int(lo), int(hi) + 1, 25)]
        else:
            lo, hi, ticks = linear_scale(low, high)
        self.draw_axes(lo, hi, ticks, percent)
        self.draw_category_labels(slot)
        zero = self.y_of(0, lo, hi)
        maxima = [max(range(count), key=lambda i, s=item: abs(s["numbers"][i])) for item in self.series]

        for index in range(count):
            if stacked:
                width = min(6.0, slot * 0.6)
                x = self.left + slot * index + (slot - width) / 2
                pos_top = neg_bottom = 0.0
                for item in self.series:
                    value = item["numbers"][index] * scales[index]
                    if not value:
                        continue
                    start = pos_top if value > 0 else neg_bottom
                    end = start + value
                    if value > 0:
                        pos_top = end
                    else:
                        neg_bottom = end
                    y0, y1 = self.y_of(start, lo, hi), self.y_of(end, lo, hi)
                    gap = min(0.5, abs(y1 - y0))
                    self._bar(x, y0 - gap if value > 0 else y0 + gap, y1, width, item["color"], radius=0.8)
            else:
                gap = 0.5
                inner = min(6.0 * len(self.series) + gap * (len(self.series) - 1), slot * 0.78)
                width = max((inner - gap * (len(self.series) - 1)) / max(len(self.series), 1), 0.6)
                start_x = self.left + slot * index + (slot - inner) / 2
                for position, item in enumerate(self.series):
                    value = item["numbers"][index]
                    if not value:
                        continue
                    x = start_x + position * (width + gap)
                    end = self.y_of(value, lo, hi)
                    self._bar(x, zero, end, width, item["color"])
                    if len(self.series) <= 4 and maxima[position] == index:
                        self.direct_label(compact(value, self.measure, self.currency), x + width / 2,
                                          end - 3.4 if value > 0 else end + 0.6)

    def _bar(self, x: float, baseline: float, end: float, width: float, color, radius: float = 1.0) -> None:
        pdf = self.pdf
        pdf.set_fill_color(*color)
        top, height = min(baseline, end), abs(baseline - end)
        if height <= 0:
            return
        corners = ("TOP_LEFT", "TOP_RIGHT") if end < baseline else ("BOTTOM_LEFT", "BOTTOM_RIGHT")
        pdf.rect(x, top, width, height, style="F", round_corners=corners,
                 corner_radius=min(radius, width / 2, height))

    def lines(self, area: bool) -> None:
        pdf = self.pdf
        self.draw_legend([(item["label"], item["color"]) for item in self.series])
        count = len(self.categories)
        slot = (self.right - self.left) / max(count, 1)
        values = [value for item in self.series for value in item["numbers"]] or [0.0]
        lo, hi, ticks = linear_scale(min(0.0, *values), max(0.0, *values))
        self.draw_axes(lo, hi, ticks)
        self.draw_category_labels(slot)
        zero = self.y_of(0, lo, hi)

        def x_of(index: int) -> float:
            return self.left + slot * index + slot / 2

        for item in self.series:
            points = [(x_of(index), self.y_of(value, lo, hi)) for index, value in enumerate(item["numbers"])]
            if not points:
                continue
            if area:
                wash = mix(SURFACE, item["color"], 0.16)
                pdf.set_fill_color(*wash)
                polygon = [(points[0][0], zero), *points, (points[-1][0], zero)]
                pdf.polygon(polygon, style="F")
            pdf.set_draw_color(*item["color"])
            pdf.set_line_width(0.5)
            if len(points) > 1:
                pdf.polyline(points, style="D")
            for px, py in points:
                pdf.set_draw_color(*SURFACE)
                pdf.set_fill_color(*item["color"])
                pdf.set_line_width(0.4)
                pdf.ellipse(px - 1, py - 1, 2, 2, style="DF")
            if len(self.series) <= 4:
                px, py = points[-1]
                self.direct_label(compact(item["numbers"][-1], self.measure, self.currency), px + 2, py - 1.5, "L")

    def donut(self) -> None:
        pdf = self.pdf
        totals = [
            {"key": category["key"], "label": category["label"],
             "value": sum(abs(item["numbers"][index]) for item in self.series)}
            for index, category in enumerate(self.categories)
        ]
        slices = sorted((item for item in totals if item["value"] > 0), key=lambda item: item["value"], reverse=True)
        if len(slices) > 6:
            rest = slices[5:]
            slices = [*slices[:5], {"key": OTHER_KEY, "label": "Λοιπά", "value": sum(item["value"] for item in rest)}]
        # A folded "Λοιπά" row plus the donut's own tail must not become two grey slices.
        others = [item for item in slices if item["key"] == OTHER_KEY]
        if len(others) > 1:
            slices = [item for item in slices if item["key"] != OTHER_KEY]
            slices.append({"key": OTHER_KEY, "label": "Λοιπά", "value": sum(item["value"] for item in others)})
        total = sum(item["value"] for item in slices) or 1
        colors = [OTHER_COLOR if item["key"] == OTHER_KEY else PALETTE[index % len(PALETTE)]
                  for index, item in enumerate(slices)]
        self.draw_legend([(item["label"], color) for item, color in zip(slices, colors, strict=True)])
        radius = min((self.bottom - self.top) / 2 - 6, 30)
        cx, cy = self.x + self.w / 2, self.top + (self.bottom - self.top) / 2
        angle = -90.0
        for item, color in zip(slices, colors, strict=True):
            sweep = item["value"] / total * 360
            pdf.set_fill_color(*color)
            pdf.set_draw_color(*SURFACE)
            pdf.set_line_width(0.5)
            pdf.polygon(self._sector(cx, cy, radius, angle, angle + sweep), style="DF")
            share = round(item["value"] / total * 1000) / 10
            if sweep > 20:
                mid = math.radians(angle + sweep / 2)
                lx, ly = cx + (radius + 5) * math.cos(mid), cy + (radius + 5) * math.sin(mid)
                align = "R" if math.cos(mid) < -0.1 else "L" if math.cos(mid) > 0.1 else "C"
                self.direct_label(f"{share:g}%", lx, ly - 1.5, align)
            angle += sweep
        pdf.set_fill_color(*SURFACE)
        pdf.ellipse(cx - radius * 0.66, cy - radius * 0.66, radius * 1.32, radius * 1.32, style="F")
        pdf.set_font("Report", "B", 12)
        pdf.set_text_color(*INK)
        pdf.set_xy(cx - radius, cy - 4)
        pdf.cell(radius * 2, 5, compact(total, self.measure, self.currency), align="C")
        pdf.set_font("Report", "", 6)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(cx - radius, cy + 1.5)
        pdf.cell(radius * 2, 3, self.measure["label"].upper(), align="C")

    @staticmethod
    def _sector(cx: float, cy: float, radius: float, start: float, end: float) -> list[tuple[float, float]]:
        """Pie-slice outline, angles in degrees clockwise from 3 o'clock (PDF y grows downward)."""
        steps = max(2, int((end - start) / 3))
        points = [(cx, cy)]
        for step in range(steps + 1):
            theta = math.radians(start + (end - start) * step / steps)
            points.append((cx + radius * math.cos(theta), cy + radius * math.sin(theta)))
        return points

    def heatmap(self) -> None:
        pdf = self.pdf
        rows, columns = len(self.series), len(self.categories)
        label_width = 42
        left = self.x + label_width
        cell_w = (self.right - left) / max(columns, 1)
        cell_h = min(7.0, max(4.0, (self.bottom - self.top - 12) / max(rows, 1)))
        values = [value for item in self.series for value in item["numbers"]] or [0.0]
        diverging = self.measure["signed"] and any(value < 0 for value in values)
        peak = max(abs(value) for value in values) or 1

        def color_of(value: float):
            if diverging:
                t = value / peak
                return mix(DIVERGING[1], DIVERGING[0], -t) if t < 0 else mix(DIVERGING[1], DIVERGING[2], t)
            return mix(SEQUENTIAL[0], SEQUENTIAL[1], abs(value) / peak)

        for row, item in enumerate(self.series):
            y = self.top + row * cell_h
            pdf.set_font("Report", "B", 6.5)
            pdf.set_text_color(*INK)
            pdf.set_xy(self.x, y + cell_h / 2 - 1.6)
            pdf.cell(label_width - 2, 3.2, truncate(pdf, item["label"], label_width - 3), align="R")
            for column, value in enumerate(item["numbers"]):
                fill = color_of(value)
                pdf.set_fill_color(*fill)
                pdf.rect(left + column * cell_w + 0.3, y + 0.3, cell_w - 0.6, cell_h - 0.6, style="F",
                         round_corners=True, corner_radius=0.8)
                if value and cell_w >= 13 and cell_h >= 4.5:
                    pdf.set_font("Report", "B", 6)
                    pdf.set_text_color(*(INK if luminance(fill) > 0.55 else SURFACE))
                    pdf.set_xy(left + column * cell_w, y + cell_h / 2 - 1.5)
                    pdf.cell(cell_w, 3, compact(value, self.measure, self.currency), align="C")
        grid_bottom = self.top + rows * cell_h
        self.left = left
        self.draw_category_labels(cell_w, grid_bottom)
        # Scale legend: a strip of small swatches with end labels.
        legend_y = grid_bottom + 7
        legend_w, steps = 40, 24
        for step in range(steps):
            t = step / (steps - 1)
            color = mix(DIVERGING[0], DIVERGING[1], t * 2) if diverging and t < 0.5 else \
                mix(DIVERGING[1], DIVERGING[2], (t - 0.5) * 2) if diverging else mix(SEQUENTIAL[0], SEQUENTIAL[1], t)
            pdf.set_fill_color(*color)
            pdf.rect(left + step * legend_w / steps, legend_y, legend_w / steps + 0.1, 2, style="F")
        pdf.set_font("Report", "", 6.5)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(left - 20, legend_y - 0.8)
        pdf.cell(19, 3.5, compact(-peak if diverging else 0, self.measure, self.currency), align="R")
        pdf.set_xy(left + legend_w + 1, legend_y - 0.8)
        pdf.cell(20, 3.5, compact(peak, self.measure, self.currency))


def draw_chart(pdf: FPDF, chart: dict[str, Any], currency: str, x: float, y: float, w: float, h: float) -> None:
    """Draw the cube's chart (as prepared by ``olap.chart_payload``) inside the given box."""
    box = ChartBox(pdf, chart, currency, x, y, w, h)
    kind = chart["type"]
    with pdf.local_context():
        if kind in {"line", "area"}:
            box.lines(area=kind == "area")
        elif kind == "donut":
            box.donut()
        elif kind == "heatmap":
            box.heatmap()
        else:
            box.bars(kind)
    pdf.set_y(y + h + 4)
