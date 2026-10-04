"""
Section Detector and Smart Context Pruner for Stage 3 Research Information Extraction.
Routes relevant section blocks and prunes 1000s of sentences into ~40-70 target candidate sentences.
"""

import re
import logging
from typing import List, Dict, Any, Set, Tuple
from .parser import ParsedPDFDocument, IndexedSentence

logger = logging.getLogger("trendscope.extraction.detector")

# Section heading regex maps
SECTION_CATEGORIES = {
    "methods": [
        r'\bmethod(?:s|ology)?\b',
        r'\bproposed\s+(?:method|framework|approach|model|architecture)\b',
        r'\bapproach\b',
        r'\bmodel\s+architecture\b',
        r'\bnetwork\s+architecture\b',
        r'\bframework\b',
        r'\bimplementation\s+details\b'
    ],
    "datasets": [
        r'\bdataset(?:s)?\b',
        r'\bbenchmark(?:s)?\b',
        r'\bdata\s+(?:source|collection|preprocessing|description)?\b',
        r'\bexperimental\s+(?:setup|setting|settings)\b',
        r'\bexperiments?\b',
        r'\bevaluation\b',
        r'\bmaterials\b',
        r'\bcohort(?:s)?\b'
    ],
    "findings": [
        r'\bresults?\b',
        r'\bfindings?\b',
        r'\bperformance\b',
        r'\bquantitative\s+evaluation\b',
        r'\bablation\s+(?:study|experiments?)\b',
        r'\bcomparative\s+analysis\b'
    ],
    "limitations": [
        r'\blimitation(?:s)?\b',
        r'\bdiscussion\b',
        r'\bthreats?\s+to\s+validity\b',
        r'\bbroader\s+impact(?:s)?\b',
        r'\bfailure\s+cases?\b'
    ],
    "future_work": [
        r'\bfuture\s+(?:work|directions?|research)\b',
        r'\bconclusion(?:s)?\b',
        r'\bconcluding\s+remarks\b'
    ]
}

# Cue keyword patterns for sentence-level classification
KEYWORD_PATTERNS = {
    "methods": [
        r'\bwe\s+(?:propose|introduce|develop|present|design|implement|formulate)\b',
        r'\bour\s+(?:architecture|model|framework|method|approach|algorithm|pipeline|system)\b',
        r'\b(?:transformer|attention|backbone|convolutional|densenet|resnet|vit|neural|deep\s+learning|llm|agent|prompt)\b',
        r'\b(?:decision\s+tree|random\s+forest|svm|logistic\s+regression|xgboost|ctree|utree|federated|fl-tdabc)\b',
        r'\b(?:loss\s+function|optimization|reinforcement\s+learning|chain-of-thought|reasoning|meta-learner)\b'
    ],
    "datasets": [
        r'\b(?:dataset|benchmark|corpus|database|cohort|registry|clinical\s+trial|scans|mri|ct\s+scans)\b',
        r'\b(?:evaluated\s+on|trained\s+on|tested\s+on|experimented\s+with|collected\s+from|patient\s+records)\b',
        r'\b(?:mimic|eicu|imagenet|kaggle|synthetic|patients|cases|subjects|ehr|emr|fracatlas|medqa|pedcorpus|medmnist)\b'
    ],
    "literature_sources": [
        r'\b(?:searches?\s+were\s+conducted|literature\s+search|queried\s+the\s+databases?|systematic\s+review)\b',
        r'\b(?:pubmed|scopus|embase|web\s+of\s+science|ieee\s+xplore|google\s+scholar|proquest|medline)\b'
    ],
    "findings": [
        r'\b(?:achieves?|outperforms?|improved\s+by|superior\s+to|accuracy\s+of|auroc|f1-score|bleu|sensitivity)\b',
        r'\b(?:statistically\s+significant|p\s*[<=]\s*0\.\d+|demonstrated\s+higher|reduced\s+error)\b'
    ],
    "limitations": [
        r'\blimitation\b', r'\blimited\s+by\b', r'\bdrawback\b', r'\bshortcoming\b',
        r'\bweakness\b', r'\bstruggles?\s+with\b', r'\bdegrades?\b', r'\bcomputational\s+(?:cost|complexity|overhead)\b',
        r'\bmemory\s+(?:cost|overhead|consumption)\b', r'\bgeneralization\b', r'\bscalability\b', r'\blacks?\s+external\s+validation\b'
    ],
    "future_work": [
        r'\bfuture\s+(?:work|research|direction|investigation|avenue)\b',
        r'\bwe\s+plan\s+to\b', r'\bwe\s+intend\s+to\b', r'\bpromising\s+direction\b',
        r'\bwill\s+be\s+explored\b', r'\bextending\s+(?:our|the)\b', r'\bremains\s+for\s+future\b'
    ]
}


DISCOURSE_MARKERS = {
    "however", "moreover", "furthermore", "nevertheless", "nonetheless", "therefore",
    "overall", "over", "given", "through", "here", "these", "prior", "specifically"
}


def classify_section_header(header_name: str) -> str:
    """
    Classifies a raw section header into a canonical category or 'other'.
    """
    clean_name = header_name.lower().strip()
    for category, patterns in SECTION_CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, clean_name):
                return category
    return "other"


