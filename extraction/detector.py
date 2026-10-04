"""
Section Detector and Smart Context Pruner for Stage 3 Research Information Extraction.
Implements Layout-Guided Section Routing across:
1. Abstract & Introduction (Core contributions & main models)
2. Methodology (Algorithms, loss functions, architectures)
3. Experiments (Datasets, benchmarks, baselines, evaluation metrics)
4. Discussion & Limitations (Failure cases, computational bottlenecks, future directions)
"""

import re
import logging
from typing import List, Dict, Any, Set, Tuple
from .parser import ParsedPDFDocument, IndexedSentence

logger = logging.getLogger("trendscope.extraction.detector")

# Section heading regex maps
SECTION_CATEGORIES = {
    "abstract_intro": [
        r'\babstract\b',
        r'\bintroduction\b',
        r'\boverview\b',
        r'\bbackground\b'
    ],
    "methods": [
        r'\bmethod(?:s|ology)?\b',
        r'\bproposed\s+(?:method|framework|approach|model|architecture)\b',
        r'\bapproach\b',
        r'\bmodel\s+architecture\b',
        r'\bnetwork\s+architecture\b',
        r'\bframework\b',
        r'\bimplementation\s+details\b',
        r'\bsystem\s+design\b',
        r'\balgorithm\b'
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
        r'\b(?:decision\s+tree|random\s+forest|svm|logistic\s+regression|xgboost|gnn|gat|gcn|diffusion|ddpm|mamba)\b',
        r'\b(?:loss\s+function|optimization|reinforcement\s+learning|chain-of-thought|reasoning|meta-learner|lora|qlora)\b'
    ],
    "datasets": [
        r'\b(?:dataset|benchmark|corpus|database|cohort|registry|clinical\s+trial|scans|mri|ct\s+scans)\b',
        r'\b(?:evaluated\s+on|trained\s+on|tested\s+on|experimented\s+with|collected\s+from|patient\s+records)\b',
        r'\b(?:mimic|eicu|imagenet|kaggle|synthetic|patients|cases|subjects|ransomware|cyberwheel|kdd|nsl-kdd|medqa)\b'
    ],
    "literature_sources": [
        r'\b(?:searches?\s+were\s+conducted|literature\s+search|queried\s+the\s+databases?|systematic\s+review)\b',
        r'\b(?:pubmed|scopus|embase|web\s+of\s+science|ieee\s+xplore|google\s+scholar|proquest|medline)\b'
    ],
    "findings": [
        r'\b(?:achieves?|outperforms?|improved\s+by|superior\s+to|accuracy\s+of|auroc|f1-score|f1\s+score|bleu|sensitivity)\b',
        r'\b(?:statistically\s+significant|p\s*[<=]\s*0\.\d+|demonstrated\s+higher|reduced\s+error|higher\s+accuracy)\b'
    ],
    "limitations": [
        r'\blimitation\b', r'\blimited\s+by\b', r'\bdrawback\b', r'\bshortcoming\b',
        r'\bweakness\b', r'\bstruggles?\s+with\b', r'\bdegrades?\b', r'\bcomputational\s+(?:cost|complexity|overhead)\b',
        r'\bmemory\s+(?:cost|overhead|consumption)\b', r'\bgeneralization\b', r'\bscalability\b', r'\blacks?\s+external\s+validation\b',
        r'\bhigh\s+latency\b', r'\bsynthetic\s+bias\b'
    ],
    "future_work": [
        r'\bfuture\s+(?:work|research|direction|investigation|avenue)\b',
        r'\bwe\s+plan\s+to\b', r'\bwe\s+intend\s+to\b', r'\bpromising\s+direction\b',
        r'\bwill\s+be\s+explored\b', r'\bextending\s+(?:our|the)\b', r'\bremains\s+for\s+future\b'
    ]
}


