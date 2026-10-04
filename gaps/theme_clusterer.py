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
        "keywords": [r'memory', r'compute', r'computational', r'gpu', r'quadratic', r'scaling', r'latency', r'inference speed', r'resource', r'vram', r'throughput'],
        "desc": "Challenges regarding exponential compute demands, GPU VRAM constraints on large models, and high latency multi-agent inference.",
        "frontier": "Explore sub-quadratic linear attention, State Space Models (Mamba), dynamic early-exit token pruning, and 4-bit activation quantization to preserve multi-step reasoning fidelity without exponential latency scaling."
    },
    {
        "id": "theme_generalization_robustness",
        "name": "Out-of-Distribution Generalization and Cross-Domain Robustness",
        "category": "generalization",
        "keywords": [r'generalization', r'out-of-distribution', r'ood', r'domain shift', r'robustness', r'cross-domain', r'unseen', r'external validation', r'cohort', r'site-to-site'],
        "desc": "Performance degradation when models encounter novel environments, unseen scanner/sensor distributions, or external multi-center cohorts.",
        "frontier": "Formulate test-time self-supervised adaptation, invariant representation learning, and domain-adversarial causal feature selection to ensure stable zero-shot transfer across independent institutions."
    },
    {
        "id": "theme_data_annotation",
        "name": "Reliance on Large-Scale Supervised Annotations and Pretraining",
        "category": "data_scarcity",
        "keywords": [r'annotation', r'labeled data', r'scarcity', r'pretraining', r'few samples', r'ground truth', r'labeling cost', r'sparse labels', r'small sample'],
        "desc": "Heavy dependence on expensive manual expert annotations and curated pretraining datasets.",
        "frontier": "Develop semi-supervised consistency regularization, high-fidelity synthetic data augmentation via latent diffusion, and self-rewarding iterative bootstrapping to train robust models with sparse labeled samples."
    },
    {
        "id": "theme_safety_alignment",
        "name": "Safety Guardrails, Privacy Protections, and Alignment Risks",
        "category": "safety_alignment",
        "keywords": [r'safety', r'alignment', r'jailbreak', r'adversarial', r'guardrail', r'risk', r'harmful', r'misalignment', r'collusion', r'privacy', r'hipaa', r'leakage', r'membership inference'],
        "desc": "Vulnerabilities to adversarial prompt injection, privacy leakages in sensitive patient/enterprise domains, and uncalibrated multi-agent collusion.",
        "frontier": "Implement differential privacy during parameter-efficient fine-tuning, formal verification for multi-agent arbitration protocols, and sandboxed symbolic guardrails."
    },
    {
        "id": "theme_evaluation_benchmarking",
        "name": "Process-Level Evaluation Gaps and Synthetic Benchmark Bias",
        "category": "evaluation_gap",
        "keywords": [r'benchmark', r'evaluation', r'metric', r'synthetic', r'proxy', r'shortcut', r'reward hacking', r'fidelity', r'static dataset', r'clinical endpoint'],
        "desc": "Limitations of static benchmark metrics (e.g. standard accuracy/BLEU) that fail to evaluate multi-step reasoning trajectories or real-world outcomes.",
        "frontier": "Construct dynamic interactive benchmark suites, step-by-step reasoning trajectory verifiers, and human-in-the-loop task simulation environments."
    },
    {
        "id": "theme_interpretability_explainability",
        "name": "Black-Box Decision Making and Uncertainty Quantification",
        "category": "interpretability",
        "keywords": [r'interpretability', r'black-box', r'explainable', r'uncertainty', r'hallucination', r'calibration', r'attribution', r'trust', r'explainability', r'confidence', r'probabilistic'],
        "desc": "Lack of transparent explanations for intermediate agent reasoning and unreliable uncertainty calibration on critical decision boundaries.",
        "frontier": "Integrate conformal prediction for rigorous uncertainty bounds, concept bottleneck layers, and mechanistic interpretability probes for faithful attribution."
    },
    {
        "id": "theme_clinical_workflow",
        "name": "Real-World Workflow Integration and Translation Bottlenecks",
        "category": "clinical_translation",
        "keywords": [r'clinical workflow', r'ehr', r'electronic health', r'hospital', r'physician', r'deployment', r'regulatory', r'fda', r'prospective', r'bedside', r'clinical trial', r'real-world'],
        "desc": "Friction in integrating AI assistance into live operational workflows, heterogeneous enterprise infrastructure, and prospective validation trials.",
        "frontier": "Standardize FHIR/RESTful streaming connectors, prospective shadow-mode trial validation, and adaptive physician-in-the-loop triage architectures."
    },
    {
        "id": "theme_multimodal_fusion",
        "name": "Cross-Modal Alignment and Heterogeneous Data Integration",
        "category": "multimodal_fusion",
        "keywords": [r'multimodal', r'cross-modal', r'heterogeneous', r'fusion', r'alignment', r'missing modality', r'multi-omics', r'imaging and text', r'tabular and image'],
        "desc": "Challenges in fusing disparate modalities (e.g., text, 3D imaging, time-series, genomics) with missing or asynchronous data channels.",
        "frontier": "Design cross-attention hypernetworks with masked modality reconstruction loss and unified joint embedding spaces resilient to missing inputs."
    },
    {
        "id": "theme_sample_efficiency",
        "name": "Class Imbalance and Long-Tail Subgroup Representation",
        "category": "sample_efficiency",
        "keywords": [r'imbalance', r'long-tail', r'rare', r'skewed', r'subgroup', r'underrepresented', r'demographic bias', r'fairness'],
        "desc": "Vulnerability to extreme class imbalance and poor performance on rare pathologies or underrepresented demographic subgroups.",
        "frontier": "Deploy focal reweighting with meta-learned sample difficulty weighting and balanced generative oversampling on long-tail instances."
    }
]


