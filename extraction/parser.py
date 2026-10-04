"""
PDF Parser using PyMuPDF (fitz) for Stage 3 Research Information Extraction.
Extracts clean, structured text blocks and indexes sentences with page provenance.
"""

import os
import sys
import re
import logging
import sqlite3
from typing import List, Dict, Any, Optional

# Ensure virtual environment site-packages is discoverable
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_site = os.path.join(BASE_DIR, ".venv", "Lib", "site-packages")
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

logger = logging.getLogger("trendscope.extraction.parser")


class IndexedSentence:
    """Represents a single sentence extracted from a PDF with provenance information."""
    def __init__(self, sentence_id: str, paper_id: str, page: int, section: str, text: str):
        self.sentence_id = sentence_id
        self.paper_id = paper_id
        self.page = page
        self.section = section
        self.text = text.strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentence_id": self.sentence_id,
            "paper_id": self.paper_id,
            "page": self.page,
            "section": self.section,
            "text": self.text
        }


class ParsedPDFDocument:
    """Container for the structured parsed content of a paper."""
    def __init__(self, paper_id: str, filepath: str):
        self.paper_id = paper_id
        self.filepath = filepath
        self.total_pages: int = 0
        self.sentences: List[IndexedSentence] = []
        self.sections: Dict[str, List[IndexedSentence]] = {}
        self.is_valid: bool = False
        self.error: Optional[str] = None


def clean_line_noise(text: str) -> str:
    """
    Cleans OCR artifacts, hyphenated line wraps, repetitive headers, and standalone citation blocks.
    """
    if not text:
        return ""
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'^\d+\s*$', '', text)
    return text.strip()


def split_into_sentences(text: str) -> List[str]:
    """
    Splits text into discrete sentences while preserving abbreviations like 'e.g.', 'i.e.', 'et al.', 'Fig.', etc.
    """
    if not text:
        return []
    
    protected = text
    abbrevs = {
        r'\be\.g\.\s*': 'e_g_placeholder ',
        r'\bi\.e\.\s*': 'i_e_placeholder ',
        r'\bet al\.\s*': 'et_al_placeholder ',
        r'\bFig\.\s*': 'Fig_placeholder ',
        r'\bEq\.\s*': 'Eq_placeholder ',
        r'\bTab\.\s*': 'Tab_placeholder ',
        r'\bvs\.\s*': 'vs_placeholder ',
        r'\bDr\.\s*': 'Dr_placeholder ',
        r'\bProf\.\s*': 'Prof_placeholder '
    }
    for pattern, placeholder in abbrevs.items():
        protected = re.sub(pattern, placeholder, protected, flags=re.IGNORECASE)

    raw_sentences = re.split(r'(?<=[.!?])\s+', protected)
    clean_sents = []
    for s in raw_sentences:
        s = s.strip()
        s = s.replace('e_g_placeholder', 'e.g.')
        s = s.replace('i_e_placeholder', 'i.e.')
        s = s.replace('et_al_placeholder', 'et al.')
        s = s.replace('Fig_placeholder', 'Fig.')
        s = s.replace('Eq_placeholder', 'Eq.')
        s = s.replace('Tab_placeholder', 'Tab.')
        s = s.replace('vs_placeholder', 'vs.')
        s = s.replace('Dr_placeholder', 'Dr.')
        s = s.replace('Prof_placeholder', 'Prof.')
        if len(s) >= 15:
            clean_sents.append(s)
            
    return clean_sents


def parse_pdf(filepath: str, paper_id: str) -> ParsedPDFDocument:
    """
    Extracts structured pages, sections, and indexed sentences from a local PDF file.
    Uses PyMuPDF as primary parser and pdfplumber as fallback.
    """
    doc = ParsedPDFDocument(paper_id=paper_id, filepath=filepath)
    
    if not os.path.exists(filepath):
        doc.error = f"File not found: {filepath}"
        logger.warning(f"[{paper_id}] {doc.error}")
        return doc

    # 1. Primary parser: PyMuPDF (fitz)
    if fitz is not None:
        try:
            pdf = fitz.open(filepath)
            doc.total_pages = len(pdf)
            sentence_idx = 1
            current_section = "Abstract"
            
            for page_num in range(len(pdf)):
                page = pdf[page_num]
                page_index = page_num + 1
                blocks = page.get_text("blocks")
                for block in blocks:
                    if len(block) >= 5 and block[4]:
                        raw_text = block[4]
                        clean_text = clean_line_noise(raw_text)
                        if not clean_text:
                            continue
                            
                        header_match = re.match(r'^(?:\d+|[IVXLCDM]+)?\.?\s*([A-Z][A-Za-z\s]{2,40})$', clean_text)
                        if header_match and len(clean_text.split()) <= 6:
                            candidate_sec = header_match.group(1).strip()
                            current_section = candidate_sec
                            continue

                        sents = split_into_sentences(clean_text)
                        for s in sents:
                            sent_obj = IndexedSentence(
                                sentence_id=f"S{sentence_idx}",
                                paper_id=paper_id,
                                page=page_index,
                                section=current_section,
                                text=s
                            )
                            doc.sentences.append(sent_obj)
                            doc.sections.setdefault(current_section, []).append(sent_obj)
                            sentence_idx += 1
                            
            pdf.close()
            doc.is_valid = len(doc.sentences) > 0
            if doc.is_valid:
                logger.info(f"[{paper_id}] Successfully parsed {len(doc.sentences)} sentences across {doc.total_pages} pages (PyMuPDF).")
                return doc
        except Exception as e:
            logger.warning(f"[{paper_id}] PyMuPDF parse attempt failed: {e}. Trying pdfplumber fallback...")

    # 2. Fallback parser: pdfplumber
    if pdfplumber is not None:
        try:
            with pdfplumber.open(filepath) as pdf:
                doc.total_pages = len(pdf.pages)
                sentence_idx = 1
                current_section = "Abstract"
                for page_num, page in enumerate(pdf.pages):
                    page_index = page_num + 1
                    raw_text = page.extract_text() or ""
                    clean_text = clean_line_noise(raw_text)
                    if not clean_text:
                        continue
                    sents = split_into_sentences(clean_text)
                    for s in sents:
                        sent_obj = IndexedSentence(
                            sentence_id=f"S{sentence_idx}",
                            paper_id=paper_id,
                            page=page_index,
                            section=current_section,
                            text=s
                        )
                        doc.sentences.append(sent_obj)
                        doc.sections.setdefault(current_section, []).append(sent_obj)
                        sentence_idx += 1
            doc.is_valid = len(doc.sentences) > 0
            if doc.is_valid:
                logger.info(f"[{paper_id}] Successfully parsed {len(doc.sentences)} sentences across {doc.total_pages} pages (pdfplumber).")
                return doc
        except Exception as e:
            logger.error(f"[{paper_id}] pdfplumber fallback failed: {e}")

    if not doc.is_valid:
        doc.error = "No readable text extracted (scanned image or empty PDF)."
    return doc
