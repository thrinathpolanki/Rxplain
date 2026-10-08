"""CLI:  python -m rxplain_pdf sample/sample_input.json --out out/"""
import argparse, json, sys
from pathlib import Path
from .generator import create_rxplain_pdf


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate an Rxplain medical-summary PDF from JSON.")
    ap.add_argument("input", help="path to JSON file ('-' for stdin)")
    ap.add_argument("--out", default=".", help="output directory or .pdf file path")
    a = ap.parse_args(argv)
    raw = sys.stdin.read() if a.input == "-" else Path(a.input).read_text(encoding="utf-8")
    res = create_rxplain_pdf(json.loads(raw), a.out)
    print(f"{res.path}  ({res.page_count} page(s))")


if __name__ == "__main__":
    main()
