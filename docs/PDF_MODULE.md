# Rxplain PDF template

Real, selectable, searchable PDFs generated with ReportLab (Platypus). Not a screenshot.

## Location
The engine lives in `rxplain_pdf/` at the repo root (see the root README for the full layout).
Logos: `rxplain_pdf/assets/` (`rxplain_logo.png` and `T.png`, the Trimitha tile shown in the top-right corner; replace to rebrand).
Reference PDF: `rxplain_pdf/reference/` (not supplied; adjust `theme.py` to match it).

## Python API
```python
from rxplain_pdf import create_rxplain_pdf
res = create_rxplain_pdf(data)                 # in memory
res = create_rxplain_pdf(data, "out/")         # saves out/Rxplain-<Name>-Medical-Summary.pdf
res.filename, res.pdf_bytes, res.page_count, res.path, res.content_disposition()
```
CLI: `python -m rxplain_pdf examples/inputs/sample_input.json --out out/`

## HTTP API (what the frontend calls)
`POST /api/generate-pdf`, `Content-Type: application/json` -> `application/pdf` (attachment).
400 `{"error": ...}` for empty/invalid input, 500 on failure. See docs/INTEGRATION.md.

## Input JSON
Accepts the live Rxplain response **as-is** plus patient fields:

| key | notes |
|---|---|
| name, age, language, date | optional; only provided fields are shown; date defaults to today (ISO `YYYY-MM-DD` ok) |
| summary | string |
| terms | `[{term, definition}]` |
| critical_warnings **or** warnings | `[string]` |
| medicines + dosage_table | site shape: `medicines[{name,purpose,timing,side_effects}]`, `dosage_table[{medicine,morning,afternoon,night,duration}]`, merged by exact name |
| medicines (flat) | brief shape: `[{name,type,purpose,morning,afternoon,night,duration}]`; Type column appears only if any row has `type` |
| checklist, notes | `[string]` |
| follow_up | string |
| diet_plan | optional `{goal, eat[], avoid[], hydration, tips[]}` |

Empty sections are omitted. Text is escaped and typeset, never rewritten.
Static headings can be overridden with `create_rxplain_pdf(data, labels={...})` (see `DEFAULT_LABELS`).

## Languages
Scripts auto-detected per word (not from `language`): Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil,
Telugu, Kannada, Malayalam, Arabic (Urdu/Kashmiri/Sindhi), Ol Chiki, Meitei Mayek. Mixed English medicine names work.
Requires `uharfbuzz` (shaping is switched on via `shaping=1` in every style).

## Known limitations
* Right-to-left text is shaped, ordered and right-aligned, but tables/columns are not mirrored.
* Only Telugu, Hindi and Urdu were visually checked; other scripts were checked for glyph coverage
  and punctuation, not by a native reader. Have a speaker review each language before launch.
* Static headings/labels are English; the site's results page also uses English headings.
* Vercel deployment is untested here; check function size and cold start on your plan.
