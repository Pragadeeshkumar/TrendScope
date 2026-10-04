"""
Entity Consolidator & Noise Filter for Stage 5 Trend Analysis.
Cleans raw extracted tokens, filters out equation/step artifacts, and groups entities into canonical scientific families.
"""

import re
import logging
from typing import Optional, Tuple, Dict, List

logger = logging.getLogger("trendscope.trends.consolidator")

# Common noise patterns to reject
NOISE_PATTERNS = [
    r'(?:step\s+[ivxldcm\d]+|eq\.?\s*\d+|section\s*[\d\.]+|table\s*\d+|fig\.?\s*\d+|figure\s*\d+|algorithm\s*\d+|appendix\s*[a-z\d]+)',
    r'(?:arxiv[:\s]*[\d\.]+(?:v\d+)?|w\d+|s\d+|p\d+|ref\s*\d+)',
    r'(?:^ss[_\s]*[a-f0-9]+|^doi[_\s]*[\d\w\.\-]+)',
    r'^(?:pandas|scipy|numpy|matplotlib|scikit-learn|sklearn|pytorch|torch|tensorflow|keras|seaborn)$',
    r'^(?:proposed\s+backbone|prompted\s+backbone|backbone\s+network|baseline\s+model|our\s+approach|the\s+model|method\s*\d+|model\s*\d+)$',
    r'^(?:standard\s+benchmark|benchmark\s+dataset|custom\s+dataset|dataset|eval\s+dataset|various\s+datasets|real-world\s+data|our\s+dataset|benchmark)$',
    r'^[a-z0-9_\-\.]{1,2}$',
    r'^(?:none|n/a|null|unknown|unspecified|not\s+applicable|overall|total|paper|all|various)$',
    r'(?:prisma|prisma-scr|scoping\s+review|systematic\s+review|narrative\s+review|pcc\s+framework|peter\s+framework|literature\s+review|cochrane\s+guidelines)',
    r'(?:standing\s+review\s+group|review\s+group|thematic\s+analysis|contextual\s+inquiry|ethnographic|semi-structured\s+interview|survey\s+methodology)',
    r'^(?:machine\s+learning|deep\s+learning|artificial\s+intelligence|ai|ml|dl|algorithm|model|approach|framework|methodology|technique|self-attention|attention)$',
    r'(?:classification\s+structure|maturity\s+taxonomy|framework\s+for\s+understanding|morbidity\s+and\s+mortality)'
]


