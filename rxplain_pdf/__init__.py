"""Rxplain PDF template package."""
from .generator import PdfResult, create_rxplain_pdf, normalise_input, safe_filename
from .template import draw_footer, draw_header
from .sections import (build_checklist_section, build_diet_section, build_disclaimer_section,
                       build_followup_section, build_medicine_table, build_notes_section,
                       build_patient_section, build_summary_section, build_terms_section,
                       build_warnings_section)

__all__ = ["create_rxplain_pdf", "safe_filename", "normalise_input", "PdfResult", "draw_header", "draw_footer",
           "build_patient_section", "build_summary_section", "build_terms_section", "build_warnings_section",
           "build_medicine_table", "build_checklist_section", "build_notes_section", "build_followup_section",
           "build_diet_section", "build_disclaimer_section"]
