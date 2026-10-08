"""Paragraph styles + small vector icon flowables."""
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable

from . import theme as T
from .fonts import SANS, SANS_BOLD, SHAPING_AVAILABLE


def _s(name, **kw):
    base = dict(fontName=SANS, fontSize=T.BODY_SIZE, leading=T.BODY_LEADING,
                textColor=T.SLATE_800, allowWidows=0, allowOrphans=0, splitLongWords=1,
                shaping=1 if SHAPING_AVAILABLE else 0)   # enables HarfBuzz shaping for Indic/Arabic (ReportLab default is 0)
    base.update(kw)
    return ParagraphStyle(name, **base)


def make_styles() -> dict:
    return {
        "h1": _s("h1", fontName=SANS_BOLD, fontSize=T.H1_SIZE, leading=27, textColor=T.TEAL_700),
        "h2": _s("h2", fontName=SANS_BOLD, fontSize=T.H2_SIZE, leading=20, textColor=T.SLATE_900),
        "body": _s("body"),
        "summary": _s("summary", leftIndent=9, rightIndent=9, backColor=T.TEAL_50,
                      borderColor=T.TEAL_100, borderWidth=0.8, borderPadding=9, borderRadius=4,
                      spaceBefore=9, spaceAfter=14),
        "followup": _s("followup", leftIndent=9, rightIndent=9, backColor=T.BLUE_50,
                       borderColor=T.BLUE_100, borderWidth=0.8, borderPadding=9, borderRadius=4,
                       spaceBefore=9, spaceAfter=14),
        "item": _s("item"),
        "item_bold": _s("item_bold", fontName=SANS_BOLD),
        "warn": _s("warn", fontName=SANS_BOLD, textColor=T.RED_700),
        "warn_cat": _s("warn_cat", fontName=SANS_BOLD, fontSize=8.5, leading=11, textColor=T.RED_700),
        "note": _s("note", textColor=T.AMBER_800),
        "term": _s("term", fontName=SANS_BOLD, fontSize=T.TABLE_SIZE + 1, leading=15.5, textColor=T.TEAL_700),
        "cell": _s("cell", fontSize=T.TABLE_SIZE, leading=14.5),
        "cell_small": _s("cell_small", fontSize=T.SMALL_SIZE, leading=13.5, textColor=T.SLATE_700),
        "med_name": _s("med_name", fontName=SANS_BOLD, fontSize=T.TABLE_SIZE + 1, leading=15, textColor=T.TEAL_700),
        "med_type": _s("med_type", fontSize=T.SMALL_SIZE, leading=13, textColor=T.SLATE_500),
        "dose": _s("dose", fontName=SANS_BOLD, fontSize=13, leading=17, alignment=TA_CENTER),
        "dose_long": _s("dose_long", fontName=SANS_BOLD, fontSize=10, leading=13, alignment=TA_CENTER),
        "dose_zero": _s("dose_zero", fontName=SANS_BOLD, fontSize=13, leading=17, alignment=TA_CENTER,
                        textColor=T.SLATE_400),
        "th": _s("th", fontName=SANS_BOLD, fontSize=T.TABLE_HEAD_SIZE + 0.5, leading=11.5, textColor=T.colors.white),
        "th_center": _s("th_center", fontName=SANS_BOLD, fontSize=T.TABLE_HEAD_SIZE + 0.5, leading=11.5,
                        alignment=TA_CENTER, textColor=T.colors.white),
        "label": _s("label", fontName=SANS_BOLD, fontSize=8, leading=10.5, textColor=T.TEAL_700),
        "value": _s("value", fontName=SANS_BOLD, fontSize=12.5, leading=17, textColor=T.SLATE_900),
        "band": _s("band", fontSize=9, leading=12, textColor=T.SLATE_700),
        "small": _s("small", fontSize=T.SMALL_SIZE, leading=13.5, textColor=T.SLATE_700),
        "disc_title": _s("disc_title", fontName=SANS_BOLD, fontSize=10, leading=14, textColor=T.AMBER_800),
        "disc_body": _s("disc_body", fontSize=T.SMALL_SIZE, leading=13.5, textColor=T.AMBER_800),
        "bullet": _s("bullet", leftIndent=12, bulletIndent=0, bulletFontName=SANS_BOLD,
                     bulletColor=T.TEAL_600, fontSize=T.TABLE_SIZE, leading=14.5),
    }


_rtl_cache: dict = {}


def rtl_variant(style: ParagraphStyle) -> ParagraphStyle:
    """Right-aligned, RTL-wrapped copy of a left-aligned style (used for Urdu etc.)."""
    if style.alignment != 0:          # centred / already aligned styles are left alone
        return style
    if style.name not in _rtl_cache:
        _rtl_cache[style.name] = ParagraphStyle(style.name + "_rtl", parent=style, alignment=TA_RIGHT,
                                                wordWrap="RTL")
    return _rtl_cache[style.name]


class Icon(Flowable):
    """Tiny vector icons (no font glyphs needed): 'check' box, 'warn' triangle, 'info' circle."""

    def __init__(self, kind: str, size: float = 14):
        super().__init__()
        self.kind, self.size = kind, size
        self.width = self.height = size

    def wrap(self, aw, ah):
        return self.size, self.size

    def draw(self):
        c, s = self.canv, self.size
        if self.kind == "check":
            c.setStrokeColor(T.SLATE_500); c.setFillColor(T.colors.white); c.setLineWidth(1.3)
            c.roundRect(0.7, 0.7, s - 1.4, s - 1.4, 2.5, stroke=1, fill=1)
        elif self.kind == "warn":
            c.setFillColor(T.RED_700); c.setStrokeColor(T.RED_700); c.setLineJoin(1); c.setLineWidth(1.4)
            p = c.beginPath(); p.moveTo(s / 2, s - 0.8); p.lineTo(s - 0.8, 1.2); p.lineTo(0.8, 1.2); p.close()
            c.drawPath(p, stroke=1, fill=1)
            c.setStrokeColor(T.colors.white); c.setFillColor(T.colors.white); c.setLineWidth(1.5)
            c.line(s / 2, s * 0.40, s / 2, s * 0.68)
            c.circle(s / 2, s * 0.25, 0.9, stroke=0, fill=1)
        elif self.kind == "info":
            c.setFillColor(T.AMBER_600); c.circle(s / 2, s / 2, s / 2 - 0.5, stroke=0, fill=1)
            c.setStrokeColor(T.colors.white); c.setFillColor(T.colors.white); c.setLineWidth(1.6)
            c.line(s / 2, s * 0.22, s / 2, s * 0.52)
            c.circle(s / 2, s * 0.72, 1, stroke=0, fill=1)
