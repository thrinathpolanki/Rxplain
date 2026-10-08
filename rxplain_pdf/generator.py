"""Public API: create_rxplain_pdf()."""
from __future__ import annotations

import io
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, date as _date
from pathlib import Path
from urllib.parse import quote

from reportlab.platypus.doctemplate import LayoutError

from . import theme as T
from .fonts import register_fonts, clean_text
from .sections import (RenderContext, build_checklist_section, build_diet_section, build_disclaimer_section,
                       build_followup_section, build_medicine_table, build_notes_section,
                       build_patient_section, build_summary_section, build_terms_section,
                       build_warnings_section)
from .styles import make_styles
from .template import make_canvas_class, make_doc, _truncate


# ===================================================================== filename
def safe_filename(patient_name: str | None, ascii_only: bool = False) -> str:
    """Rxplain-[PatientName]-Medical-Summary.pdf with a sanitised patient name.

    Keeps letters/digits/combining marks of any script (so Indic names survive),
    turns whitespace/underscores/dots into '-', drops everything else (path
    separators, quotes, control chars...) and caps the length.
    """
    name = unicodedata.normalize("NFC", clean_text(patient_name))
    if ascii_only:
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    out = []
    for ch in name:
        cat = unicodedata.category(ch)
        if cat[0] in "LMN":
            out.append(ch)
        elif ch.isspace() or ch in "-_.":
            out.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(out)).strip("-")[:60].strip("-")
    return f"Rxplain-{slug or 'Patient'}-Medical-Summary.pdf"


@dataclass
class PdfResult:
    filename: str
    pdf_bytes: bytes
    page_count: int
    path: Path | None = None

    def content_disposition(self, inline: bool = False) -> str:
        """HTTP header value that works for ASCII *and* non-ASCII (Indic) filenames."""
        ascii_name = self.filename.encode("ascii", "ignore").decode() or "Rxplain-Medical-Summary.pdf"
        ascii_name = re.sub(r'[^A-Za-z0-9._-]', "-", ascii_name)
        if ascii_name == "Rxplain-Medical-Summary.pdf" or ascii_name.startswith("Rxplain--"):
            ascii_name = "Rxplain-Patient-Medical-Summary.pdf"
        kind = "inline" if inline else "attachment"
        return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(self.filename)}"


# ===================================================================== normalisation
def _items(v) -> list:
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _text_list(v, keys=("text", "warning", "message", "note", "item")) -> list[str]:
    out = []
    for x in _items(v):
        if isinstance(x, dict):
            x = next((x[k] for k in keys if k in x), None)
        s = clean_text(x)
        if s:
            out.append(s)
    return out


def _norm_terms(v) -> list[dict]:
    out = []
    for x in _items(v):
        if isinstance(x, dict):
            term = clean_text(x.get("term") or x.get("name"))
            definition = clean_text(x.get("definition") or x.get("meaning") or x.get("explanation"))
        else:
            term, definition = "", clean_text(x)
        if term or definition:
            out.append({"term": term, "definition": definition})
    return out


def _norm_warnings(v) -> list[dict]:
    """Warnings may be plain strings (live Rxplain data) or {category, text} objects."""
    out = []
    for x in _items(v):
        if isinstance(x, dict):
            text = clean_text(x.get("text") or x.get("warning") or x.get("message"))
            cat = clean_text(x.get("category"))
        else:
            text, cat = clean_text(x), ""
        if text:
            out.append({"text": text, "category": cat})
    return out


_SCHEDULE_KEYS = ("morning", "afternoon", "night", "duration")


def _mkey(name) -> str:
    return re.sub(r"\s+", " ", clean_text(name)).casefold()


def _norm_medicines(medicines, dosage_table) -> list[dict]:
    """Merge Rxplain's `medicines` (purpose/timing/side_effects) with `dosage_table`
    (morning/afternoon/night/duration) by *exact* medicine name.  Rows are never
    fuzzy-matched, so two similarly named drugs can never be merged by accident.
    Also accepts one flat list where each item already carries every field."""
    rows: "OrderedDict[str, dict]" = OrderedDict()

    def upsert(src: dict, fields: tuple):
        dosage = src.get("dosage")
        if isinstance(dosage, dict):                       # {"dosage": {"morning":..}} contract shape
            src = {**{k: dosage.get(k) for k in _SCHEDULE_KEYS}, **{k: v for k, v in src.items() if v not in (None, "")}}
        name = clean_text(src.get("name") or src.get("medicine"))
        if not name:
            return
        row = rows.setdefault(_mkey(name), {"name": name})
        for f in fields:
            val = clean_text(src.get(f))
            if val and not row.get(f):
                row[f] = val

    for m in _items(medicines):
        if isinstance(m, dict):
            upsert(m, ("type", "purpose", "timing", "side_effects") + _SCHEDULE_KEYS)
        elif clean_text(m):
            rows.setdefault(_mkey(m), {"name": clean_text(m)})
    for d in _items(dosage_table):
        if isinstance(d, dict):
            upsert(d, ("type",) + _SCHEDULE_KEYS)
        elif clean_text(d):
            rows.setdefault(_mkey(d), {"name": clean_text(d)})
    return list(rows.values())


