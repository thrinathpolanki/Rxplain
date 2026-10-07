# Rxplain

**Making Medical Terms Simple.** Rxplain is an AI-powered web app that explains prescriptions and medical
documents in plain language, in English and Indian regional languages, with Firebase sign-in, report history,
text-to-speech and accessibility features. A report can be exported as a branded, multi-page **PDF**.

Powered by **Trimitha** · https://rxplain.vercel.app · https://trimitha.co.in

> Rxplain is an informational AI tool. It does not replace a doctor or give medical advice.

## Repository layout

```
Rxplain/
├── index.html                  The whole front-end (single page app: Tailwind, Lucide, Firebase, Gemini via Apps Script)
├── Rxplain Logo.png            Logos used by index.html (must stay at the repo root)
├── Trimitha Logo.png
├── api/
│   └── generate-pdf.py         Vercel Python function: POST /api/generate-pdf -> application/pdf
├── rxplain_pdf/                PDF engine (ReportLab). Imported by the API function
│   ├── generator.py            create_rxplain_pdf(), input normalisation, filename sanitiser
│   ├── request.py              server-side validation of the API request
│   ├── template.py             branded header/footer, page numbering
│   ├── sections.py             summary, terms, warnings, medicine table, action plan, notes, follow-up, diet
│   ├── styles.py  theme.py     typography + all brand colours/text (edit here to rebrand)
│   ├── fonts.py                Unicode fonts, per-word script switching, HarfBuzz shaping
│   ├── assets/                 logos used inside the PDF
│   ├── fonts/                  Noto fonts for 12 Indic/Arabic scripts + Latin (required at runtime)
│   └── reference/              drop the official reference PDF here (not read at runtime)
├── examples/
│   ├── inputs/                 sample request data (English, Hindi, Telugu, Urdu, flat schema)
│   └── pdfs/                   sample generated PDFs
├── tests/
│   ├── python/test_generate.py PDF engine + validation tests (9)
│   └── frontend/               jsdom tests for the download modal flow (32 checks)
├── tools/patch_fonts.py        one-off script that prepared the fonts (already applied)
├── docs/
│   ├── INTEGRATION.md          architecture, API contract, exact index.html edits, manual test checklist
│   ├── PDF_MODULE.md           PDF engine reference (input schema, languages, limitations)
│   ├── index.html.patch        diff of the PDF-export change against the previous index.html
│   └── ORIGINAL_README.md      the previous README, kept for reference
├── vercel.json                 bundles rxplain_pdf/** into the Python function
├── requirements.txt            reportlab, uharfbuzz, Pillow
└── .gitignore
```

## How PDF export works
Download button -> patient name + age modal -> `POST /api/generate-pdf` with the result object already on screen
-> Python/ReportLab builds the PDF -> browser downloads `Rxplain-<Name>-Medical-Summary.pdf`.
No screenshot, no second AI call. Details and the API contract: [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Run and test
```bash
pip install -r requirements.txt            # PDF engine
python -m rxplain_pdf examples/inputs/sample_input.json --out out/     # make a PDF from sample data

pip install pypdf pytest                    # test-only
python -m tests.python.test_generate        # backend tests

cd tests/frontend && npm install && (python server.py &) && npm test    # front-end flow tests

vercel dev                                  # full site + /api locally (a plain static server has no /api)
```

## Deploy
Push to Vercel with the repo root as the project root. `index.html` is served statically and `api/generate-pdf.py`
runs as a Python function. No environment variables or secrets are required for the PDF export.

## Troubleshooting
If Download shows "Could not generate the PDF", read the second line in the modal and see section 8 of [docs/INTEGRATION.md](docs/INTEGRATION.md). Quick check: open `/api/generate-pdf` in the browser; it should return a small JSON with `"status": "ok"`.

## Known limitations
See "Known limitations" in [docs/PDF_MODULE.md](docs/PDF_MODULE.md). Notably: the reference PDF was not supplied, so branding
follows the logos and site palette; right-to-left tables are not mirrored; only Hindi, Telugu, Urdu and English were
visually reviewed; Vercel deployment was not tested.

## License
See [LICENSE](LICENSE). Bundled Noto fonts are licensed under the SIL Open Font License.