def classify_section_header(header_name: str) -> str:
    """Classifies a raw section header into a canonical category or 'other'."""
    if not header_name:
        return "other"
        
    h_lower = header_name.lower().strip()
    for cat, patterns in SECTION_CATEGORIES.items():
        for pat in patterns:
            if re.search(pat, h_lower):
                return cat
                
    return "other"


def score_sentence_relevance(sent: IndexedSentence, target_category: str) -> float:
    """Scores how relevant a sentence is to a given scientific extraction category."""
    text_lower = sent.text.lower()
    score = 0.0
    
    # 1. Section alignment bonus
    sec_cat = classify_section_header(sent.section)
    if sec_cat == target_category:
        score += 3.0
    elif sec_cat == "abstract_intro" and target_category in {"methods", "limitations"}:
        score += 1.5
        
    # 2. Keyword pattern matches
    patterns = KEYWORD_PATTERNS.get(target_category, [])
    for pat in patterns:
        matches = len(re.findall(pat, text_lower))
        score += matches * 2.0
        
    # 3. Sentence length penalty (very short or very long sentences)
    words = len(text_lower.split())
    if words < 6 or words > 60:
        score -= 1.0
        
    return score


def extract_section_targeted_context(
    doc: ParsedPDFDocument,
    max_sentences_per_category: int = 8
) -> Dict[str, List[IndexedSentence]]:
    """
    Extracts high-signal candidate sentences grouped by section-targeted category.
    Ensures comprehensive coverage of Contributions, Methods, Benchmarks, and Limitations.
    """
    categorized_sents: Dict[str, List[Tuple[float, IndexedSentence]]] = {
        "abstract_intro": [],
        "methods": [],
        "datasets": [],
        "literature_sources": [],
        "findings": [],
        "limitations": [],
        "future_work": []
    }
    
    seen_ids: Set[str] = set()
    
    for sent in doc.sentences:
        for cat in categorized_sents.keys():
            score = score_sentence_relevance(sent, cat)
            if score > 1.0:
                categorized_sents[cat].append((score, sent))
                
    # Sort by score descending and take top N
    final_selection: Dict[str, List[IndexedSentence]] = {}
    for cat, scored_list in categorized_sents.items():
        scored_list.sort(key=lambda x: x[0], reverse=True)
        chosen = []
        for score, sent in scored_list:
            if sent.sentence_id not in seen_ids or len(chosen) < 3:
                chosen.append(sent)
                seen_ids.add(sent.sentence_id)
            if len(chosen) >= max_sentences_per_category:
                break
        final_selection[cat] = chosen
        
    return final_selection


# Retain backward-compatible alias
extract_smart_candidate_context = extract_section_targeted_context


def build_compact_prompt_context(
    doc: ParsedPDFDocument, 
    pruned_sents: Dict[str, List[IndexedSentence]]
) -> str:
    """
    Formats the candidate sentences into a compact, clearly structured prompt block
    with sentence IDs [S...], section headers, and page coordinates.
    """
    lines = []
    
    category_labels = [
        ("abstract_intro", "=== ABSTRACT & INTRODUCTION ==="),
        ("methods", "=== PROPOSED ARCHITECTURE & METHODOLOGY ==="),
        ("datasets", "=== BENCHMARKS, DATASETS & EXPERIMENTAL SETUP ==="),
        ("findings", "=== EMPIRICAL FINDINGS & EVALUATION METRICS ==="),
        ("limitations", "=== LIMITATIONS, BOTTLENECKS & FAILURE CASES ==="),
        ("future_work", "=== FUTURE RESEARCH DIRECTIONS ===")
    ]
    
    for cat_key, header in category_labels:
        sents = pruned_sents.get(cat_key, [])
        if sents:
            lines.append(f"\n{header}")
            for s in sents:
                lines.append(f"[{s.sentence_id}] (p.{s.page}, {s.section}): {s.text}")
                
    return "\n".join(lines)
