"""Section builders. Each returns a list of Platypus flowables.

Layout rules shared by all sections
-----------------------------------
* Short sections are wrapped in KeepTogether (heading never stranded from its body).
* Long sections get a CondPageBreak before the heading so at least a few rows
  follow it, then flow/split naturally across pages.
* Tables use repeatRows=1 (header repeats on each page) and split between rows.
  If a single row is ever taller than a page, the generator retries with
  `row_split=True`, which lets ReportLab split *inside* a row. Text is never cut.
* Text arrives pre-structured from Rxplain; this module only escapes + typesets it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reportlab.lib.units import mm
from reportlab.platypus import (CondPageBreak, KeepTogether, Paragraph, Spacer, Table, TableStyle)

from . import theme as T
from .fonts import markup, clean_text, is_rtl
from .styles import Icon, rtl_variant

CW = T.CONTENT_W
FRAME_H = T.PAGE_H - T.FRAME_TOP - T.FRAME_BOTTOM
KEEP_LIMIT = 0.30 * FRAME_H          # sections shorter than this are kept on one page


@dataclass
class RenderContext:
    labels: dict
    styles: dict
    row_split: bool = False
    patient_line: str = ""
    page_count: int = 0


# ------------------------------------------------------------------ helpers
def _style(ctx, name, text):
    st = ctx.styles[name]
    return rtl_variant(st) if is_rtl(clean_text(text)) else st


def _P(text, style, ctx, bold=False, md=False):
    return Paragraph(markup(text, bold=bold, md_bold=md), _style(ctx, style, text))


def _heading(title: str, ctx, color=T.TEAL_700) -> Table:
    t = Table([[Paragraph(markup(title, bold=True), ctx.styles["h2"])]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, 0), 4.5, color),
        ("LINEBELOW", (0, 0), (-1, -1), 0.7, T.SLATE_200),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    t.spaceBefore = 15
    t.spaceAfter = 6
    return t


def _height(flowables) -> float:
    total = 0.0
    for f in flowables:
        _, h = f.wrap(CW, 10 ** 6)
        total += h + f.getSpaceBefore() + f.getSpaceAfter()
    return total


def _assemble(heading, body: list, min_start: float = 46 * mm) -> list:
    """Keep short sections whole; for long ones guarantee some body follows the heading."""
    if _height([heading] + body) <= KEEP_LIMIT:
        return [KeepTogether([heading] + body)]
    return [CondPageBreak(min_start), heading] + body


def _tbl(data, widths, ctx, repeat=0, **kw) -> Table:
    return Table(data, colWidths=widths, repeatRows=repeat, splitByRow=1,
                 splitInRow=1 if ctx.row_split else 0, **kw)


# ------------------------------------------------------------------ patient
def build_patient_section(patient: dict, ctx: RenderContext) -> list:
    """Title + patient information card (name, age, date, language – only fields provided)."""
    L = ctx.labels
    fields = [("name", L["patient_name"], 4.2), ("age", L["age"], 1.3),
              ("date", L["date"], 2.3), ("language", L["language"], 2.2)]
    fields = [f for f in fields if clean_text(patient.get(f[0]))]
    out = [Paragraph(markup(L["report_title"], bold=True), ctx.styles["h1"]), Spacer(1, 7)]
    if not fields:
        return out
    total = sum(w for _, _, w in fields)
    widths = [CW * w / total for _, _, w in fields]
    cells = [[Paragraph(markup(lbl.upper()), ctx.styles["label"]),
              Paragraph(markup(patient[key], bold=True), ctx.styles["value"])] for key, lbl, _ in fields]
    t = Table([cells], colWidths=widths, splitInRow=1 if ctx.row_split else 0)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), T.TEAL_50), ("BOX", (0, 0), (-1, -1), 0.9, T.TEAL_100),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, T.TEAL_100), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return out + [t, Spacer(1, 4)]


# ------------------------------------------------------------------ summary
def build_summary_section(summary: str, ctx: RenderContext) -> list:
    if not clean_text(summary):
        return []
    body = [_P(summary, "summary", ctx)]
    return _assemble(_heading(ctx.labels["summary"], ctx), body, 38 * mm)


# ------------------------------------------------------------------ terms
def build_terms_section(terms: list[dict], ctx: RenderContext) -> list:
    if not terms:
        return []
    L = ctx.labels
    data = [[_P(L["term_col"], "th", ctx), _P(L["meaning_col"], "th", ctx)]]
    for t in terms:
        data.append([_P(t["term"], "term", ctx), _P(t["definition"], "cell", ctx)])
    tbl = _tbl(data, [CW * 0.30, CW * 0.70], ctx, repeat=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), T.TEAL_700),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [T.colors.white, T.SLATE_50]),
        ("GRID", (0, 0), (-1, -1), 0.6, T.SLATE_300), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
    ]))
    return _assemble(_heading(L["terms"], ctx), [tbl])


# ------------------------------------------------------------------ icon lists
def _icon_list(items, icon, text_style, ctx, bg, line, box=True, top_pad=7) -> Table:
    def cell(i):
        if isinstance(i, dict):                      # warning with an explicit category label
            body = _P(i["text"], text_style, ctx, bold=(text_style == "warn"))
            return [_P(i["category"], "warn_cat", ctx, bold=True), body] if i.get("category") else body
        return _P(i, text_style, ctx, bold=(text_style == "warn"))
    data = [[Icon(icon, 14), cell(i)] for i in items]
    t = _tbl(data, [26, CW - 26], ctx)
    st = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 10), ("RIGHTPADDING", (0, 0), (0, -1), 2),
        ("LEFTPADDING", (1, 0), (1, -1), 6), ("RIGHTPADDING", (1, 0), (1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), top_pad), ("BOTTOMPADDING", (0, 0), (-1, -1), top_pad),
        ("TOPPADDING", (0, 0), (0, -1), top_pad + 2),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, line),
    ]
    if bg is not None:
        st.append(("BACKGROUND", (0, 0), (-1, -1), bg))
    if box:
        st.append(("BOX", (0, 0), (-1, -1), 0.9, line))
    t.setStyle(TableStyle(st))
    return t


def build_warnings_section(warnings: list[str], ctx: RenderContext) -> list:
    if not warnings:
        return []
    body = [_icon_list(warnings, "warn", "warn", ctx, T.RED_50, T.RED_200)]
    return _assemble(_heading(ctx.labels["warnings"], ctx, T.RED_700), body)


def build_checklist_section(checklist: list[str], ctx: RenderContext) -> list:
    if not checklist:
        return []
    body = [_icon_list(checklist, "check", "item", ctx, None, T.SLATE_200, box=True)]
    return _assemble(_heading(ctx.labels["checklist"], ctx), body)


def build_notes_section(notes: list[str], ctx: RenderContext) -> list:
    if not notes:
        return []
    body = [_icon_list(notes, "info", "note", ctx, T.AMBER_50, T.AMBER_200)]
    return _assemble(_heading(ctx.labels["notes"], ctx, T.AMBER_600), body)


# ------------------------------------------------------------------ follow-up
def build_followup_section(follow_up: str, ctx: RenderContext) -> list:
    if not clean_text(follow_up):
        return []
    body = [_P(follow_up, "followup", ctx)]
    return _assemble(_heading(ctx.labels["follow_up"], ctx, T.BLUE_700), body, 36 * mm)


# ------------------------------------------------------------------ medicines
_ZERO = {"0", "-", "—", ""}


def build_medicine_table(medicines: list[dict], ctx: RenderContext) -> list:
    """Medicine schedule. `Type` column is added only when at least one row has a type."""
    if not medicines:
        return []
    L = ctx.labels
    has_type = any(clean_text(m.get("type")) for m in medicines)
    if has_type:
        mm_w = [30, 17, 47, 19, 19, 19, 27]
        heads = [L["col_medicine"], L["col_type"], L["col_purpose"], L["col_morning"],
                 L["col_afternoon"], L["col_night"], L["col_duration"]]
        dose_cols = (3, 4, 5)
    else:
        mm_w = [36, 50, 20, 20, 20, 32]
        heads = [L["col_medicine"], L["col_purpose"], L["col_morning"], L["col_afternoon"],
                 L["col_night"], L["col_duration"]]
        dose_cols = (2, 3, 4)
    widths = [w * mm for w in mm_w]
    assert abs(sum(widths) - CW) < 1.0, "medicine column widths must sum to content width"

    head = [_P(h, "th_center" if i in dose_cols else "th", ctx) for i, h in enumerate(heads)]
    data = [head]
    for m in medicines:
        detail = []
        if clean_text(m.get("purpose")):
            detail.append(_P(m["purpose"], "cell", ctx))
        if clean_text(m.get("timing")):
            detail.append(Paragraph(f'<b>{markup(L["lbl_timing"], bold=True)}</b> {markup(m["timing"])}',
                                    _style(ctx, "cell_small", m["timing"])))
        if clean_text(m.get("side_effects")):
            detail.append(Paragraph(f'<b>{markup(L["lbl_side_effects"], bold=True)}</b> {markup(m["side_effects"])}',
                                    _style(ctx, "cell_small", m["side_effects"])))
        name_cell = [Paragraph(markup(m["name"], bold=True), ctx.styles["med_name"])]
        doses = []
        for k in ("morning", "afternoon", "night"):
            v = clean_text(m.get(k)) or "—"
            style = "dose_zero" if v in _ZERO else ("dose" if len(v) <= 4 else "dose_long")
            doses.append(Paragraph(markup(v), ctx.styles[style]))
        dur = _P(m.get("duration") or "—", "cell", ctx)
        row = [name_cell]
        if has_type:
            row.append(Paragraph(markup(m.get("type") or "—"), ctx.styles["med_type"]))
        row += [detail or Paragraph("—", ctx.styles["cell"])] + doses + [dur]
        data.append(row)

    tbl = _tbl(data, widths, ctx, repeat=1)
    first_dose, last_dose = dose_cols[0], dose_cols[-1]
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), T.TEAL_700),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [T.colors.white, T.SLATE_50]),
        ("GRID", (0, 0), (-1, -1), 0.6, T.SLATE_300),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("VALIGN", (first_dose, 1), (last_dose + 1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("LINEAFTER", (first_dose - 1, 1), (first_dose - 1, -1), 0.9, T.SLATE_300),
        ("BACKGROUND", (first_dose, 1), (last_dose, -1), T.TEAL_50),
    ]))
    return _assemble(_heading(L["schedule"], ctx), [tbl], 55 * mm)


# ------------------------------------------------------------------ diet (optional)
def build_diet_section(diet: dict, ctx: RenderContext) -> list:
    """Optional diet plan, present in the live Rxplain response (`diet_plan`)."""
    if not diet:
        return []
    L = ctx.labels
    body: list = []
    if clean_text(diet.get("goal")):
        body.append(Paragraph(f'<b>{markup(L["diet_goal"], bold=True)}</b> {markup(diet["goal"], md_bold=True)}',
                              ctx.styles["body"]))
        body.append(Spacer(1, 6))
    eat, avoid = diet.get("eat") or [], diet.get("avoid") or []
    if eat or avoid:
        data = [[_P(L["diet_eat"], "th", ctx), _P(L["diet_avoid"], "th", ctx)]]
        for i in range(max(len(eat), len(avoid))):
            def cell(lst):
                return (Paragraph(markup(lst[i], md_bold=True), ctx.styles["bullet"], bulletText="•")
                        if i < len(lst) else "")
            data.append([cell(eat), cell(avoid)])
        t = _tbl(data, [CW / 2, CW / 2], ctx, repeat=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), T.TEAL_700), ("BACKGROUND", (1, 0), (1, 0), T.RED_700),
            ("BACKGROUND", (0, 1), (0, -1), T.TEAL_50), ("BACKGROUND", (1, 1), (1, -1), T.RED_50),
            ("BOX", (0, 0), (-1, -1), 0.7, T.SLATE_300), ("LINEAFTER", (0, 0), (0, -1), 0.7, T.SLATE_300),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ]))
        body.append(t)
    if clean_text(diet.get("hydration")):
        body += [Spacer(1, 8), Paragraph(f'<b>{markup(L["diet_hydration"], bold=True)}</b> '
                                         f'{markup(diet["hydration"], md_bold=True)}', ctx.styles["body"])]
    tips = diet.get("tips") or []
    if tips:
        body += [Spacer(1, 8), Paragraph(markup(L["diet_tips"], bold=True), ctx.styles["item_bold"]), Spacer(1, 3)]
        body += [Paragraph(markup(t, md_bold=True), ctx.styles["bullet"], bulletText="•") for t in tips]
    if not body:
        return []
    return _assemble(_heading(L["diet"], ctx), body, 80 * mm)     # keep goal + table header + a few rows with the heading


# ------------------------------------------------------------------ closing disclaimer
def build_disclaimer_section(ctx: RenderContext) -> list:
    L = ctx.labels
    inner = [Paragraph(markup(L["disclaimer_title"], bold=True), ctx.styles["disc_title"]),
             Paragraph(markup(L["disclaimer_body"]), ctx.styles["disc_body"]),
             Spacer(1, 4),
             Paragraph(markup(L["reminder"]), ctx.styles["disc_body"])]
    t = Table([[inner]], colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), T.AMBER_50), ("BOX", (0, 0), (-1, -1), 0.9, T.AMBER_200),
        ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    t.spaceBefore = 18
    return [KeepTogether([t])]
