"""
End-to-End Pipeline for Stage 3 Research Information Extraction.
Orchestrates PDF parsing, smart context pruning, LLM extraction, normalization, and DB persistence.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import PaperExtractionResult, ExtractionRunManifest
from .parser import parse_pdf, ParsedPDFDocument, IndexedSentence, split_into_sentences
from .extractor import LLMStructuredExtractor
from .storage import init_extraction_db, save_paper_extraction_to_db, save_extraction_manifest_to_json

logger = logging.getLogger("trendscope.extraction.pipeline")


class ExtractionPipeline:
    """Executes Stage 3 research information extraction across a corpus of scientific papers."""

    def __init__(
        self,
        db_path: str = "data/trendscope.db",
        model_name: str = "openai/gpt-oss-20b",
        max_workers: int = 2
    ):
        self.db_path = db_path
        self.model_name = model_name
        self.max_workers = max_workers
        self.extractor = LLMStructuredExtractor(model_name=model_name)
        init_extraction_db(self.db_path)

    def run_for_manifest(self, manifest_path: str, resolved_only: bool = True) -> ExtractionRunManifest:
        """
        Executes extraction for papers defined in a Stage 1/2 run manifest JSON.
        """
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        run_id = manifest_data.get("run_id") or manifest_data.get("retrieval_run_id", "unknown_run")
        papers = manifest_data.get("papers", [])
        
        # If papers are not stored directly in manifest JSON, load from SQLite papers table
        if not papers:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if resolved_only:
                cursor.execute("""
                    SELECT paper_id, title, publication_year, pdf_path, fulltext_resolved
                    FROM papers 
                    WHERE run_id = ? AND (fulltext_resolved = 1 OR pdf_path IS NOT NULL);
                """, (run_id,))
            else:
                cursor.execute("""
                    SELECT paper_id, title, publication_year, pdf_path, fulltext_resolved
                    FROM papers WHERE run_id = ?;
                """, (run_id,))
            rows = cursor.fetchall()
            conn.close()

            for r in rows:
                papers.append({
                    "paper_id": r[0],
                    "title": r[1],
                    "publication_year": r[2],
                    "pdf_path": r[3],
                    "fulltext_resolved": bool(r[4])
                })

        if resolved_only:
            papers = [p for p in papers if p.get("fulltext_resolved") or (p.get("pdf_path") and os.path.exists(p.get("pdf_path")))]

        return self.run_for_papers(run_id=run_id, papers=papers)

    def run_for_run_id(self, run_id: str, resolved_only: bool = True) -> ExtractionRunManifest:
        """
        Loads papers for a specific run_id from SQLite or manifest file and runs extraction.
        """
        manifest_path = f"data/manifest_{run_id}.json"
        if os.path.exists(manifest_path):
            return self.run_for_manifest(manifest_path, resolved_only=resolved_only)

        # Query SQLite papers table directly
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if resolved_only:
            cursor.execute("""
                SELECT paper_id, title, publication_year, pdf_path, fulltext_resolved
                FROM papers 
                WHERE run_id = ? AND (fulltext_resolved = 1 OR pdf_path IS NOT NULL);
            """, (run_id,))
        else:
            cursor.execute("""
                SELECT paper_id, title, publication_year, pdf_path, fulltext_resolved
                FROM papers WHERE run_id = ?;
            """, (run_id,))
        rows = cursor.fetchall()
        conn.close()

        papers = []
        for r in rows:
            papers.append({
                "paper_id": r[0],
                "title": r[1],
                "publication_year": r[2],
                "pdf_path": r[3],
                "fulltext_resolved": bool(r[4])
            })

        if resolved_only:
            papers = [p for p in papers if p.get("fulltext_resolved") or (p.get("pdf_path") and os.path.exists(p.get("pdf_path")))]

        return self.run_for_papers(run_id=run_id, papers=papers)

    def _process_single_paper(self, paper: Dict[str, Any], run_id: str) -> PaperExtractionResult:
        """Processes a single paper: parsing PDF, extracting structured entities, and saving to DB."""
        paper_id = paper.get("paper_id", "unknown")
        title = paper.get("title", "Unknown Title")
        year = paper.get("publication_year")
        pdf_path = paper.get("pdf_path") or f"data/pdfs/{paper_id}.pdf"

        logger.info(f"[{paper_id}] Starting Stage 3 Extraction for '{title[:50]}...'")

        # 1. Parse PDF text & sentences
        parsed_doc = parse_pdf(pdf_path, paper_id=paper_id)

        # Abstract fallback if PDF was not resolved or is unreadable
        if not parsed_doc.is_valid:
            abstract_text = ""
            try:
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute("SELECT abstract FROM papers WHERE paper_id = ?", (paper_id,))
                row = c.fetchone()
                if row and row[0]:
                    abstract_text = row[0]
                conn.close()
            except Exception:
                pass
            
            if abstract_text:
                sents = split_into_sentences(abstract_text)
                if sents:
                    parsed_doc = ParsedPDFDocument(paper_id=paper_id, filepath=pdf_path)
                    parsed_doc.total_pages = 1
                    for s_i, s_text in enumerate(sents):
                        sent_obj = IndexedSentence(
                            sentence_id=f"S{s_i+1}",
                            paper_id=paper_id,
                            page=1,
                            section="Abstract",
                            text=s_text
                        )
                        parsed_doc.sentences.append(sent_obj)
                        parsed_doc.sections.setdefault("Abstract", []).append(sent_obj)
                    parsed_doc.is_valid = True
                    logger.info(f"[{paper_id}] Using abstract text fallback ({len(sents)} sentences).")

        # 2. Extract structured entities with LLM / fallback
        res = self.extractor.extract_from_parsed_doc(
            doc=parsed_doc,
            paper_metadata={"title": title, "publication_year": year}
        )

        # 3. Save to database
        try:
            save_paper_extraction_to_db(res, run_id=run_id, db_path=self.db_path)
        except Exception as e:
            logger.error(f"[{paper_id}] Failed to save extraction to DB: {e}")

        return res

    def run_for_papers(self, run_id: str, papers: List[Dict[str, Any]]) -> ExtractionRunManifest:
        """
        Runs extraction across a list of paper dictionaries concurrently.
        """
        logger.info(f"=== Starting Stage 3 Extraction for run_id: {run_id} ({len(papers)} papers) ===")
        results: List[PaperExtractionResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_paper = {
                executor.submit(self._process_single_paper, p, run_id): p 
                for p in papers
            }
            for future in as_completed(future_to_paper):
                p = future_to_paper[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    logger.error(f"Error processing paper {p.get('paper_id')}: {e}")
                    results.append(PaperExtractionResult(
                        paper_id=p.get("paper_id", "unknown"),
                        title=p.get("title", "Unknown"),
                        status="ERROR",
                        error_message=str(e)
                    ))

        # Calculate summary metrics
        success_count = sum(1 for r in results if r.status == "SUCCESS")
        fail_count = len(results) - success_count
        total_methods = sum(len(r.methods) for r in results)
        total_datasets = sum(len(r.datasets) for r in results)
        total_limitations = sum(len(r.limitations) for r in results)
        total_future_work = sum(len(r.future_work) for r in results)

        manifest = ExtractionRunManifest(
            run_id=run_id,
            timestamp=datetime.utcnow().isoformat(),
            total_papers=len(papers),
            successful_extractions=success_count,
            failed_extractions=fail_count,
            total_methods_found=total_methods,
            total_datasets_found=total_datasets,
            total_limitations_found=total_limitations,
            total_future_work_found=total_future_work,
            papers=results
        )

        # Save manifest JSON
        save_extraction_manifest_to_json(manifest)
        logger.info(
            f"=== Completed Stage 3 Extraction for {run_id}: "
            f"{success_count}/{len(papers)} papers succeeded. "
            f"Found {total_methods} methods, {total_datasets} datasets, "
            f"{total_limitations} limitations, {total_future_work} future work items. ==="
        )
        return manifest
