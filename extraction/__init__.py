"""
Stage 3: Research Information Extraction Subsystem for TrendScope.
"""

from .models import (
    ProvenancePointer,
    ExtractedMethod,
    ExtractedDataset,
    ExtractedLimitation,
    ExtractedFutureWork,
    ExtractedFinding,
    PaperExtractionResult,
    ExtractionRunManifest
)
from .parser import parse_pdf, ParsedPDFDocument, IndexedSentence
from .detector import extract_smart_candidate_context, build_compact_prompt_context
from .normalizer import normalize_method_name, normalize_dataset_name
from .extractor import LLMStructuredExtractor
from .storage import init_extraction_db, save_paper_extraction_to_db, save_extraction_manifest_to_json
from .pipeline import ExtractionPipeline

__all__ = [
    "ProvenancePointer",
    "ExtractedMethod",
    "ExtractedDataset",
    "ExtractedLimitation",
    "ExtractedFutureWork",
    "ExtractedFinding",
    "PaperExtractionResult",
    "ExtractionRunManifest",
    "parse_pdf",
    "ParsedPDFDocument",
    "IndexedSentence",
    "extract_smart_candidate_context",
    "build_compact_prompt_context",
    "normalize_method_name",
    "normalize_dataset_name",
    "LLMStructuredExtractor",
    "init_extraction_db",
    "save_paper_extraction_to_db",
    "save_extraction_manifest_to_json",
    "ExtractionPipeline"
]
