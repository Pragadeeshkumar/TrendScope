"""
LLM-Grounded Structured Information Extractor for Stage 3.
Extracts Methods, Datasets, Limitations, Future Work, and Key Findings with verbatim provenance.
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

from .models import (
    PaperExtractionResult,
    ExtractedMethod,
    ExtractedDataset,
    ExtractedLiteratureSource,
    ExtractedLimitation,
    ExtractedFutureWork,
    ExtractedFinding,
    ProvenancePointer
)
from .parser import ParsedPDFDocument, IndexedSentence
from .detector import extract_smart_candidate_context, build_compact_prompt_context
from .normalizer import normalize_method_name, normalize_dataset_name

load_dotenv()

logger = logging.getLogger("trendscope.extraction.extractor")

EXTRACTION_SYSTEM_PROMPT = """Extract grounded scientific entities from paper snippets with sentence IDs [S...].

JSON Schema:
{
  "methods": [{"name": "str", "type": "model|algorithm|loss_function|architecture|framework", "role": "proposed|baseline", "sentence_id": "S...", "page": 1, "section": "str", "quote": "verbatim text"}],
  "datasets": [{"name": "str", "modality": "str", "usage": "evaluation|training|benchmark", "sentence_id": "S...", "page": 1, "section": "str", "quote": "verbatim text"}],
  "literature_sources": [{"name": "str", "sentence_id": "S...", "page": 1, "section": "str", "quote": "verbatim text"}],
  "findings": [{"claim": "str", "metric": "str", "value": "str", "direction": "improvement|degradation|neutral", "sentence_id": "S...", "page": 1, "section": "str", "quote": "verbatim text"}],
  "limitations": [{"text": "str", "category": "computational_cost|data_scarcity|generalization|scalability|general", "sentence_id": "S...", "page": 1, "section": "str", "quote": "verbatim text"}],
  "future_work": [{"text": "str", "category": "methodological_extension|dataset_expansion|efficiency", "sentence_id": "S...", "page": 1, "section": "str", "quote": "verbatim text"}]
}