def match_limitation_to_theme(lim_text: str) -> Tuple[str, str, str, str, str]:
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
        return best_match["id"], best_match["name"], best_match["category"], best_match["desc"], best_match.get("frontier", "")

    # Dynamic fallback based on syntactic focus
    if any(w in text_lower for w in ["cost", "speed", "time", "complex", "param"]):
        return "theme_compute_scaling", "High Computational Complexity and Memory Scaling", "computational_cost", "Challenges regarding compute demands and latency constraints.", "Explore sub-quadratic linear attention and quantization."
    if any(w in text_lower for w in ["data", "sample", "size", "patient", "cohort", "limit"]):
        return "theme_data_annotation", "Reliance on Large-Scale Supervised Annotations and Pretraining", "data_scarcity", "Sample size constraints and dataset limitations.", "Leverage self-supervised pretraining and synthetic data augmentation."

    return "theme_general_empirical", "Empirical System Trade-offs and Domain Bottlenecks", "general", "Empirical design trade-offs and specialized system bottlenecks identified in domain literature.", "Conduct comparative ablation studies across external benchmark datasets."


def cluster_limitation_themes(papers: List[Dict[str, Any]]) -> List[LimitationTheme]:
    """
    Extracts and groups all limitation instances from papers into canonical limitation themes,
    associating affected methods, benchmarks, and actionable research vectors.
    """
    theme_buckets = defaultdict(lambda: {
        "name": "",
        "category": "",
        "desc": "",
        "frontier": "",
        "instances": [],
        "paper_ids": set(),
        "years": [],
        "quotes": [],
        "methods": set(),
        "benchmarks": set()
    })

    for p in papers:
        pid = p.get("paper_id", "unknown")
        title = p.get("title", "Unknown")
        year = p.get("publication_year") or 2026

        p_methods = [m.get("name") if isinstance(m, dict) else str(m) for m in p.get("methods", [])]
        p_datasets = [d.get("name") if isinstance(d, dict) else str(d) for d in p.get("datasets", [])]

        for lim in p.get("limitations", []):
            text = lim.get("text", "").strip() if isinstance(lim, dict) else str(lim).strip()
            if not text:
                continue

            theme_id, name, cat, desc, frontier = match_limitation_to_theme(text)
            
            prov = lim.get("provenance", {}) if isinstance(lim, dict) else {}
            quote = prov.get("quote") or text

            theme_buckets[theme_id]["name"] = name
            theme_buckets[theme_id]["category"] = cat
            theme_buckets[theme_id]["desc"] = desc
            theme_buckets[theme_id]["frontier"] = frontier
            theme_buckets[theme_id]["paper_ids"].add(pid)
            theme_buckets[theme_id]["years"].append(year)
            for m in p_methods:
                if m:
                    theme_buckets[theme_id]["methods"].add(m)
            for d in p_datasets:
                if d:
                    theme_buckets[theme_id]["benchmarks"].add(d)
            if quote and len(theme_buckets[theme_id]["quotes"]) < 5:
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
            lifecycle_status="UNADDRESSED",  # will be refined by classifier
            paper_ids=list(b["paper_ids"]),
            key_quotes=b["quotes"],
            actionable_frontier=b["frontier"],
            affected_methods=list(b["methods"])[:6],
            affected_benchmarks=list(b["benchmarks"])[:4]
        ))

    # Sort themes by total papers affected
    themes.sort(key=lambda x: x.total_papers, reverse=True)
    logger.info(f"Clustered {sum(len(b['paper_ids']) for b in theme_buckets.values())} limitation instances into {len(themes)} themes.")
    return themes
