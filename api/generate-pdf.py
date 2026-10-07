"""POST /api/generate-pdf  ->  application/pdf        (Vercel Python serverless function)

Success : 200, Content-Type: application/pdf, Content-Disposition: attachment; filename=...
Failure : 4xx/5xx, Content-Type: application/json, {"error": "<safe message>", "code": "<machine code>"}
Never returns HTML and never includes stack traces, paths or secrets in a response.
"""
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rxplain_pdf import create_rxplain_pdf                      # noqa: E402
from rxplain_pdf.request import MAX_BODY_BYTES, RequestError, parse_pdf_request  # noqa: E402

log = logging.getLogger("rxplain.pdf")
logging.basicConfig(level=logging.INFO)

GENERIC_FAIL = "Could not generate the PDF."


class handler(BaseHTTPRequestHandler):
    server_version = "RxplainPDF"
    sys_version = ""

    # ---- helpers -------------------------------------------------------
    def _common_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")

    def _json(self, status, message, code):
        body = json.dumps({"error": message, "code": code}).encode("utf-8")
        self.send_response(status)
        self._common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):      # default would emit an HTML page
        self._json(code, "Request could not be processed.", "http_error")

    def log_message(self, fmt, *args):                            # never log request bodies
        log.info("%s %s", self.command, self.path.split("?")[0])

    # ---- methods -------------------------------------------------------
    def _not_allowed(self):
        self.send_response(405)
        self.send_header("Allow", "POST")
        self._common_headers()
        body = b'{"error":"Method not allowed.","code":"method_not_allowed"}'
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _not_allowed             # same-origin only: no CORS

    def do_GET(self):
        """Health check: open /api/generate-pdf in a browser to confirm the function is deployed."""
        try:
            from rxplain_pdf.fonts import FONTS_DIR, SHAPING_AVAILABLE
            fonts_ok = (FONTS_DIR / "NotoSans-Regular.ttf").exists()
            body = {"service": "rxplain-pdf", "status": "ok" if fonts_ok else "degraded",
                    "fonts": fonts_ok, "shaping": SHAPING_AVAILABLE}
        except Exception:                                                              # noqa: BLE001
            log.exception("health check failed")
            body = {"service": "rxplain-pdf", "status": "error"}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self._common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        try:
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._json(415, "Content-Type must be application/json.", "unsupported_media_type")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n <= 0:
                return self._json(400, "Request body is required.", "empty_body")
            if n > MAX_BODY_BYTES:
                return self._json(413, "Report is too large to export.", "too_large")
            raw = self.rfile.read(n)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json(400, "Request body is not valid JSON.", "bad_json")
            try:
                data = parse_pdf_request(payload)
                result = create_rxplain_pdf(data)
            except RequestError as exc:
                return self._json(400, exc.message, "invalid_request")
            except ValueError:                                     # e.g. result has no content
                return self._json(400, "The report has no content to export.", "empty_result")
        except Exception:                                          # noqa: BLE001  - technical detail stays in server logs
            log.exception("PDF generation failed")
            return self._json(500, GENERIC_FAIL, "generation_failed")

        pdf = result.pdf_bytes
        self.send_response(200)
        self._common_headers()
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", result.content_disposition())
        self.send_header("Content-Length", str(len(pdf)))
        self.end_headers()
        self.wfile.write(pdf)
