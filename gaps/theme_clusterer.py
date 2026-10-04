"""
Semantic Limitation Theme Clusterer for Stage 6.
Groups hundreds of raw extracted paper limitation sentences into cohesive, recurring research themes.
"""

import re
import logging
from collections import defaultdict
from typing import List, Dict, Any, Tuple
from .models import LimitationTheme, LimitationInstance

logger = logging.getLogger("trendscope.gaps.clusterer")

THEME_TAXONOMY_RULES = [
    {
        "id": "theme_compute_scaling",
        "name": "High Computational Complexity and Memory Scaling",
        "category": "computational_cost",
        "keywords": [r'memory', r'compute', r'computational', r'gpu', r'quadratic', r'scaling', r'latency', r'inference speed', r'resource', r'vram'],
        "desc": "Challenges regarding exponential compute demands, GPU VRAM constraints on large models, and high latency inference."
    },
    {
        "id": "theme_generalization_robustness",
        "name": "Out-of-Distribution Generalization and Cross-Domain Robustness",
        "category": "generalization",
        "keywords": [r'generalization', r'out-of-distribution', r'ood', r'domain shift', r'robustness', r'cross-domain', r'unseen', r'external validation', r'cohort'],
        "desc": "Performance degradation when applied to novel environments, unseen data distributions, or real-world variations."
    },
    {
        "id": "theme_data_annotation",
        "name": "Reliance on Large-Scale Supervised Annotations and Pretraining",
        "category": "data_scarcity",
        "keywords": [r'annotation', r'labeled data', r'scarcity', r'pretraining', r'few samples', r'ground truth', r'labeling cost', r'sparse labels', r'small sample'],
        "desc": "Heavy dependence on expensive manual human annotations and large-scale pretraining datasets."
    },
    {
        "id": "theme_safety_alignment",
        "name": "Safety Guardrails, Privacy Protections, and Alignment Risks",
        "category": "safety_alignment",
        "keywords": [r'safety', r'alignment', r'jailbreak', r'adversarial', r'guardrail', r'risk', r'harmful', r'misalignment', r'collusion', r'privacy', r'hipaa', r'leakage'],
        "desc": "Vulnerabilities to adversarial bypasses, privacy leakages in sensitive domains, and safety alignment failures."
    },
    {
        "id": "theme_evaluation_benchmarking",
        "name": "Process-Level Evaluation Gaps and Synthetic Benchmark Bias",
        "category": "evaluation_gap",
        "keywords": [r'benchmark', r'evaluation', r'metric', r'synthetic', r'proxy', r'shortcut', r'reward hacking', r'fidelity', r'static dataset', r'clinical endpoint'],
        "desc": "Limitations of static benchmark metrics that fail to evaluate multi-step reasoning trajectories or real-world nuance."
    },
    {
        "id": "theme_interpretability_explainability",
        "name": "Black-Box Decision Making and Uncertainty Quantification",
        "category": "interpretability",
        "keywords": [r'interpretability', r'black-box', r'explainable', r'uncertainty', r'hallucination', r'calibration', r'attribution', r'trust', r'explainability', r'confidence'],
        "desc": "Lack of transparent explanations for intermediate reasoning and unreliable confidence calibration."
    },
    {
        "id": "theme_clinical_workflow",
        "name": "Clinical Workflow Integration and Regulatory Validation",
        "category": "clinical_translation",
        "keywords": [r'clinical workflow', r'ehr', r'electronic health', r'hospital', r'physician', r'deployment', r'regulatory', r'fda', r'prospective', r'bedside', r'clinical trial'],
        "desc": "Friction in integrating AI assistance into live clinical workflows, EHR environments, and prospective medical trials."
    },
    {
        "id": "theme_multimodal_fusion",
        "name": "Cross-Modal Alignment and Heterogeneous Data Integration",
        "category": "multimodal_fusion",
        "keywords": [r'multimodal', r'cross-modal', r'heterogeneous', r'fusion', r'alignment', r'missing modality', r'multi-omics', r'imaging and text'],
        "desc": "Challenges in fusing disparate data types (e.g., genomics, imaging, time-series, text) with asynchronous alignment."
    },
    {
        "id": "theme_sample_efficiency",
        "name": "Class Imbalance and Long-Tail Distribution Shift",
        "category": "sample_efficiency",
        "keywords": [r'imbalance', r'long-tail', r'rare', r'skewed', r'subgroup', r'underrepresented', r'demographic bias', r'fairness'],
        "desc": "Vulnerability to extreme class imbalance and poor performance on rare pathologies or underrepresented demographic subgroups."
    }
]


