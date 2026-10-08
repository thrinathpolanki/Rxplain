"""Unicode font registration + script-aware text markup.

Why this exists
---------------
ReportLab's built-in fonts only cover Latin-1.  Rxplain output can be in 23 Indian
languages, usually mixed with English medicine names ("Paracetamol 500 mg").  No
single Noto font covers every script, so instead of choosing one font per report
we split every string into *script runs* and wrap each non-Latin run in a
``<font name=...>`` tag.  This works for:

  * pure English, pure regional, and mixed text,
  * any `language` value (the language field is only a hint, never required),
  * complex shaping (conjuncts, matras, Tamil/Malayalam ligatures) because
    ReportLab >= 4.4 shapes TTFont text through HarfBuzz when `uharfbuzz` is installed.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from xml.sax.saxutils import escape

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

from .theme import FONTS_DIR

log = logging.getLogger("rxplain_pdf.fonts")

try:                                    # HarfBuzz shaping (needed for correct Indic/Arabic text)
    import uharfbuzz  # noqa: F401
    SHAPING_AVAILABLE = True
except Exception:                       # pragma: no cover - depends on the deployment
    SHAPING_AVAILABLE = False
    log.warning("uharfbuzz is not installed: Latin text works, Indic scripts will not be shaped correctly")

def _patch_reportlab_setrise() -> None:
    """Workaround for a ReportLab 4.4.x bug seen with Arabic-script (Urdu) text.

    When HarfBuzz returns a vertical mark offset for the very first glyph of a text
    object, `PDFTextObject.setRise` does `self._code[-1]` on an empty list and raises
    IndexError. This makes the method tolerate an empty buffer; behaviour is otherwise identical.
    """
    from reportlab.pdfgen import textobject as _to
    cls = _to.PDFTextObject
    if getattr(cls.setRise, "_rx_patched", False):
        return

    def setRise(self, rise):
        v = f"{_to.fp_str(rise)} Ts"
        if self._code and self._code[-1].endswith(" Ts"):
            self._y += self._rise
            self._code[-1] = v
        else:
            self._rise = rise
            self._y -= rise
            self._code.append(v)

    setRise._rx_patched = True
    cls.setRise = setRise


_patch_reportlab_setrise()

# family key -> (reportlab family name, file stem)
FAMILIES = {
    "latin": ("RxSans", "NotoSans"),
    "deva": ("RxDeva", "NotoSansDevanagari"),     # Hindi, Marathi, Nepali, Konkani, Maithili, Dogri, Bodo, Sanskrit
    "beng": ("RxBeng", "NotoSansBengali"),        # Bengali, Assamese
    "guru": ("RxGuru", "NotoSansGurmukhi"),       # Punjabi
    "gujr": ("RxGujr", "NotoSansGujarati"),
    "orya": ("RxOrya", "NotoSansOriya"),          # Odia
    "taml": ("RxTaml", "NotoSansTamil"),
    "telu": ("RxTelu", "NotoSansTelugu"),
    "knda": ("RxKnda", "NotoSansKannada"),
    "mlym": ("RxMlym", "NotoSansMalayalam"),
    "arab": ("RxArab", "NotoNaskhArabic"),        # Urdu, Kashmiri, Sindhi  (see RTL note in README)
    "olck": ("RxOlck", "NotoSansOlChiki"),        # Santali
    "mtei": ("RxMtei", "NotoSansMeeteiMayek"),    # Manipuri (Meitei Mayek)
}

# (start, end, family) – inclusive code point ranges
_RANGES = [
    (0x0900, 0x097F, "deva"), (0xA8E0, 0xA8FF, "deva"),
    (0x0980, 0x09FF, "beng"),
    (0x0A00, 0x0A7F, "guru"),
    (0x0A80, 0x0AFF, "gujr"),
    (0x0B00, 0x0B7F, "orya"),
    (0x0B80, 0x0BFF, "taml"),
    (0x0C00, 0x0C7F, "telu"),
    (0x0C80, 0x0CFF, "knda"),
    (0x0D00, 0x0D7F, "mlym"),
    (0x0600, 0x06FF, "arab"), (0x0750, 0x077F, "arab"),
    (0xFB50, 0xFDFF, "arab"), (0xFE70, 0xFEFF, "arab"),
    (0x1C50, 0x1C7F, "olck"),
    (0xABC0, 0xABFF, "mtei"), (0xAAE0, 0xAAFF, "mtei"),
]
_ZERO_WIDTH = {0x200C, 0x200D, 0x200E, 0x200F}   # ZWNJ, ZWJ, LRM, RLM: stay in current run

_registered: dict[str, bool] = {}


def _try_register(key: str) -> bool:
    if key in _registered:
        return _registered[key]
    fam, stem = FAMILIES[key]
    reg, bold = FONTS_DIR / f"{stem}-Regular.ttf", FONTS_DIR / f"{stem}-Bold.ttf"
    if not reg.exists():
        log.warning("Font file missing: %s (script '%s' will fall back to Latin font)", reg.name, key)
        _registered[key] = False
        return False
    try:
        pdfmetrics.registerFont(TTFont(fam, str(reg)))
        pdfmetrics.registerFont(TTFont(f"{fam}-Bold", str(bold if bold.exists() else reg)))
        pdfmetrics.registerFontFamily(fam, normal=fam, bold=f"{fam}-Bold",
                                      italic=fam, boldItalic=f"{fam}-Bold")
        _registered[key] = True
    except Exception as exc:                       # corrupt font etc.
        log.warning("Could not register %s: %s", reg.name, exc)
        _registered[key] = False
    return _registered[key]


def register_fonts() -> None:
    """Register every available font. Idempotent and cheap after the first call."""
    for key in FAMILIES:
        _try_register(key)
    if not _registered.get("latin"):
        raise RuntimeError(
            f"NotoSans-Regular.ttf not found in {FONTS_DIR}. Copy the fonts/ folder into the project."
        )


# Convenience names used by styles
SANS = "RxSans"
SANS_BOLD = "RxSans-Bold"


def family_for_char(ch: str) -> str | None:
    """Return the script family for a char, or None if it is 'latin/neutral'."""
    cp = ord(ch)
    if cp < 0x0600:
        return None
    for lo, hi, fam in _RANGES:
        if lo <= cp <= hi:
            return fam
    return None


def font_for_family(key: str | None, bold: bool = False) -> str:
    if key is None or not _try_register(key):
        key = "latin"
    fam = FAMILIES[key][0]
    return f"{fam}-Bold" if bold else fam


def detect_scripts(text: str) -> set[str]:
    return {f for f in (family_for_char(c) for c in text) if f}


def is_rtl(text: str) -> bool:
    """True when most letters in `text` are Arabic-script (Urdu, Kashmiri, Sindhi)."""
    arab = other = 0
    for ch in text:
        if ch.isalpha():
            if family_for_char(ch) == "arab":
                arab += 1
            else:
                other += 1
    return arab > 0 and arab >= other


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BOLD_MD = re.compile(r"\*\*(.+?)\*\*", re.S)


def clean_text(value) -> str:
    """Coerce to str, normalise newlines, strip control chars. No wording changes."""
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n")
    s = _CTRL.sub("", s)
    return unicodedata.normalize("NFC", s).strip()


_WEAK_EXTRA = {0x0964, 0x0965}      # danda / double danda are shared by many Indic scripts


def _is_weak(ch: str) -> bool:
    """Punctuation, digits, symbols: take the font of the word they sit in."""
    cp = ord(ch)
    if cp in _WEAK_EXTRA:
        return True
    return not ch.isalpha() and not unicodedata.category(ch).startswith("M")


def _token_runs(tok: str) -> list[list]:
    """Runs for one whitespace-free word.  Whole word = ONE font whenever possible, because
    ReportLab mis-draws glyphs when fonts change inside an unbroken word."""
    strong = []
    for ch in tok:
        if ord(ch) in _ZERO_WIDTH or _is_weak(ch):
            continue
        strong.append(family_for_char(ch))
    kinds = set(strong)
    if not kinds:
        return [[None, tok]]
    if len(kinds) == 1:
        return [[next(iter(kinds)), tok]]
    # rare: e.g. "दवा(Paracetamol)" or script glued to Latin letters -> split at script changes
    runs: list[list] = []
    cur = next(f for f in strong)           # family of first strong char
    for ch in tok:
        if ord(ch) in _ZERO_WIDTH or _is_weak(ch):
            fam = cur
        else:
            fam = family_for_char(ch)
        if runs and runs[-1][0] == fam:
            runs[-1][1] += ch
        else:
            runs.append([fam, ch])
        cur = fam
    return runs


@lru_cache(maxsize=2048)
def _runs(text: str) -> tuple[tuple[str | None, str], ...]:
    """Split text into (family|None, substring) runs; whitespace joins the previous run."""
    runs: list[list] = []
    lead = ""
    for part in re.split(r"(\s+)", text):
        if not part:
            continue
        if part.isspace():
            if runs:
                runs[-1][1] += part
            else:
                lead += part
            continue
        for fam, chunk in _token_runs(part):
            if runs and runs[-1][0] == fam:
                runs[-1][1] += chunk
            else:
                runs.append([fam, chunk])
    if lead:
        if runs:
            runs[0][1] = lead + runs[0][1]
        else:
            runs.append([None, lead])
    return tuple((f, t) for f, t in runs)


def markup(value, bold: bool = False, md_bold: bool = False) -> str:
    """Return ReportLab Paragraph markup for `value`.

    * XML-escapes the text (so '&', '<' in medical text are safe)
    * wraps non-Latin script runs in <font name=...> with the right Noto font
    * turns newlines into <br/>
    * optional **bold** markdown handling (the Rxplain site does this for diet text)
    """
    text = clean_text(value)
    if not text:
        return ""

    def render(segment: str, seg_bold: bool) -> str:
        out = []
        for fam, chunk in _runs(segment):
            esc = escape(chunk).replace("\n", "<br/>")
            if fam is None:
                out.append(esc)
            else:
                out.append(f'<font name="{font_for_family(fam, bold or seg_bold)}">{esc}</font>')
        return "".join(out)

    if not md_bold:
        return render(text, False)
    parts, last = [], 0
    for m in _BOLD_MD.finditer(text):
        parts.append(render(text[last:m.start()], False))
        parts.append(f"<b>{render(m.group(1), True)}</b>")
        last = m.end()
    parts.append(render(text[last:], False))
    return "".join(parts)