def _norm_diet(d) -> dict:
    if not isinstance(d, dict):
        return {}
    return {"goal": clean_text(d.get("goal")), "eat": _text_list(d.get("eat")), "avoid": _text_list(d.get("avoid")),
            "hydration": clean_text(d.get("hydration")), "tips": _text_list(d.get("tips"))}


def _fmt_date(v, now: datetime) -> str:
    s = clean_text(v)
    if not s:
        return now.strftime("%d %b %Y")
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).strftime("%d %b %Y")
        except ValueError:
            pass
    return s


def normalise_input(data: dict, now: datetime | None = None) -> dict:
    """Accepts BOTH the live Rxplain response shape (critical_warnings, medicines + dosage_table,
    diet_plan) and the flat shape (warnings, medicines with schedule fields). Returns a clean dict."""
    if not isinstance(data, dict):
        raise TypeError("Rxplain PDF input must be a JSON object / dict")
    now = now or datetime.now()
    patient_in = data.get("patient") if isinstance(data.get("patient"), dict) else {}
    pick = lambda *keys: next((data.get(k) if data.get(k) not in (None, "") else patient_in.get(k)
                               for k in keys if (data.get(k) not in (None, "") or patient_in.get(k) not in (None, ""))), "")
    result = {
        "patient": {
            "name": clean_text(pick("name", "patient_name")),
            "age": clean_text(pick("age")),
            "language": clean_text(pick("language")),
            "date": _fmt_date(pick("date", "report_date", "analysis_date"), now),
        },
        "summary": "\n".join(_text_list(data.get("summary"))),
        "terms": _norm_terms(data.get("terms")),
        "warnings": _norm_warnings(data.get("critical_warnings") if data.get("critical_warnings") not in (None, "", [])
                                   else data.get("warnings")),
        "medicines": _norm_medicines(data.get("medicines"), data.get("dosage_table")),
        "checklist": _text_list(data.get("checklist")),
        "notes": _text_list(data.get("notes")),
        "follow_up": "\n".join(_text_list(data.get("follow_up"))),
        "diet_plan": _norm_diet(data.get("diet_plan")),
    }
    has_content = any(result[k] for k in ("summary", "terms", "warnings", "medicines", "checklist",
                                          "notes", "follow_up")) or any(result["diet_plan"].values())
    if not has_content:
        raise ValueError("No Rxplain result content supplied (summary, medicines, terms, ... are all empty).")
    return result


# ===================================================================== build
def _build_story(d: dict, ctx: RenderContext) -> list:
    story: list = []
    story += build_patient_section(d["patient"], ctx)
    story += build_summary_section(d["summary"], ctx)
    story += build_terms_section(d["terms"], ctx)
    story += build_warnings_section(d["warnings"], ctx)
    story += build_medicine_table(d["medicines"], ctx)
    story += build_checklist_section(d["checklist"], ctx)
    story += build_notes_section(d["notes"], ctx)
    story += build_followup_section(d["follow_up"], ctx)
    story += build_diet_section(d["diet_plan"], ctx)
    story += build_disclaimer_section(ctx)
    return story


def _render(d: dict, labels: dict, row_split: bool) -> tuple[bytes, int]:
    ctx = RenderContext(labels=labels, styles=make_styles(), row_split=row_split)
    name = d["patient"]["name"]
    if name:
        from .fonts import markup
        line = f'<b>{markup(labels["continued"], bold=True)}</b> {markup(_truncate(name, 70), bold=True)}'
        if d["patient"]["date"]:
            line += f' &nbsp;·&nbsp; {markup(d["patient"]["date"])}'
        ctx.patient_line = line
    buf = io.BytesIO()
    title = f"Rxplain Medical Summary" + (f" - {name}" if name else "")
    doc = make_doc(buf, ctx, title)
    doc.build(_build_story(d, ctx), canvasmaker=make_canvas_class(ctx))
    return buf.getvalue(), ctx.page_count


def create_rxplain_pdf(data: dict, output: str | Path | None = None, *, labels: dict | None = None,
                       now: datetime | None = None) -> PdfResult:
    """Generate the Rxplain medical-summary PDF.

    data    Rxplain result + patient info (see README for the schema).
    output  None -> in-memory only (use result.pdf_bytes)
            directory -> saved there as Rxplain-<Name>-Medical-Summary.pdf
            file path -> saved exactly there
    labels  optional dict overriding any static label (e.g. translated headings).
    """
    register_fonts()
    d = normalise_input(data, now)
    merged = {**T.DEFAULT_LABELS, **(labels or {})}
    try:
        pdf, pages = _render(d, merged, row_split=False)
    except LayoutError:
        # A single table row is taller than a page: allow splitting *inside* rows.
        pdf, pages = _render(d, merged, row_split=True)

    filename = safe_filename(d["patient"]["name"])
    path = None
    if output is not None:
        out = Path(output)
        path = out / filename if (out.is_dir() or out.suffix.lower() != ".pdf") else out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf)
    return PdfResult(filename=filename, pdf_bytes=pdf, page_count=pages, path=path)
