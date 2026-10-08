"""Page chrome: branded header + footer drawn on every page, and the document template."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph

from . import theme as T
from .fonts import SANS, SANS_BOLD, markup, clean_text


def _truncate(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip() + "…"


def draw_header(c: Canvas, page_no: int, ctx) -> None:
    """Rxplain logo + name (left), 'Powered by Trimitha' + logo (right), teal rule."""
    top = T.PAGE_H
    logo = 13 * mm
    y0 = top - 7 * mm - logo
    x = T.MARGIN_X

    c.drawImage(str(T.RXPLAIN_LOGO), x, y0, logo, logo, mask="auto")
    tx = x + logo + 4 * mm
    c.setFillColor(T.TEAL_700); c.setFont(SANS_BOLD, 22)
    c.drawString(tx, y0 + logo * 0.46, T.BRAND_NAME)
    c.setFillColor(T.SLATE_500); c.setFont(SANS, 9.5)
    c.drawString(tx, y0 + logo * 0.46 - 13.5, T.BRAND_TAGLINE)

    # Right block: "Powered by / Trimitha" text (the Trimitha logo tile is optional, see theme.SHOW_TRIMITHA_LOGO)
    rx = T.PAGE_W - T.MARGIN_X
    name_w = stringWidth(T.POWERED_BY_BRAND, SANS_BOLD, 14)
    if T.SHOW_TRIMITHA_LOGO:
        bw = T.TRIMITHA_BORDER_W
        box = logo
        c.setStrokeColor(T.PEACOCK_NAVY); c.setFillColor(colors.white); c.setLineWidth(bw)
        c.roundRect(rx - box + bw / 2, y0 + bw / 2, box - bw, box - bw, 2.8 * mm, stroke=1, fill=1)
        gap = bw + 1.1
        tri = box - 2 * gap
        c.saveState()
        clip = c.beginPath(); clip.roundRect(rx - box + gap, y0 + gap, tri, tri, 1.9 * mm)
        c.clipPath(clip, stroke=0, fill=0)
        c.drawImage(str(T.TRIMITHA_LOGO), rx - box + gap, y0 + gap, tri, tri)
        c.restoreState()
        text_right = rx - box - 3 * mm
    else:
        text_right = rx
    base = y0 + logo / 2 - 10                    # vertically centred on the Rxplain logo
    c.setFillColor(T.SLATE_800); c.setFont(SANS_BOLD, 14)
    c.drawRightString(text_right, base, T.POWERED_BY_BRAND)
    c.setFillColor(T.SLATE_500); c.setFont(SANS, 8.5)
    c.drawRightString(text_right, base + 15, T.POWERED_BY)
    c.linkURL(T.FOOTER_RIGHT_URL, (text_right - max(name_w, 52), base - 4, text_right, base + 24), relative=0)

    # rule
    rule_y = top - 24 * mm
    c.setStrokeColor(T.TEAL_700); c.setLineWidth(1.6)
    c.line(T.MARGIN_X, rule_y, T.PAGE_W - T.MARGIN_X, rule_y)

    # continuation strip with patient identity (pages 2+)
    if page_no > 1 and ctx.patient_line:
        p = Paragraph(ctx.patient_line, ctx.styles["band"])
        _, h = p.wrap(T.CONTENT_W, T.CONT_BAND_H)
        p.drawOn(c, T.MARGIN_X, rule_y - 2.2 * mm - h)


def draw_footer(c: Canvas, page_no: int, total: int, ctx) -> None:
    """rxplain.vercel.app (left) · Page X of Y (centre) · trimitha.co.in (right)."""
    y_line = T.FOOTER_H
    c.setStrokeColor(T.SLATE_300); c.setLineWidth(0.7)
    c.line(T.MARGIN_X, y_line, T.PAGE_W - T.MARGIN_X, y_line)
    base = y_line - 6.2 * mm
    size = 9.5
    c.setFont(SANS_BOLD, size); c.setFillColor(T.TEAL_700)
    c.drawString(T.MARGIN_X, base, T.FOOTER_LEFT_TEXT)
    w = stringWidth(T.FOOTER_LEFT_TEXT, SANS_BOLD, size)
    c.linkURL(T.FOOTER_LEFT_URL, (T.MARGIN_X, base - 3, T.MARGIN_X + w, base + size), relative=0)
    c.drawRightString(T.PAGE_W - T.MARGIN_X, base, T.FOOTER_RIGHT_TEXT)
    w = stringWidth(T.FOOTER_RIGHT_TEXT, SANS_BOLD, size)
    c.linkURL(T.FOOTER_RIGHT_URL, (T.PAGE_W - T.MARGIN_X - w, base - 3, T.PAGE_W - T.MARGIN_X, base + size), relative=0)
    c.setFont(SANS, size); c.setFillColor(T.SLATE_500)
    lab = ctx.labels
    c.drawCentredString(T.PAGE_W / 2, base, f"{lab['page']} {page_no} {lab['of']} {total}")


def make_canvas_class(ctx):
    """Two-pass canvas so the footer can print 'Page X of Y'."""

    class RxCanvas(Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._states: list[dict] = []

        def showPage(self):
            self._states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._states)
            ctx.page_count = total
            ann_count = self._annotationCount        # keep link-annotation ids unique across pages
            for i, st in enumerate(self._states, 1):
                self.__dict__.update(st)
                self._annotationCount = ann_count
                draw_header(self, i, ctx)
                draw_footer(self, i, total, ctx)
                ann_count = self._annotationCount
                Canvas.showPage(self)
            Canvas.save(self)

    return RxCanvas


def make_doc(target, ctx, title: str) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        target, pagesize=T.PAGE_SIZE, title=title, author="Rxplain by Trimitha",
        subject="Prescription explanation generated by Rxplain", creator="Rxplain PDF Template",
        leftMargin=T.MARGIN_X, rightMargin=T.MARGIN_X, topMargin=T.FRAME_TOP, bottomMargin=T.FRAME_BOTTOM,
    )
    frame = Frame(T.MARGIN_X, T.FRAME_BOTTOM, T.CONTENT_W, T.PAGE_H - T.FRAME_TOP - T.FRAME_BOTTOM,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    return doc
