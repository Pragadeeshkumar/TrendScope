"""
Deterministic Evidence Validation Pipeline for Stage 3 Research Information Extraction.
Enforces strict scientific ontology boundaries, discourse word rejection,
author name filtering, literature source routing, and verbatim provenance grounding.
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from .models import (
    ScientificEntity,
    ScientificFinding,
    ScientificRelation,
    ScientificLimitation,
    ScientificFutureWork,
    PaperEvidenceRecord,
    ConfidenceScores
)

logger = logging.getLogger("trendscope.extraction.validator")

# Universal closed-class grammatical tokens (pronouns, determiners, quantifiers, conjunctions, discourse)
CLOSED_CLASS_FUNCTION_WORDS = {
    # Pronouns & Reflexives
    "i", "me", "my", "myself", "we", "us", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    # Determiners & Quantifiers
    "a", "an", "the", "such", "each", "every", "both", "all", "half",
    "several", "few", "fewer", "fewest", "many", "much", "more", "most",
    "other", "others", "another", "some", "any", "no", "none", "either", "neither",
    # Prepositions & Connectives
    "about", "above", "across", "after", "against", "along", "among", "around",
    "as", "at", "before", "behind", "below", "beneath", "beside", "between",
    "beyond", "by", "down", "during", "except", "for", "from", "in", "inside",
    "into", "near", "of", "off", "on", "onto", "out", "outside", "over", "past",
    "through", "throughout", "to", "toward", "towards", "under", "underneath",
    "until", "up", "upon", "with", "within", "without",
    # Discourse markers & generic prose tokens
    "however", "moreover", "furthermore", "nevertheless", "nonetheless", "therefore",
    "thus", "hence", "overall", "specifically", "additionally", "instead", "meanwhile",
    "notably", "namely", "finally", "first", "second", "third", "given", "here",
    "prior", "historical", "automated", "participants", "conclusions", "conclusion",
    "discussion", "introduction", "background", "results", "methods", "evaluation",
    "decision", "better", "online", "they", "its", "such", "both", "few"
}

DISCOURSE_STOPWORDS = CLOSED_CLASS_FUNCTION_WORDS

# Known Literature Databases / Academic Indexes
LITERATURE_DATABASES = {
    "pubmed", "scopus", "web of science", "ieee xplore", "embase", "proquest",
    "google scholar", "cochrane", "cochrane library", "medline", "cinahl",
    "springerlink", "sciencedirect", "arxiv", "biorxiv", "medrxiv"
}

# Known Dataset Indicators
DATASET_INDICATORS = [
    "dataset", "benchmark", "corpus", "cohort", "registry", "database",
    "trial", "patients", "images", "samples", "cases", "scans", "bank", "set"
]

# Known Method Indicators
METHOD_INDICATORS = [
    "model", "net", "network", "transformer", "bert", "gpt", "algorithm",
    "framework", "architecture", "pipeline", "loss", "encoder", "decoder",
    "classifier", "regressor", "agent", "system", "method", "technique", "gan",
    "learning", "optimization", "attention", "propagation", "clustering", "regression",
    "diffusion", "reasoning", "search", "routing", "decoding", "prompting", "tuning",
    "adaptation", "distillation", "embedding", "tree", "forest", "svm", "boosting",
    "descent", "regularization", "representation", "space", "fusion"
]


class ValidationResult(BaseModel):
    """Result of validating a single entity."""
    is_valid: bool
    status: str = Field(description="'ACCEPTED', 'REJECTED', 'FLAGGED'")
    reason: str
    adjusted_confidence: float
    rerouted_type: Optional[str] = None


class ValidationReport(BaseModel):
    """Corpus or paper level validation summary statistics."""
    total_evaluated: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    flagged_count: int = 0
    rejection_reasons: Dict[str, int] = Field(default_factory=dict)

    @property
    def rejection_rate(self) -> float:
        return (self.rejected_count / self.total_evaluated) if self.total_evaluated > 0 else 0.0

    @property
    def acceptance_rate(self) -> float:
        return (self.accepted_count / self.total_evaluated) if self.total_evaluated > 0 else 0.0


def validate_scientific_entity(
    entity: ScientificEntity,
    sentence_lookup: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """
    Deterministically validates a single ScientificEntity against scientific ontology rules,
    discourse filters, literature database routing, and quote grounding.
    """
    raw_name = entity.raw_name.strip()
    raw_lower = raw_name.lower()
    clean_name = re.sub(r"[^\w\s-]", "", raw_lower).strip()

    # 1. Rule: Numerical tokens & Publication Years (e.g. '400', '1000', '2022', '2023', '2024')
    if re.match(r"^[\d\.,\s%]+$", raw_name) or re.match(r"^(19|20)\d{2}(\s*[-–/]\s*(19|20)?\d{2})?$", raw_name):
        return ValidationResult(
            is_valid=False,
            status="REJECTED",
            reason=f"Numerical value or year rather than scientific entity: '{raw_name}'",
            adjusted_confidence=0.0
        )

    # 2. Rule: Closed-Class Function Words / Discourse / Determiner rejection
    if clean_name in CLOSED_CLASS_FUNCTION_WORDS:
        return ValidationResult(
            is_valid=False,
            status="REJECTED",
            reason=f"Closed-class grammatical / discourse token: '{raw_name}'",
            adjusted_confidence=0.0
        )

    # 3. Rule: Length & single character anomalies
    if len(clean_name) <= 2 and not clean_name.isupper():
        return ValidationResult(
            is_valid=False,
            status="REJECTED",
            reason=f"Name too short to be a valid scientific entity: '{raw_name}'",
            adjusted_confidence=0.0
        )

    # 4. Rule: Author / Personal Name Check (e.g., 'Elliot Bolton', 'John Smith et al.')
    if re.match(r"^[A-Z][a-z]+\s+[A-Z][a-z]+(\s+et\s+al\.?)?$", raw_name):
        has_method_word = any(ind in raw_lower for ind in METHOD_INDICATORS)
        has_ds_word = any(ind in raw_lower for ind in DATASET_INDICATORS)
        if not has_method_word and not has_ds_word:
            return ValidationResult(
                is_valid=False,
                status="REJECTED",
                reason=f"Identified as personal/author name or geographic phrase: '{raw_name}'",
                adjusted_confidence=0.0
            )

    # 4. Rule: Literature Database / Search Engine Context Rerouting
    is_lit_db = clean_name in LITERATURE_DATABASES or any(db in clean_name for db in LITERATURE_DATABASES)
    if is_lit_db:
        if entity.entity_type == "dataset":
            # Check quote context for search terms
            quote_lower = (entity.provenance.quote or "").lower()
            search_signals = ["searched", "searches", "search", "retrieved", "query", "database search", "scoping", "literature"]
            if any(sig in quote_lower for sig in search_signals) or clean_name in LITERATURE_DATABASES:
                return ValidationResult(
                    is_valid=True,
                    status="ACCEPTED",
                    reason="Rerouted literature search database to literature_source",
                    adjusted_confidence=0.98,
                    rerouted_type="literature_source"
                )

    # 5. Rule: Evidence Grounding (Entity must appear in quote or sentence)
    quote = (entity.provenance.quote or "").lower()
    sent_text = ""
    if sentence_lookup and entity.provenance.sentence_id in sentence_lookup:
        sent_text = sentence_lookup[entity.provenance.sentence_id].lower()

    target_text = quote + " " + sent_text
    # Simple sub-token check
    name_tokens = [t for t in re.split(r"[\s\-_]+", clean_name) if len(t) > 2]
    matched_tokens = [t for t in name_tokens if t in target_text]

    if name_tokens and (len(matched_tokens) / len(name_tokens)) < 0.5:
        # Less than half the tokens found in quote
        return ValidationResult(
            is_valid=False,
            status="REJECTED",
            reason=f"Hallucination: entity tokens '{entity.raw_name}' not grounded in quote/sentence",
            adjusted_confidence=0.1
        )

    # 6. Rule: Dataset Type Validation
    if entity.entity_type == "dataset":
        # Check if entity or quote has dataset indicators or known benchmark structure
        has_ds_signal = any(ind in raw_lower or ind in quote for ind in DATASET_INDICATORS)
        if not has_ds_signal and len(clean_name.split()) > 5:
            return ValidationResult(
                is_valid=True,
                status="FLAGGED",
                reason=f"Dataset lacks explicit benchmark/cohort signals: '{entity.raw_name}'",
                adjusted_confidence=0.65
            )

    return ValidationResult(
        is_valid=True,
        status="ACCEPTED",
        reason="Passed all deterministic validation checks",
        adjusted_confidence=entity.confidence.composite_score
    )


def validate_paper_evidence_record(
    record: PaperEvidenceRecord,
    sentence_lookup: Optional[Dict[str, str]] = None
) -> Tuple[PaperEvidenceRecord, ValidationReport]:
    """
    Validates all entities, findings, and relations within a PaperEvidenceRecord.
    Filters out invalid entities and cascades cleanups to dependent relations and findings.
    """
    report = ValidationReport()
    valid_entities: List[ScientificEntity] = []
    valid_entity_ids = set()

    for ent in record.entities:
        report.total_evaluated += 1
        res = validate_scientific_entity(ent, sentence_lookup=sentence_lookup)

        if res.is_valid:
            if res.rerouted_type:
                ent.entity_type = res.rerouted_type
                ent.role = "database"
            if res.status == "FLAGGED":
                report.flagged_count += 1
                ent.confidence.extraction_confidence = min(ent.confidence.extraction_confidence, res.adjusted_confidence)
            else:
                report.accepted_count += 1
            valid_entities.append(ent)
            valid_entity_ids.add(ent.entity_id)
        else:
            report.rejected_count += 1
            report.rejection_reasons[res.reason] = report.rejection_reasons.get(res.reason, 0) + 1
            logger.info(f"[{record.paper_id}] Rejected entity '{ent.raw_name}': {res.reason}")

    # Clean up relations pointing to rejected entities
    valid_relations: List[ScientificRelation] = []
    for rel in record.relations:
        if rel.source_entity_id in valid_entity_ids and rel.target_entity_id in valid_entity_ids:
            valid_relations.append(rel)

    # Clean up findings
    valid_findings: List[ScientificFinding] = []
    for f in record.findings:
        f.method_entity_ids = [m for m in f.method_entity_ids if m in valid_entity_ids]
        f.baseline_entity_ids = [b for b in f.baseline_entity_ids if b in valid_entity_ids]
        f.dataset_entity_ids = [d for d in f.dataset_entity_ids if d in valid_entity_ids]
        valid_findings.append(f)

    # Clean up limitations
    valid_limitations: List[ScientificLimitation] = []
    for lim in record.limitations:
        lim.affected_entity_ids = [a for a in lim.affected_entity_ids if a in valid_entity_ids]
        valid_limitations.append(lim)

    validated_record = PaperEvidenceRecord(
        paper_id=record.paper_id,
        title=record.title,
        publication_year=record.publication_year,
        entities=valid_entities,
        findings=valid_findings,
        relations=valid_relations,
        limitations=valid_limitations,
        future_work=record.future_work
    )

    return validated_record, report
