# Rxplain – PNG export replaced by real PDF export

## 1. Architecture
```
Browser (index.html)                              Vercel
 click Download ─► downloadReport()
   └► patient modal (name + age, validated)
       └► generatePdfReport()  ── POST /api/generate-pdf (JSON) ──►  api/generate-pdf.py
            body = {patient, language, date, result: currentReportData (whitelisted keys)}
                                                      │ rxplain_pdf.request.parse_pdf_request()  (validate)
                                                      │ rxplain_pdf.create_rxplain_pdf()         (ReportLab)
            ◄── 200 application/pdf  (or JSON error) ◄┘
   └► checks status + Content-Type + "%PDF-" magic ─► browser download
```
No html2canvas, no screenshot, no second Gemini call. The PDF is built from the same object given to `renderResults()`.

## 2. Files
New: `api/generate-pdf.py`, `vercel.json`, `requirements.txt`, `rxplain_pdf/` (generator, sections, fonts, assets, request validation, tests).
Modified: `index.html` only (see `docs/index.html.patch`, 8 small hunks).
Tests: `tests/python/` and `tests/frontend/` (jsdom flow tests). Samples: `examples/`.

## 3. index.html changes (exact)
| # | Where | Change |
|---|---|---|
| 1 | `<head>` lines 50-51 | **Delete** the `<!-- html2canvas for Screenshot -->` comment and its `<script src=".../html2canvas.min.js">` (it was used only by `downloadReport`). |
| 2 | Download button (results page) | Only `title="Save as Image"` -> `title="Download as PDF" aria-label="Download as PDF"`. `onclick="downloadReport()"` unchanged. |
| 3 | Directly **before** `<div id="results-section"` | **Insert** the `#patient-details-modal` markup. |
| 4 | After `let currentLanguage = 'English';` | **Insert** `let currentReportData = null;` |
| 5 | `selectLanguage()`, right before `renderResults(result);` | **Insert** `currentReportData = result;` |
| 6 | `loadHistoryItem()`, right before `renderResults(data);` | **Insert** `currentReportData = data;` |
| 7 | First line of `resetApp()` | **Insert** `currentReportData = null;` (Analyze Another) |
| 8 | Old `function downloadReport() { ... html2canvas ... }` | **Delete the whole function** and put the `// === PDF EXPORT START ... END ===` block in its place (before `callGeminiAPI`). |

Deleted old code: the `html2canvas(element, {...}).then(...)` call, the canvas `toDataURL('image/png')` link, `link.download = 'Rxplain-Medical-Summary.png'`, and the "Could not generate image" handler.
Nothing else is touched: Firebase, history, Gemini prompt, speech, onboarding and `renderResults` are unchanged.

## 4. API contract: POST /api/generate-pdf
```json
{ "patient": {"name": "Ravi Kumar", "age": 45},
  "language": "English",
  "date": "2026-10-06",
  "result": { "summary": "...", "terms": [{"term":"","definition":""}],
              "critical_warnings": ["..."],
              "medicines": [{"name":"","purpose":"","timing":"","side_effects":""}],
              "dosage_table": [{"medicine":"","morning":"1","afternoon":"0","night":"1","duration":""}],
              "checklist": [], "notes": [], "follow_up": "...", "diet_plan": {} } }
```
* **The live Rxplain result is sent as-is.** It differs from the example in the brief: warnings are plain strings (key `critical_warnings`), medicines are split into `medicines` + `dosage_table`, and there is no `type` or warning `category`. The server accepts BOTH shapes: `warnings: [{category,text}]` and `medicines[].type` / `medicines[].dosage{morning,afternoon,night}` are rendered when present; the Type column / category label appear only when the data has them. Nothing is invented.
* Validation (HTTP 400, never truncates): name 1-100 chars with a letter; age whole number 0-120; list/string types; <=200 items per list, <=20,000 chars per string, <=250,000 total; body <=1 MB. Unknown keys (history metadata) are dropped.
* Responses: `200 application/pdf` + `Content-Disposition` (ASCII + UTF-8 `filename*`), else JSON `{error, code}` with 400/405/413/415/500. Never HTML; no stack traces/paths; details only in Vercel function logs. Same-origin only (no CORS headers).

## 5. Deployment (Vercel)
Keep `index.html` at repo root. Add `api/`, `rxplain_pdf/`, `vercel.json`, `requirements.txt` (the other folders are optional for deployment). Vercel installs `reportlab`, `uharfbuzz`, `Pillow` and bundles `rxplain_pdf/**` (fonts ~4 MB) via `includeFiles`. No env vars or secrets are needed. Local test: `vercel dev` (a plain static server has no `/api`).

## 6. Dependencies
Python: reportlab >= 4.4 (HarfBuzz shaping), uharfbuzz, Pillow. Frontend: none new (html2canvas removed).

## 7. Testing
Automated (run here): `python -m tests.python.test_generate` (9 tests) and `cd tests/frontend && npm i && python server.py & npm test` (24 checks: modal, validation, account checkbox, duplicate clicks, abort, failure, non-PDF responses).
Manual checklist (do these in a real browser on the deployed site):
- [ ] New report -> Download -> PDF contains exactly the on-screen content
- [ ] Open from History -> Download -> PDF of that report (no new analysis)
- [ ] English, Hindi, Telugu, Tamil, Urdu results render correctly
- [ ] Long result -> multiple pages; header/footer/table header repeat
- [ ] Missing optional fields (no diet, no follow-up, no warnings)
- [ ] "Use the account details": fills + locks name; account without name -> asks for it
- [ ] Invalid ages (blank, abc, -1, 121, 4.5, 045) and empty name blocked
- [ ] Cancel / Esc / backdrop close; result stays on screen
- [ ] Double-click Generate -> one download
- [ ] Break the endpoint (offline/DevTools block) -> "Could not generate the PDF. Please try again."; result intact
- [ ] Phone (<=390 px) and desktop: modal fits, keyboard doesn't hide buttons, 16 px inputs don't zoom (iOS)
- [ ] Filename `Rxplain-<Name>-Medical-Summary.pdf`; header logos/brand; footer links
- [ ] No `html2canvas` request in Network tab; no PNG downloaded


## 8. Troubleshooting: "Could not generate the PDF. Please try again."
The modal now shows a second line saying what went wrong. Match it here:

| Second line shown | Cause | Fix |
|---|---|---|
| "The PDF service was not found on this page..." | `/api/generate-pdf` does not exist where the page is served (Live Server, `python -m http.server`, file://, or `api/` not deployed) | Open the **deployed** site, or run `vercel dev`. Make sure `api/`, `rxplain_pdf/`, `vercel.json`, `requirements.txt` are in the repo root that Vercel deploys. |
| "Please check your internet connection." | Browser could not reach the server | Check network / ad-blocker / that the page and `/api` share the same origin. |
| "The request took too long." | Cold start or > 45 s | Retry; check Vercel function logs. |
| `Reference: generation_failed` / `http_500` | The Python function crashed | Open Vercel -> Project -> Logs -> `api/generate-pdf`. The traceback is logged there (never sent to the browser). |
| A sentence such as "Report is too large to export." | Server validation rejected the data (safe message) | Follow the message. |

Quick deployment check: open `https://<your-site>/api/generate-pdf` in a browser. You should see
`{"service": "rxplain-pdf", "status": "ok", "fonts": true, "shaping": true}`.
`fonts: false` means `rxplain_pdf/fonts/` was not deployed; `shaping: false` means `uharfbuzz` failed to install
(English still works, Indian scripts will not shape correctly).