Rules:
1. Route search engines/databases (PubMed, Scopus, Google Scholar, Web of Science, IEEE Xplore) ONLY to "literature_sources".
2. Do NOT extract pronouns, determiners, or discourse markers (e.g., However, Such, Its, Both, Each, Instead).
3. Do NOT extract author names or standalone years/numbers as methods/datasets.
4. Keep exact sentence_id, page, section, and short quote (<=15 words). Output ONLY valid JSON."""


from .llm_rotator import GroqKeyRotator
from .ollama_client import OllamaLocalClient

class LLMStructuredExtractor:
    """Extracts structured research entities and provenance links from parsed scientific papers."""
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        model_name: str = "qwen/qwen3.8-27b",
        groq_keys: Optional[List[str]] = None,
        ollama_model: str = "qwen2.5:7b"
    ):
        self.ollama_client = OllamaLocalClient(model_name=ollama_model)
        self.groq_rotator = GroqKeyRotator(model_name=model_name, api_keys=groq_keys)
        self.gemini_api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_model_name = "gemini-2.5-flash"
        self.gemini_client = None
        self._init_gemini_client()

    def _init_gemini_client(self):
        if not self.gemini_api_key:
            return

        try:
            from google import genai
            self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            self.use_new_genai = True
            logger.info("Initialized Google GenAI Client as backup extractor.")
        except Exception:
            try:
                import google.generativeai as gai
                gai.configure(api_key=self.gemini_api_key)
                self.gemini_client = gai.GenerativeModel(self.gemini_model_name)
                self.use_new_genai = False
                logger.info("Initialized google.generativeai Client as backup extractor.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini backup client: {e}")
                self.gemini_client = None
                self.use_new_genai = False

    def extract_from_parsed_doc(
        self, 
        doc: ParsedPDFDocument, 
        paper_metadata: Optional[Dict[str, Any]] = None
    ) -> PaperExtractionResult:
        """
        Extracts structured information from a parsed PDF document.
        """
        paper_metadata = paper_metadata or {}
        title = paper_metadata.get("title", "Unknown Title")
        year = paper_metadata.get("publication_year")

        result = PaperExtractionResult(
            paper_id=doc.paper_id,
            title=title,
            publication_year=year,
            pdf_path=doc.filepath
        )

        if not doc.is_valid:
            result.status = "NO_PDF" if not os.path.exists(doc.filepath) else "ERROR"
            result.error_message = doc.error or "Invalid PDF text."
            logger.warning(f"[{doc.paper_id}] Extraction skipped: {result.error_message}")
            return result

        # 1. Prune down to high-signal candidate context (compact ~20-30 sentences)
        pruned_sents = extract_smart_candidate_context(doc, max_sentences_per_category=8)
        compact_context = build_compact_prompt_context(doc, pruned_sents)

        if not compact_context.strip():
            result.status = "PARTIAL"
            result.error_message = "No relevant sentences detected in document."
            return result

        # 2. Build index map for sentence verification
        sentence_lookup: Dict[str, IndexedSentence] = {s.sentence_id: s for s in doc.sentences}

        # 3. Call LLM (Groq Multi-Key Fallback first, then Local Ollama, then Gemini, then rule-based fallback)
        extracted_data = None
        user_prompt = f"Paper Title: {title}\n\n--- EXTRACTED PAPER SNIPPETS ---\n{compact_context}"

        # Primary: Groq Multi-Key Fallback Client (openai/gpt-oss-20b)
        if self.groq_rotator.clients:
            try:
                extracted_data = self.groq_rotator.generate_json(
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.1
                )
            except Exception as e:
                logger.warning(f"[{doc.paper_id}] Groq extraction failed: {e}")

        # Secondary Backup: Gemini
        if not extracted_data and self.gemini_client:
            try:
                extracted_data = self._call_gemini_llm(title, compact_context)
            except Exception as e:
                pass

        # Final Fallback: Rule-based
        if not extracted_data:
            extracted_data = self._rule_based_fallback_extraction(doc, pruned_sents)

        # 4. Map and validate extracted entities with Provenance Pointer
        self._populate_extraction_result(result, extracted_data, sentence_lookup, doc)
        
        result.status = "SUCCESS"
        logger.info(
            f"[{doc.paper_id}] Extracted {len(result.methods)} methods, "
            f"{len(result.datasets)} datasets, {len(result.limitations)} limitations, "
            f"{len(result.future_work)} future work items."
        )
        return result

    def _call_gemini_llm(self, title: str, compact_context: str) -> Optional[Dict[str, Any]]:
        """Backup call to Gemini if Groq is unavailable."""
        user_prompt = f"Paper Title: {title}\n\n--- EXTRACTED PAPER SNIPPETS ---\n{compact_context}"

        if getattr(self, "use_new_genai", False):
            response = self.gemini_client.models.generate_content(
                model=self.gemini_model_name,
                contents=[EXTRACTION_SYSTEM_PROMPT, user_prompt],
                config={"response_mime_type": "application/json", "temperature": 0.1}
            )
            raw_text = response.text
        else:
            full_prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\n{user_prompt}"
            response = self.gemini_client.generate_content(
                full_prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.1}
            )
            raw_text = response.text

        clean_json = raw_text.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()

        try:
            return json.loads(clean_json)
        except Exception:
            match = re.search(r'(\{[\s\S]*\})', clean_json)
            if match:
                return json.loads(match.group(1))
            return None

    def _rule_based_fallback_extraction(
        self, 
        doc: ParsedPDFDocument, 
        pruned_sents: Dict[str, List[IndexedSentence]]
    ) -> Dict[str, Any]:
        """
        Deterministic rule-based extractor used for offline testing or when LLM API is unavailable.
        """
        output: Dict[str, List[Dict[str, Any]]] = {
            "methods": [],
            "datasets": [],
            "limitations": [],
            "future_work": [],
            "findings": []
        }

        # Extract Methods using regex pattern matching on method sentences
        method_candidates = set()
        for s in pruned_sents.get("methods", []):
            # Extract capitalized terms or common AI architecture keywords from sentence
            found = re.findall(r'\b(?:[A-Z][a-zA-Z0-9_\-]+(?:\s+[A-Z][a-zA-Z0-9_\-]+)*)\b', s.text)
            for cand in found:
                cand_clean = cand.strip()
                if len(cand_clean) >= 3 and cand_clean.lower() not in {"the", "this", "our", "and", "for", "with", "fig", "table", "section", "arxiv"}:
                    if cand_clean.lower() not in method_candidates:
                        method_candidates.add(cand_clean.lower())
                        output["methods"].append({
                            "name": cand_clean,
                            "type": "model",
                            "role": "proposed",
                            "sentence_id": s.sentence_id,
                            "page": s.page,
                            "section": s.section,
                            "quote": s.text[:200]
                        })
                if len(output["methods"]) >= 4:
                    break
            if len(output["methods"]) >= 4:
                break

        # Extract Datasets using regex pattern matching on dataset sentences
        dataset_candidates = set()
        for s in pruned_sents.get("datasets", []):
            found = re.findall(r'\b(?:[A-Z0-9][a-zA-Z0-9_\-]+(?:\s+[A-Z0-9][a-zA-Z0-9_\-]+)*)\b', s.text)
            for cand in found:
                cand_clean = cand.strip()
                if len(cand_clean) >= 3 and cand_clean.lower() not in {"the", "this", "our", "and", "for", "with", "data", "dataset", "table", "benchmark"}:
                    if cand_clean.lower() not in dataset_candidates:
                        dataset_candidates.add(cand_clean.lower())
                        output["datasets"].append({
                            "name": cand_clean,
                            "modality": "Clinical Data",
                            "usage": "evaluation",
                            "samples": "N/A",
                            "sentence_id": s.sentence_id,
                            "page": s.page,
                            "section": s.section,
                            "quote": s.text[:200]
                        })
                if len(output["datasets"]) >= 4:
                    break
            if len(output["datasets"]) >= 4:
                break

        # Extract Limitations
        for s in pruned_sents.get("limitations", [])[:2]:
            output["limitations"].append({
                "text": s.text[:150],
                "category": "general",
                "sentence_id": s.sentence_id,
                "page": s.page,
                "section": s.section,
                "quote": s.text[:200]
            })

        # Extract Future Work
        for s in pruned_sents.get("future_work", [])[:2]:
            output["future_work"].append({
                "text": s.text[:150],
                "category": "methodological_extension",
                "sentence_id": s.sentence_id,
                "page": s.page,
                "section": s.section,
                "quote": s.text[:200]
            })

        return output

    def _populate_extraction_result(
        self,
        result: PaperExtractionResult,
        data: Dict[str, Any],
        sentence_lookup: Dict[str, IndexedSentence],
        doc: ParsedPDFDocument
    ) -> None:
        """Parses raw dictionary payload into validated Pydantic models with provenance verification."""
        
        def resolve_provenance(item: Dict[str, Any]) -> ProvenancePointer:
            sent_id = str(item.get("sentence_id") or "S1")
            raw_page = item.get("page", 1)
            try:
                page = int(raw_page) if raw_page not in ("", None) else 1
            except Exception:
                page = 1
            section = str(item.get("section") or "General")
            quote = str(item.get("quote") or "")

            # If sentence ID exists in document, ground it to actual sentence
            if sent_id in sentence_lookup:
                matched_sent = sentence_lookup[sent_id]
                page = matched_sent.page
                section = matched_sent.section
                if not quote:
                    quote = matched_sent.text

            return ProvenancePointer(
                sentence_id=sent_id,
                page=page,
                section=section,
                quote=quote
            )

        LITERATURE_DB_NAMES = {
            "pubmed", "scopus", "embase", "web of science", "ieee xplore", "google scholar",
            "proquest", "proquest consumer health database", "medline", "cochrane"
        }
        NOISE_TERMS = {
            "however", "moreover", "furthermore", "overall", "over", "given", "through",
            "here", "these", "prior", "specifically", "clinicians", "automated", "principles",
            "reviewer", "historical", "base model selection", "elliot bolton", "figure", "table",
            "section", "unknown method", "unknown dataset", "benchmark dataset"
        }

        # 1. Methods
        for m in data.get("methods", []):
            raw_name = m.get("name", "").strip()
            if not raw_name or len(raw_name) < 2:
                continue
            clean_lower = raw_name.lower()
            if clean_lower in NOISE_TERMS or clean_lower in LITERATURE_DB_NAMES:
                continue
            # Skip author name patterns
            if re.search(r'\bet\s+al\.?\b', clean_lower) or clean_lower == "elliot bolton":
                continue

            prov = resolve_provenance(m)
            result.methods.append(ExtractedMethod(
                name=raw_name,
                normalized_name=normalize_method_name(raw_name),
                type=m.get("type", "model"),
                role=m.get("role", "proposed"),
                provenance=prov
            ))

        # 2. Datasets
        for d in data.get("datasets", []):
            raw_name = d.get("name", "").strip()
            if not raw_name or len(raw_name) < 2:
                continue
            clean_lower = raw_name.lower()
            if clean_lower in NOISE_TERMS:
                continue
            prov = resolve_provenance(d)
            
            # Route literature search databases to literature_sources
            if any(ldb in clean_lower for ldb in LITERATURE_DB_NAMES):
                result.literature_sources.append(ExtractedLiteratureSource(
                    name=raw_name,
                    normalized_name=raw_name.title(),
                    provenance=prov
                ))
                continue

            result.datasets.append(ExtractedDataset(
                name=raw_name,
                normalized_name=normalize_dataset_name(raw_name),
                modality=d.get("modality"),
                usage=d.get("usage", "evaluation"),
                samples=d.get("samples"),
                provenance=prov
            ))

        # 3. Explicit Literature Sources from LLM
        for ls in data.get("literature_sources", []):
            raw_name = ls.get("name", "").strip()
            if not raw_name or len(raw_name) < 2:
                continue
            prov = resolve_provenance(ls)
            result.literature_sources.append(ExtractedLiteratureSource(
                name=raw_name,
                normalized_name=raw_name.title(),
                provenance=prov
            ))

        # 4. Limitations
        for lim in data.get("limitations", []):
            prov = resolve_provenance(lim)
            result.limitations.append(ExtractedLimitation(
                text=lim.get("text", "Unspecified limitation"),
                category=lim.get("category", "general"),
                provenance=prov
            ))

        # 5. Future Work
        for fw in data.get("future_work", []):
            prov = resolve_provenance(fw)
            result.future_work.append(ExtractedFutureWork(
                text=fw.get("text", "Unspecified future research"),
                category=fw.get("category", "methodological_extension"),
                provenance=prov
            ))

        # 6. Findings
        for f in data.get("findings", []):
            prov = resolve_provenance(f)
            finding_text = f.get("claim") or f.get("finding") or "Unspecified finding"
            metric = f.get("metric")
            val = f.get("value") or f.get("result")
            result.findings.append(ExtractedFinding(
                finding=finding_text,
                metric=metric,
                result=val,
                provenance=prov
            ))