# Canonical scientific method families & regex patterns
CANONICAL_METHOD_FAMILIES = [
    {
        "family": "Classical Statistical & Machine Learning Baselines",
        "category": "Classical Baselines",
        "patterns": [r'random\s+forest', r'logistic\s+regression', r'xgboost', r'\bsvm\b', r'support\s+vector', r'decision\s+tree', r'linear\s+regression', r'naive\s+bayes', r'\bknn\b', r'k-nearest', r'\bcnn\b', r'convolutional', r'resnet', r'gradient\s+boosting'],
        "replaces": "Manual Clinical Rules"
    },
    {
        "family": "Clinical Decision Support Systems (CDSS) & Rule Engines",
        "category": "Clinical Informatics",
        "patterns": [r'\bcdss\b', r'clinical\s+decision\s+support', r'diagnostic\s+decision\s+support', r'triage\s+system', r'clinical\s+workflow\s+engine', r'order\s+set'],
        "replaces": "Static Manual Chart Reviews"
    },
    {
        "family": "Medical Knowledge Graphs & Ontological Reasoning",
        "category": "Neuro-Symbolic & Grounded AI",
        "patterns": [r'knowledge\s+graph', r'\bumls\b', r'snomed', r'fhir', r'hl7', r'medical\s+ontology', r'neuro-symbolic', r'meta-predicate'],
        "replaces": "Unstructured Raw Text Heuristics"
    },
    {
        "family": "Clinical Retrieval-Augmented Generation (Medical RAG)",
        "category": "Knowledge Grounding & Retrieval",
        "patterns": [r'\brag\b', r'retrieval-augmented', r'dense\s+retrieval', r'pubmedbert', r'biobert', r'evidence-grounded', r'clinical\s+retrieval', r'vector\s+search'],
        "replaces": "Closed-Book Static LLM Hallucinations"
    },
    {
        "family": "Privacy-Preserving Federated Learning for Healthcare",
        "category": "Distributed & Secure AI",
        "patterns": [r'federated\s+learning', r'\bfl\b', r'simulated\s+federated', r'differential\s+privacy', r'split\s+learning', r'secure\s+enclave', r'hipaa'],
        "replaces": "Centralized Cross-Hospital Data Sharing"
    },
    {
        "family": "Direct Preference Optimization (DPO)",
        "category": "Alignment & Preference Tuning",
        "patterns": [r'\bdpo\b', r'direct\s+preference\s+optimization', r'dpo\s+alignment', r'preference\s+tuning', r'kto\b', r'orpo\b', r'simpo\b'],
        "replaces": "PPO / Complex Reward Models"
    },
    {
        "family": "Reinforcement Learning & Policy Optimization (RLHF / PPO / GRPO)",
        "category": "Reinforcement Learning",
        "patterns": [r'\brlhf\b', r'\bppo\b', r'\bgrpo\b', r'policy\s+gradient', r'q-learning', r'actor-critic', r'reward\s+model(?:ing)?', r'policy\s+optimization', r'self-play\s+rl', r'proximal\s+policy'],
        "replaces": "Supervised Fine-Tuning Alone"
    },
    {
        "family": "Hierarchical Multi-Agent Systems & Clinical ReAct",
        "category": "Agentic Reasoning & Tool Use",
        "patterns": [r'multi-agent', r'hierarchical\s+agent', r'react\s+framework', r'react\s+prompting', r'agentic\s+workflow', r'agent\s+collaboration', r'planner-actor', r'agent\s+consensus', r'healthagent', r'medagent', r'tool\s+calling'],
        "replaces": "Single-Prompt Chain-of-Thought"
    },
    {
        "family": "Mixture-of-Experts (MoE) & Sparse Routing",
        "category": "Efficient Foundation Architectures",
        "patterns": [r'mixture\s+of\s+experts', r'\bmoe\b', r'sparse\s+moe', r'expert\s+routing', r'top-k\s+routing', r'switch\s+transformer'],
        "replaces": "Dense Monolithic Transformers"
    },
    {
        "family": "Linear State-Space Models (Mamba / SSM)",
        "category": "Efficient Sequence Modeling",
        "patterns": [r'\bmamba\b', r'state-space\s+model', r'\bssm\b', r'linear\s+attention', r'selective\s+state\s+space', r's4\s+model', r'recurrent\s+state\s+space'],
        "replaces": "Full Quadratic Self-Attention"
    },
    {
        "family": "Transformer-based Foundation Architectures",
        "category": "Foundation Models",
        "patterns": [r'\btransformer\b', r'\bvit\b', r'vision\s+transformer', r'swin\s+transformer', r'attention\s+mechanism', r'decoder-only\s+llm', r'transformer\s+backbone', r'\bbert\b', r'\bllama\b', r'\bgpt-4\b', r'\bgpt-3\.?5\b'],
        "replaces": "Recurrent (LSTM/GRU) & Classic CNNs"
    },
    {
        "family": "Vision-Language & Multimodal Tokenizers (VLM)",
        "category": "Multimodal AI",
        "patterns": [r'vision-language', r'\bvlm\b', r'multimodal\s+transformer', r'visual\s+tokenizer', r'cross-modal\s+attention', r'patch\s+projection', r'\bclip\b', r'llava', r'flamingo', r'contrastive\s+language-image', r'multimodal\s+fusion'],
        "replaces": "Separate Disconnected CNN + LLM Pipelines"
    },
    {
        "family": "Parameter-Efficient Fine-Tuning (PEFT / LoRA)",
        "category": "Model Adaptation & Efficiency",
        "patterns": [r'\blora\b', r'\bqlora\b', r'\bpeft\b', r'low-rank\s+adaptation', r'adapter\s+tuning', r'prefix\s+tuning', r'prompt\s+tuning'],
        "replaces": "Full-Parameter Fine-Tuning"
    },
    {
        "family": "Diffusion & Flow-Matching Generative Models",
        "category": "Generative Modeling",
        "patterns": [r'diffusion\s+model', r'\bddpm\b', r'\bddim\b', r'latent\s+diffusion', r'score-based\s+model', r'flow\s+matching', r'stable\s+diffusion', r'denoising\s+diffusion'],
        "replaces": "Generative Adversarial Networks (GANs)"
    },
    {
        "family": "Quantization, Distillation & Pruning Acceleration",
        "category": "Edge & System Efficiency",
        "patterns": [r'quantiz(?:ation|ed)', r'int[48]\s+quantization', r'\bpruning\b', r'weight\s+compression', r'npu\s+accelerator', r'knowledge\s+distillation', r'model\s+distillation', r'awq\b', r'gptq\b'],
        "replaces": "Uncompressed FP32/FP16 Inference"
    },
    {
        "family": "Process-Level Trajectory Verification & Guardrails",
        "category": "Trustworthy & Verifiable AI",
        "patterns": [r'guardrail', r'verifier', r'process\s+reward', r'\bprm\b', r'trajectory\s+verification', r'safety\s+routing', r'uncertainty\s+estimation', r'self-modeling', r'critic\s+loop', r'self-refine', r'self-consistency', r'auditable'],
        "replaces": "Static Post-Hoc Output Filtering"
    }
]