def score_sentence_relevance(sentence_text: str, category: str) -> int:
    """
    Computes a keyword relevance score for a sentence for a target category.
    """
    text_lower = sentence_text.lower()
    score = 0
    patterns = KEYWORD_PATTERNS.get(category, [])
    for pattern in patterns:
        if re.search(pattern, text_lower):
            score += 1
    return score


def classify_sentence_intent(sentence_text: str, section_header: str = "") -> Dict[str, Any]:
    """
    Multi-label classification of a scientific sentence.
    Distinguishes methods, datasets, literature sources, findings, limitations, and future work.
    """
    text_lower = sentence_text.lower().strip()
    sec_cat = classify_section_header(section_header)
    
    labels = {
        "method": False,
        "dataset": False,
        "literature_source": False,
        "finding": False,
        "limitation": False,
        "future_work": False
    }
    scores: Dict[str, int] = {}
    
    for cat, patterns in KEYWORD_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text_lower))
        if sec_cat == cat:
            score += 2
        scores[cat] = score
    
    if scores.get("literature_sources", 0) > 0 and any(kw in text_lower for kw in ["search", "scopus", "pubmed", "proquest", "databases"]):
        labels["literature_source"] = True
    
    labels["method"] = scores.get("methods", 0) >= 1
    labels["dataset"] = scores.get("datasets", 0) >= 1 and not labels["literature_source"]
    labels["finding"] = scores.get("findings", 0) >= 1 or sec_cat == "findings"
    labels["limitation"] = scores.get("limitations", 0) >= 1 or sec_cat == "limitations"
    labels["future_work"] = scores.get("future_work", 0) >= 1 or sec_cat == "future_work"
    
    confidence = min(1.0, max(0.5, sum(scores.values()) * 0.2))
    return {
        "labels": labels,
        "scores": scores,
        "confidence": round(confidence, 2)
    }


def extract_smart_candidate_context(
    doc: ParsedPDFDocument, 
    max_sentences_per_category: int = 5
) -> Dict[str, List[IndexedSentence]]:
    """
    Prunes the complete document (1000s of sentences) down to ~15-20 high-signal candidate sentences,
    organized by extraction goal (methods, datasets, limitations, future_work).
    """
    categorized_sentences: Dict[str, List[IndexedSentence]] = {
        "methods": [],
        "datasets": [],
        "limitations": [],
        "future_work": []
    }
    
    # 1. Pass: Route sentences based on recognized section headings
    for section_name, sents in doc.sections.items():
        category = classify_section_header(section_name)
        if category in categorized_sentences:
            for s in sents:
                if len(s.text.strip()) >= 20:  # skip trivial fragments
                    categorized_sentences[category].append(s)

    # 2. Pass: If any category has few sentences, score via keywords
    for category in ["methods", "datasets", "limitations", "future_work"]:
        if len(categorized_sentences[category]) < 4:
            scored_candidates: List[Tuple[int, IndexedSentence]] = []
            for s in doc.sentences:
                sec_lower = s.section.lower()
                if "reference" in sec_lower or "bibliography" in sec_lower or "acknowledg" in sec_lower:
                    continue
                if len(s.text.strip()) < 20:
                    continue
                score = score_sentence_relevance(s.text, category)
                if score > 0:
                    scored_candidates.append((score, s))
            
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            for _, s in scored_candidates[:max_sentences_per_category]:
                if s not in categorized_sentences[category]:
                    categorized_sentences[category].append(s)

    # 3. Pass: Rank & prune each category to max_sentences_per_category
    pruned_result: Dict[str, List[IndexedSentence]] = {}
    for category, sents in categorized_sentences.items():
        scored = [(score_sentence_relevance(s.text, category), s) for s in sents]
        scored.sort(key=lambda x: x[0], reverse=True)
        top_sents = [s for _, s in scored[:max_sentences_per_category]]
        top_sents.sort(key=lambda s: (s.page, int(s.sentence_id[1:]) if s.sentence_id[1:].isdigit() else 0))
        pruned_result[category] = top_sents

    total_selected = sum(len(v) for v in pruned_result.values())
    logger.debug(f"[{doc.paper_id}] Selected {total_selected} target sentences out of {len(doc.sentences)} total.")
    
    return pruned_result


def build_compact_prompt_context(
    doc: ParsedPDFDocument, 
    pruned_sents: Dict[str, List[IndexedSentence]]
) -> str:
    """
    Formats the pruned sentences into a clean, numbered context block ready for the LLM prompt.
    """
    seen_sentence_ids: Set[str] = set()
    ordered_all_sents: List[IndexedSentence] = []
    
    for category in ["methods", "datasets", "limitations", "future_work"]:
        for s in pruned_sents.get(category, []):
            if s.sentence_id not in seen_sentence_ids:
                seen_sentence_ids.add(s.sentence_id)
                ordered_all_sents.append(s)

    # Sort in document reading order
    ordered_all_sents.sort(key=lambda s: (s.page, int(s.sentence_id[1:]) if s.sentence_id[1:].isdigit() else 0))

    lines = []
    current_sec = None
    for s in ordered_all_sents:
        if s.section != current_sec:
            current_sec = s.section
            lines.append(f"\n[SECTION: {s.section.upper()} | Page {s.page}]")
        lines.append(f"[{s.sentence_id}] {s.text}")

    return "\n".join(lines)
