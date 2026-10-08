"""Server-side validation of the POST /api/generate-pdf request.

Request contract
----------------
{
  "patient":  {"name": "Ravi Kumar", "age": 45},          # required
  "language": "English",                                   # optional, display only
  "date":     "2026-10-06",                                # optional YYYY-MM-DD (client-local date)
  "result":   { ...the Rxplain result object... }          # required
}
`result` is the object Rxplain already produced (summary, terms, critical_warnings|warnings,
medicines, dosage_table, checklist, notes, follow_up, diet_plan). It is typeset, never altered.

Validation rejects (HTTP 400) instead of silently truncating: medical text is never cut.
"""
from __future__ import annotations

import re
from datetime import datetime

MAX_BODY_BYTES = 1_000_000
MAX_NAME_LEN = 100
MAX_LANG_LEN = 40
MAX_TEXT_LEN = 20_000        # any single string
MAX_ITEMS = 200              # any list
MAX_TOTAL_CHARS = 250_000    # whole result

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_AGE_RE = re.compile(r"^(0|[1-9]\d{0,2})$")

LIST_KEYS = ("terms", "critical_warnings", "warnings", "medicines", "dosage_table", "checklist", "notes")
STR_KEYS = ("summary", "follow_up")          # a list of strings is also accepted and joined
ALLOWED_KEYS = set(LIST_KEYS) | set(STR_KEYS) | {"diet_plan"}


class RequestError(ValueError):
    """Client error: `.message` is safe to show to the caller."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message, self.field = message, field


def _validate_name(v) -> str:
    if not isinstance(v, str):
        raise RequestError("Patient name is required.", "patient.name")
    name = re.sub(r"\s+", " ", v).strip()
    if not name:
        raise RequestError("Patient name is required.", "patient.name")
    if len(name) > MAX_NAME_LEN:
        raise RequestError(f"Patient name must be at most {MAX_NAME_LEN} characters.", "patient.name")
    if _CTRL.search(name) or not any(ch.isalpha() for ch in name):
        raise RequestError("Patient name is not valid.", "patient.name")
    return name


def _validate_age(v) -> str:
    if isinstance(v, bool):
        raise RequestError("Age must be a whole number from 0 to 120.", "patient.age")
    if isinstance(v, int):
        s = str(v)
    elif isinstance(v, float) and v.is_integer():
        s = str(int(v))
    elif isinstance(v, str):
        s = v.strip()
    else:
        raise RequestError("Age is required.", "patient.age")
    if not _AGE_RE.match(s) or int(s) > 120:
        raise RequestError("Age must be a whole number from 0 to 120.", "patient.age")
    return s


def _check_size(node, budget: list, depth: int = 0) -> None:
    """Walk the result: enforce types, per-string/list caps and a total character budget."""
    if depth > 4:
        raise RequestError("Report data is nested too deeply.")
    if isinstance(node, str):
        if len(node) > MAX_TEXT_LEN:
            raise RequestError("A report field is too long to export.")
        budget[0] += len(node)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        budget[0] += len(str(node))
    elif node is None or isinstance(node, bool):
        pass
    elif isinstance(node, list):
        if len(node) > MAX_ITEMS:
            raise RequestError("Report has too many items to export.")
        for x in node:
            _check_size(x, budget, depth + 1)
    elif isinstance(node, dict):
        if len(node) > 50:
            raise RequestError("Report data is malformed.")
        for k, x in node.items():
            if not isinstance(k, str):
                raise RequestError("Report data is malformed.")
            _check_size(x, budget, depth + 1)
    else:
        raise RequestError("Report data is malformed.")
    if budget[0] > MAX_TOTAL_CHARS:
        raise RequestError("Report is too large to export.")


def parse_pdf_request(payload) -> dict:
    """Validate the JSON body and return the flat dict that create_rxplain_pdf() accepts."""
    if not isinstance(payload, dict):
        raise RequestError("Request body must be a JSON object.")
    patient = payload.get("patient")
    if not isinstance(patient, dict):
        raise RequestError("Patient details are required.", "patient")
    name = _validate_name(patient.get("name"))
    age = _validate_age(patient.get("age"))

    language = payload.get("language")
    if language is not None and language != "":
        if not isinstance(language, str) or len(language) > MAX_LANG_LEN or _CTRL.search(language):
            raise RequestError("Language is not valid.", "language")
        language = language.strip()
    else:
        language = ""

    date = payload.get("date")
    if isinstance(date, str):
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            date = ""
    else:
        date = ""

    result = payload.get("result")
    if not isinstance(result, dict):
        raise RequestError("Report result is required.", "result")
    unknown = set(result) - ALLOWED_KEYS
    clean = {k: v for k, v in result.items() if k in ALLOWED_KEYS}      # silently ignore extra keys (e.g. history metadata)
    for k in LIST_KEYS:                                                 # AI output sometimes contains null entries: carry no data
        if isinstance(clean.get(k), list):
            clean[k] = [x for x in clean[k] if x is not None]
    for k in LIST_KEYS:
        if clean.get(k) is not None and not isinstance(clean[k], list):
            raise RequestError("Report data is malformed.", f"result.{k}")
    for k in STR_KEYS:
        v = clean.get(k)
        if v is not None and not isinstance(v, str) and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise RequestError("Report data is malformed.", f"result.{k}")
    if clean.get("diet_plan") is not None and not isinstance(clean["diet_plan"], dict):
        raise RequestError("Report data is malformed.", "result.diet_plan")
    _check_size(clean, [0])
    for k in ("terms", "medicines", "dosage_table"):          # items: objects, or plain strings / numbers (kept as text)
        for item in clean.get(k) or []:
            if not isinstance(item, (dict, str, int, float)) or isinstance(item, bool):
                raise RequestError("Report data is malformed.", f"result.{k}")

    return {**clean, "name": name, "age": age, "language": language, "date": date}