# Canonical dataset groups
CANONICAL_DATASET_FAMILIES = [
    {
        "name": "MedQA / MedMCQA / USMLE Medical Exams",
        "modality": "Clinical Question Answering & Medical Licensing",
        "patterns": [r'medqa', r'medmcqa', r'usmle', r'pubmedqa', r'mubench', r'healthqa', r'bioasq']
    },
    {
        "name": "MIMIC-III / MIMIC-IV / eICU Critical Care Records",
        "modality": "Longitudinal Electronic Health Records (EHR)",
        "patterns": [r'mimic', r'eicu', r'physionet', r'clinical\s+records', r'ehr\s+dataset']
    },
    {
        "name": "OSWorld / WebArena / AgentBoard Environments",
        "modality": "Interactive Web/OS Simulation",
        "patterns": [r'osworld', r'webarena', r'agentboard', r'toolbench', r'toolsandbox', r'scienceworld', r'planbench', r'mind2web', r'intercode', r'healthagentbench', r'patientagentbench']
    },
    {
        "name": "Synapse / BraTS / ChestX-ray Medical Imaging",
        "modality": "Volumetric 3D Medical Scans & Radiography",
        "patterns": [r'synapse', r'brats', r'acdc', r'isic', r'chestx-ray', r'mimic-cxr', r'luna16', r'refuge', r'fundus', r'echocardiograph']
    },
    {
        "name": "GSM8K / MATH Synthetic Reasoning",
        "modality": "Mathematical & Multi-step Logic",
        "patterns": [r'gsm8k', r'\bmath\b', r'svamp', r'asdiv', r'mathqa', r'olympiadbench', r'minerva\s+math', r'aime\b']
    },
    {
        "name": "HumanEval / MBPP Code Benchmarks",
        "modality": "Software Engineering & Python Code",
        "patterns": [r'humaneval', r'mbpp', r'swe-bench', r'codeforces', r'evalplus', r'apps\s+benchmark', r'conala']
    },
    {
        "name": "MMLU / ARC Knowledge Benchmarks",
        "modality": "Multi-Task Academic Knowledge",
        "patterns": [r'mmlu', r'arc-c', r'arc-e', r'hellaswag', r'triviaqa', r'natural\s+questions', r'winogrande', r'openbookqa', r'agieval', r'gpqa']
    },
    {
        "name": "ImageEval / VQA Multimodal Benchmarks",
        "modality": "Multimodal Vision-Language",
        "patterns": [r'imageeval', r'vqa', r'gqa', r'ok-vqa', r'coco\s+caption', r'textvqa', r'mmbench', r'mme\b', r'pope\b', r'seed-bench']
    }
]



def is_noise_entity(raw_name: str) -> bool:
    """Checks if extracted entity name is OCR noise, structural boilerplate, or citation artifact."""
    if not raw_name or len(raw_name.strip()) < 3:
        return True
    clean = raw_name.strip().lower()
    if "arxiv" in clean:
        return True
    for pat in NOISE_PATTERNS:
        if re.search(pat, clean):
            return True
    return False



def consolidate_method_name(raw_name: str, fallback_type: str = "model") -> Optional[Tuple[str, str, str, str]]:
    """
    Consolidates raw method name into (Canonical Name, Family Name, Category, Replaces Target).
    Returns None if the entity is noise.
    """
    if is_noise_entity(raw_name):
        return None

    clean = raw_name.strip().lower()

    # Match against known canonical families
    for fam in CANONICAL_METHOD_FAMILIES:
        for pat in fam["patterns"]:
            if re.search(pat, clean):
                return fam["family"], fam["family"], fam["category"], fam["replaces"]

    # If meaningful scientific method not in pre-mapped list, title-case and return as domain-specific
    clean_title = raw_name.strip().title()
    if len(clean_title) > 40:
        clean_title = clean_title[:40] + "..."
    return clean_title, "Domain-Specific Architecture", "Domain Methodology", "Previous Baseline"


def consolidate_dataset_name(raw_name: str, fallback_modality: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """
    Consolidates raw dataset name into (Canonical Name, Modality).
    Returns None if the entity is noise.
    """
    if is_noise_entity(raw_name):
        return None

    clean = raw_name.strip().lower()

    # Match against known benchmark families
    for fam in CANONICAL_DATASET_FAMILIES:
        for pat in fam["patterns"]:
            if re.search(pat, clean):
                return fam["name"], fam["modality"]

    clean_title = raw_name.strip().title()
    if len(clean_title) > 35:
        clean_title = clean_title[:35] + "..."
    modality = fallback_modality or "Domain Empirical Dataset"
    return clean_title, modality

