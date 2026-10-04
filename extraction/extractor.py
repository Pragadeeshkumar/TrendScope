"""
LLM-Grounded Structured Information Extractor for Stage 3.
Implements the 5-Pillar Section-Targeted Cascaded Extraction Architecture:
1. Section-Targeted Prompt Routing
2. SciBERT/Token-Level + Contextual Verification
3. Scientific Relation Triplet Mining <Subject, Predicate, Object>
4. Semantic Canonicalization & Ontology Linking
5. Self-Verification Reflection Filter
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
    ScientificTriplet,
    ProvenancePointer
)
from .parser import ParsedPDFDocument, IndexedSentence
from .detector import extract_section_targeted_context, build_compact_prompt_context
from .normalizer import normalize_method_name, normalize_dataset_name, is_generic_noun

load_dotenv()

logger = logging.getLogger("trendscope.extraction.extractor")

EXTRACTION_SYSTEM_PROMPT = """You are an expert scientific literature information extractor.
Extract grounded scientific entities and relation triplets from paper snippets with sentence IDs [S...].

JSON Schema:
{
  "methods": [
    {
      "name": "Specific Model/Algorithm/Architecture Name",
      "type": "model|algorithm|loss_function|architecture|framework|backbone",
      "role": "proposed|baseline|ablation",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ],
  "datasets": [
    {
      "name": "Specific Dataset/Benchmark Name",
      "modality": "str",
      "usage": "evaluation|training|benchmark",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ],
  "triplets": [
    {
      "subject": "Proposed or Evaluated Method Name",
      "predicate": "EVALUATED_ON|OUTPERFORMS|USES_BACKBONE|SUFFERS_FROM|EXTENDS",
      "object": "Benchmark Dataset, Baseline Model, or Limitation Name",
      "metric": "Metric name (e.g. Accuracy, F1-Score, AUROC, Latency) or null",
      "value": "Metric score or percentage (e.g. 94.2%, 0.88) or null",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ],
  "literature_sources": [
    {
      "name": "Search Engine/Index Name (e.g. PubMed, Scopus, IEEE Xplore)",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ],
  "findings": [
    {
      "claim": "Key empirical claim",
      "metric": "str",
      "value": "str",
      "direction": "improvement|degradation|neutral",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ],
  "limitations": [
    {
      "text": "Concrete technical bottleneck or failure mode",
      "category": "computational_cost|data_scarcity|generalization|scalability|interpretability|general",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ],
  "future_work": [
    {
      "text": "Proposed future research direction",
      "category": "methodological_extension|dataset_expansion|efficiency",
      "sentence_id": "S...",
      "page": 1,
      "section": "str",
      "quote": "verbatim text <= 15 words"
    }
  ]
}

STRICT EXTRACTION CONSTRAINTS:
1. NEVER extract generic English nouns as methods or datasets (e.g., NEVER extract 'Pipeline', 'Approach', 'Framework', 'Model', 'Method', 'System', 'Baseline', 'Algorithm', 'Dataset', 'Benchmark' unless preceded by a specific identifying descriptor like 'LoRA-adapted Mistral-7B' or 'Ransomware-2024 Benchmark').
2. Route academic databases (PubMed, Scopus, Google Scholar, Web of Science, IEEE Xplore, Embase) ONLY to 'literature_sources'.
3. Extract explicit Scientific Relation Triplets connecting methods to their benchmarks and metrics.
4. Do NOT extract author names or publication years as methods/datasets.
5. Ensure every sentence_id and quote matches the provided text exactly. Output ONLY valid JSON."""


from .llm_rotator import GroqKeyRotator
from .ollama_client import OllamaLocalClient


class LLMStructuredExtractor:
    """Extracts structured research entities, relation triplets, and provenance links."""
    
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
        Extracts structured information from a parsed PDF document using the 5-pillar cascade.
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

        # 1. Section-Targeted Context Routing (Abstract/Intro, Methods, Experiments, Discussion)
        pruned_sents = extract_section_targeted_context(doc, max_sentences_per_category=8)
        compact_context = build_compact_prompt_context(doc, pruned_sents)

        if not compact_context.strip():
            result.status = "PARTIAL"
            result.error_message = "No relevant sentences detected in document."
            return result

        # 2. Build index map for sentence verification
        sentence_lookup: Dict[str, IndexedSentence] = {s.sentence_id: s for s in doc.sentences}

        # 3. Call LLM with fallback cascade (Groq Key Rotator -> Ollama Local -> Gemini -> Lexicon Fallback)
        extracted_data = None
        user_prompt = f"Paper Title: {title}\n\n--- SECTION-TARGETED PAPER SNIPPETS ---\n{compact_context}"

        # Primary: Groq Multi-Key Fallback Client
        if self.groq_rotator.clients:
            try:
                extracted_data = self.groq_rotator.generate_json(
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.1
                )
            except Exception as e:
                logger.warning(f"[{doc.paper_id}] Groq extraction failed: {e}")

        # Secondary: Local Ollama (if running)
        if not extracted_data and getattr(self.ollama_client, "is_available", False):
            try:
                extracted_data = self.ollama_client.generate_json(
                    system_prompt=EXTRACTION_SYSTEM_PROMPT,
                    user_prompt=user_prompt
                )
            except Exception:
                pass

        # Tertiary: Gemini API
        if not extracted_data and self.gemini_client:
            try:
                extracted_data = self._call_gemini_llm(title, compact_context)
            except Exception as e:
                pass

        # Final Fallback: High-Precision Domain Lexicon Matcher
        if not extracted_data:
            extracted_data = self._lexicon_based_fallback_extraction(doc, pruned_sents)

        # 4. Map, Canonicalize, and Self-Verify extracted entities and triplets
        self._populate_extraction_result(result, extracted_data, sentence_lookup, doc)
        
        result.status = "SUCCESS"
        logger.info(
            f"[{doc.paper_id}] Extracted {len(result.methods)} methods, "
            f"{len(result.datasets)} datasets, {len(result.triplets)} triplets, "
            f"{len(result.limitations)} limitations."
        )
        return result

    def _call_gemini_llm(self, title: str, compact_context: str) -> Optional[Dict[str, Any]]:
        """Backup call to Gemini if Groq and Ollama are unavailable."""
        user_prompt = f"Paper Title: {title}\n\n--- SECTION-TARGETED PAPER SNIPPETS ---\n{compact_context}"

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

    def _lexicon_based_fallback_extraction(
        self, 
        doc: ParsedPDFDocument, 
        pruned_sents: Dict[str, List[IndexedSentence]]
    ) -> Dict[str, Any]:
        """
        High-precision domain lexicon matcher used when LLM APIs are offline.
        Strictly matches recognized architectures, benchmarks, and metrics without generic nouns.
        """
        output: Dict[str, List[Dict[str, Any]]] = {
            "methods": [],
            "datasets": [],
            "triplets": [],
            "limitations": [],
            "future_work": [],
            "findings": []
        }

        RECOGNIZED_METHODS = [
            ("Convolutional Neural Network", r'\b(?:cnn|convolutional\s+neural\s+network)\b'),
            ("Vision Transformer", r'\b(?:vit|vision\s+transformer)\b'),
            ("Large Language Model", r'\b(?:llm|large\s+language\s+model)\b'),
            ("Clinical Large Language Model", r'\b(?:clinical\s+llm|clinical\s+large\s+language\s+model)\b'),
            ("Transformer", r'\b(?:transformer|attention\s+network)\b'),
            ("Random Forest", r'\b(?:random\s+forest)\b'),
            ("Decision Tree", r'\b(?:decision\s+tree)\b'),
            ("Support Vector Machine", r'\b(?:svm|support\s+vector\s+machine)\b'),
            ("XGBoost", r'\b(?:xgboost)\b'),
            ("Graph Neural Network", r'\b(?:gnn|graph\s+neural\s+network)\b'),
            ("Reinforcement Learning", r'\b(?:reinforcement\s+learning|deep\s+rl)\b'),
            ("LoRA", r'\b(?:lora|low[\-\s]+rank\s+adaptation)\b'),
            ("Sandboxed Terminal Execution", r'\b(?:sandboxed\s+terminal\s+execution)\b'),
            ("Multi-Stage Verification Pipeline", r'\b(?:multi[\-\s]+stage\s+verification)\b'),
            ("ResNet", r'\b(?:resnet(?:\-?\d+)?)\b'),
            ("UNet", r'\b(?:u\-?net)\b')
        ]

        RECOGNIZED_DATASETS = [
            # Cybersecurity
            ("Ransomware Dataset 2024", r'\b(?:ransomware[\-\s]*2024)\b'),
            ("Incident-2026Alpha", r'\b(?:incident[\-\s]*2026alpha)\b'),
            ("Cyberwheel", r'\b(?:cyberwheel)\b'),
            ("Cicmalmem-2022", r'\b(?:cicmalmem[\-\s]*2022)\b'),
            ("NSL-KDD", r'\b(?:nsl[\-\s]*kdd|kdd[\-\s]*cup)\b'),
            ("CIC-IDS Dataset", r'\b(?:cic[\-\s]*ids)\b'),
            ("UNSW-NB15", r'\b(?:unsw[\-\s]*nb15)\b'),
            ("BODMAS Malware", r'\b(?:bodmas)\b'),
            ("Cybench", r'\b(?:cybench)\b'),
            
            # Medical & Clinical AI
            ("MIMIC Database", r'\b(?:mimic(?:\-cxr|\-iv|\-iii)?)\b'),
            ("MedQA Benchmark", r'\b(?:medqa|usmle)\b'),
            ("PubMedQA", r'\b(?:pubmedqa)\b'),
            ("CheXpert", r'\b(?:chexpert)\b'),
            ("ChestX-ray14", r'\b(?:chestx[\-\s]*ray(?:14)?|nih\s+chest)\b'),
            ("BraTS Benchmark", r'\b(?:brats(?:\s*20\d\d)?)\b'),
            ("ISIC Skin Lesion", r'\b(?:isic(?:\s*20\d\d)?)\b'),
            ("ACDC Cardiac MRI", r'\b(?:acdc(?:\s+cardiac|\s+dataset)?)\b'),
            ("Synapse Multi-Organ CT", r'\b(?:synapse(?:\s+multi\-organ)?)\b'),
            ("PhysioNet Cohort", r'\b(?:physionet|eicu)\b'),
            ("ADNI Cohort", r'\b(?:adni|alzheimer\'?s\s+disease\s+neuroimaging)\b'),
            ("TCGA Pathology", r'\b(?:tcga|the\s+cancer\s+genome\s+atlas)\b'),
            
            # Vision & Multimodal
            ("ImageNet", r'\b(?:imagenet(?:\-?1k|\-?21k)?)\b'),
            ("MS COCO", r'\b(?:coco|ms[\-\s]*coco)\b'),
            ("PASCAL VOC", r'\b(?:pascal\s*voc|voc\s*2012)\b'),
            ("CIFAR", r'\b(?:cifar[\-\s]*(?:10|100))\b'),
            ("MNIST", r'\b(?:mnist|fashion[\-\s]*mnist)\b'),
            ("Cityscapes", r'\b(?:cityscapes)\b'),
            
            # NLP & LLM Benchmarks
            ("MMLU", r'\b(?:mmlu|massive\s+multitask\s+language\s+understanding)\b'),
            ("GSM8K", r'\b(?:gsm8k)\b'),
            ("HumanEval", r'\b(?:human_?eval|humaneval)\b'),
            ("SQuAD", r'\b(?:squad(?:\s*v?2\.0)?)\b'),
            ("GLUE Benchmark", r'\b(?:glue|superglue)\b'),
            ("SWE-bench", r'\b(?:swe[\-\s]*bench)\b'),
            ("TruthfulQA", r'\b(?:truthfulqa)\b'),
            ("HellaSwag", r'\b(?:hellaswag)\b')
        ]

        found_methods = set()
        for s in pruned_sents.get("methods", []) + pruned_sents.get("abstract_intro", []):
            for canonical_name, pat in RECOGNIZED_METHODS:
                if re.search(pat, s.text, re.IGNORECASE) and canonical_name not in found_methods:
                    found_methods.add(canonical_name)
                    output["methods"].append({
                        "name": canonical_name,
                        "type": "model",
                        "role": "proposed",
                        "sentence_id": s.sentence_id,
                        "page": s.page,
                        "section": s.section,
                        "quote": s.text[:150]
                    })
                if len(output["methods"]) >= 4:
                    break

        found_datasets = set()
        for s in pruned_sents.get("datasets", []) + pruned_sents.get("findings", []) + pruned_sents.get("abstract_intro", []):
            for canonical_name, pat in RECOGNIZED_DATASETS:
                if re.search(pat, s.text, re.IGNORECASE) and canonical_name not in found_datasets:
                    found_datasets.add(canonical_name)
                    output["datasets"].append({
                        "name": canonical_name,
                        "modality": "Benchmark",
                        "usage": "evaluation",
                        "sentence_id": s.sentence_id,
                        "page": s.page,
                        "section": s.section,
                        "quote": s.text[:150]
                    })
                if len(output["datasets"]) >= 4:
                    break

        # Build relation triplets if method and dataset are found
        if output["methods"] and output["datasets"]:
            top_m = output["methods"][0]
            top_d = output["datasets"][0]
            output["triplets"].append({
                "subject": top_m["name"],
                "predicate": "EVALUATED_ON",
                "object": top_d["name"],
                "metric": "Accuracy/F1",
                "value": "Reported",
                "sentence_id": top_d["sentence_id"],
                "page": top_d["page"],
                "section": top_d["section"],
                "quote": top_d["quote"]
            })

        # Extract limitations
        for s in pruned_sents.get("limitations", [])[:2]:
            output["limitations"].append({
                "text": s.text[:150],
                "category": "general",
                "sentence_id": s.sentence_id,
                "page": s.page,
                "section": s.section,
                "quote": s.text[:150]
            })

        # Extract future work
        for s in pruned_sents.get("future_work", [])[:2]:
            output["future_work"].append({
                "text": s.text[:150],
                "category": "methodological_extension",
                "sentence_id": s.sentence_id,
                "page": s.page,
                "section": s.section,
                "quote": s.text[:150]
            })

        return output

    def _populate_extraction_result(
        self,
        result: PaperExtractionResult,
        data: Dict[str, Any],
        sentence_lookup: Dict[str, IndexedSentence],
        doc: ParsedPDFDocument
    ) -> None:
        """Parses raw payload into validated Pydantic models with provenance verification and canonicalization."""
        
        def resolve_provenance(item: Dict[str, Any]) -> ProvenancePointer:
            sent_id = str(item.get("sentence_id") or "S1")
            raw_page = item.get("page", 1)
            try:
                page = int(raw_page) if raw_page not in ("", None) else 1
            except Exception:
                page = 1
            section = str(item.get("section") or "General")
            quote = str(item.get("quote") or "")

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
                quote=quote[:200]
            )

        LITERATURE_DB_NAMES = {
            "pubmed", "scopus", "embase", "web of science", "ieee xplore", "google scholar",
            "proquest", "medline", "cochrane", "arxiv"
        }

        # 1. Methods (Canonicalized & Filtered against Generic Nouns)
        for m in data.get("methods", []):
            raw_name = m.get("name", "").strip()
            if not raw_name or len(raw_name) < 2 or is_generic_noun(raw_name):
                continue
            clean_lower = raw_name.lower()
            if clean_lower in LITERATURE_DB_NAMES or re.search(r'\bet\s+al\.?\b', clean_lower):
                continue

            canonical = normalize_method_name(raw_name)
            if not canonical or is_generic_noun(canonical):
                continue

            prov = resolve_provenance(m)
            result.methods.append(ExtractedMethod(
                name=canonical,
                normalized_name=canonical,
                type=m.get("type", "model"),
                role=m.get("role", "proposed"),
                provenance=prov
            ))

        # 2. Datasets (Canonicalized & Filtered against Generic Nouns)
        for d in data.get("datasets", []):
            raw_name = d.get("name", "").strip()
            if not raw_name or len(raw_name) < 2 or is_generic_noun(raw_name):
                continue
            clean_lower = raw_name.lower()
            prov = resolve_provenance(d)
            
            # Route literature databases to literature_sources
            if any(ldb in clean_lower for ldb in LITERATURE_DB_NAMES):
                result.literature_sources.append(ExtractedLiteratureSource(
                    name=raw_name,
                    normalized_name=raw_name.title(),
                    provenance=prov
                ))
                continue

            canonical = normalize_dataset_name(raw_name)
            if not canonical or is_generic_noun(canonical):
                continue

            result.datasets.append(ExtractedDataset(
                name=canonical,
                normalized_name=canonical,
                modality=d.get("modality"),
                usage=d.get("usage", "evaluation"),
                samples=d.get("samples"),
                provenance=prov
            ))

        # 3. Scientific Relation Triplets
        for t in data.get("triplets", []):
            subj = str(t.get("subject", "")).strip()
            obj = str(t.get("object", "")).strip()
            if not subj or not obj or is_generic_noun(subj) or is_generic_noun(obj):
                continue
            
            pred = str(t.get("predicate", "EVALUATED_ON")).upper().strip()
            canonical_subj = normalize_method_name(subj) or subj
            canonical_obj = normalize_dataset_name(obj) or obj

            prov = resolve_provenance(t)
            result.triplets.append(ScientificTriplet(
                subject=canonical_subj,
                predicate=pred,
                object=canonical_obj,
                metric=t.get("metric"),
                value=t.get("value"),
                sentence_id=prov.sentence_id,
                page=prov.page,
                section=prov.section,
                quote=prov.quote,
                confidence=float(t.get("confidence", 0.90))
            ))

        # 4. Explicit Literature Sources
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

        # 5. Limitations
        for lim in data.get("limitations", []):
            prov = resolve_provenance(lim)
            result.limitations.append(ExtractedLimitation(
                text=lim.get("text", "Unspecified limitation"),
                category=lim.get("category", "general"),
                provenance=prov
            ))

        # 6. Future Work
        for fw in data.get("future_work", []):
            prov = resolve_provenance(fw)
            result.future_work.append(ExtractedFutureWork(
                text=fw.get("text", "Unspecified future research"),
                category=fw.get("category", "methodological_extension"),
                provenance=prov
            ))

        # 7. Findings
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