def match_limitation_to_theme(lim_text: str) -> Tuple[str, str, str, str]:
    """Matches a limitation text against theme rule patterns."""
    text_lower = lim_text.lower()
    
    best_match = None
    max_score = 0

    for rule in THEME_TAXONOMY_RULES:
        score = sum(1 for kw in rule["keywords"] if re.search(kw, text_lower))
        if score > max_score:
            max_score = score
            best_match = rule

    if best_match and max_score >= 1:
        return best_match["id"], best_match["name"], best_match["category"], best_match["desc"]

    # Dynamic fallback based on syntactic focus
    if any(w in text_lower for w in ["cost", "speed", "time", "complex", "param"]):
        return "theme_compute_scaling", "High Computational Complexity and Memory Scaling", "computational_cost", "Challenges regarding compute demands and latency constraints."
    if any(w in text_lower for w in ["data", "sample", "size", "patient", "cohort", "limit"]):
        return "theme_data_annotation", "Reliance on Large-Scale Supervised Annotations and Pretraining", "data_scarcity", "Sample size constraints and dataset limitations."

    return "theme_general_empirical", "Empirical System Trade-offs and Domain Bottlenecks", "general", "Empirical design trade-offs and specialized system bottlenecks identified in domain literature."


def cluster_limitation_themes(papers: List[Dict[str, Any]]) -> List[LimitationTheme]:
    """
    Extracts and groups all limitation instances from papers into canonical limitation themes.
    """
    theme_buckets = defaultdict(lambda: {
        "name": "",
        "category": "",
        "desc": "",
        "instances": [],
        "paper_ids": set(),
        "years": [],
        "quotes": []
    })

    for p in papers:
        pid = p.get("paper_id", "unknown")
        title = p.get("title", "Unknown")
        year = p.get("publication_year") or 2026

        for lim in p.get("limitations", []):
            text = lim.get("text", "").strip()
            if not text:
                continue

            theme_id, name, cat, desc = match_limitation_to_theme(text)
            
            prov = lim.get("provenance", {})
            quote = prov.get("quote") or text

            theme_buckets[theme_id]["name"] = name
            theme_buckets[theme_id]["category"] = cat
            theme_buckets[theme_id]["desc"] = desc
            theme_buckets[theme_id]["paper_ids"].add(pid)
            theme_buckets[theme_id]["years"].append(year)
            if quote and len(theme_buckets[theme_id]["quotes"]) < 4:
                theme_buckets[theme_id]["quotes"].append(quote)

    themes: List[LimitationTheme] = []
    for tid, b in theme_buckets.items():
        if not b["paper_ids"]:
            continue

        years = b["years"]
        min_y = min(years) if years else 2026
        max_y = max(years) if years else 2026

        themes.append(LimitationTheme(
            theme_id=tid,
            name=b["name"],
            category=b["category"],
            description=b["desc"],
            total_papers=len(b["paper_ids"]),
            first_year=min_y,
            latest_year=max_y,
            lifecycle_status="UNADDRESSED",  # will be assigned by classifier
            paper_ids=list(b["paper_ids"]),
            key_quotes=b["quotes"]
        ))

    # Sort themes by total papers affected
    themes.sort(key=lambda x: x.total_papers, reverse=True)
    logger.info(f"Clustered {sum(len(b['paper_ids']) for b in theme_buckets.values())} limitation instances into {len(themes)} themes.")
    return themes
