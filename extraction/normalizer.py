"""
Canonical Normalizer for scientific concepts, method architectures, and dataset names.
Standardizes variations (e.g. 'ViT' -> 'Vision Transformer', 'LLM' -> 'Large Language Model')
and strictly filters out generic nouns, stop words, and discourse artifacts.
"""

import re
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger("trendscope.extraction.normalizer")

# Generic non-specific nouns that must NEVER be extracted as standalone methods or datasets
GENERIC_NOUN_BLACKLIST: Set[str] = {
    "approach", "method", "methods", "methodology", "framework", "pipeline", "system", 
    "model", "models", "architecture", "architectures", "algorithm", "algorithms", 
    "technique", "techniques", "strategy", "strategies", "scheme", "schemes", 
    "baseline", "baselines", "component", "components", "module", "modules", 
    "tool", "tools", "protocol", "protocols", "mechanism", "mechanisms", 
    "process", "processes", "procedure", "procedures", "concept", "concepts",
    "dataset", "datasets", "benchmark", "benchmarks", "corpus", "corpora", 
    "data", "database", "databases", "table", "tables", "figure", "figures", 
    "section", "sections", "paper", "papers", "study", "studies", "author", 
    "authors", "work", "works", "result", "results", "experiment", "experiments",
    "evaluation", "evaluations", "analysis", "analyses", "finding", "findings",
    "proposal", "proposals", "solution", "solutions", "setup", "setups",
    "however", "moreover", "furthermore", "therefore", "thus", "overall", "such",
    "each", "both", "this", "that", "these", "those", "their", "our", "its"
}

# Multi-Domain Canonical Aliases Map for Methods & Architectures
METHOD_CANONICAL_MAP: Dict[str, str] = {
    # Large Language Models & Agentic Reasoning
    r'\b(?:llms?|large\s+language\s+models?)\b': "Large Language Model",
    r'\b(?:clinical\s+llms?|clinical\s+large\s+language\s+models?)\b': "Clinical Large Language Model",
    r'\b(?:chain[\-\s]+of[\-\s]+thoughts?|cot\s+reasoning|cot\s+prompting)\b': "Chain-of-Thought (CoT)",
    r'\b(?:tree[\-\s]+of[\-\s]+thoughts?|tot)\b': "Tree-of-Thought (ToT)",
    r'\b(?:retrieval[\-\s]+augmented\s+generation|rag)\b': "Retrieval-Augmented Generation (RAG)",
    r'\b(?:lora|low[\-\s]+rank\s+adaptation)\b': "LoRA",
    r'\b(?:qlora)\b': "QLoRA",
    r'\b(?:rlhf|reinforcement\s+learning\s+from\s+human\s+feedback)\b': "RLHF",
    r'\b(?:dpo|direct\s+preference\s+optimization)\b': "Direct Preference Optimization (DPO)",
    r'\b(?:multi[\-\s]+agent(?:ic)?\s+(?:system|framework|collaboration)?)\b': "Multi-Agent AI Framework",
    r'\b(?:autonomous\s+(?:cyber\s+)?defense\s+(?:agent|system)?)\b': "Autonomous Cyber Defense",
    r'\b(?:sandboxed\s+terminal\s+(?:execution|environment)?)\b': "Sandboxed Terminal Execution",
    r'\b(?:prompt\s+engineering|in[\-\s]+context\s+learning|icl)\b': "In-Context Learning",
    
    # Transformers & Attention Backbones
    r'\b(?:vit|vision\s+transformers?(?:\s+architecture)?)\b': "Vision Transformer",
    r'\b(?:swin(?:\s+transformer|\-t|\-b|\-l|\-unet)?)\b': "Swin Transformer",
    r'\b(?:transunet|trans\-unet)\b': "TransUNet",
    r'\b(?:segformer|seg\-former)\b': "SegFormer",
    r'\b(?:bert|bert[\-\s]+base|bert[\-\s]+large)\b': "BERT",
    r'\b(?:roberta)\b': "RoBERTa",
    r'\b(?:deberta)\b': "DeBERTa",
    r'\b(?:scibert)\b': "SciBERT",
    r'\b(?:biobert)\b': "BioBERT",
    r'\b(?:gpt[\-\s]*[345]|chatgpt|gpt[\-\s]*4o?)\b': "GPT Architecture",
    r'\b(?:llama(?:\s*[234])?|llama[\-\s]*3(?:\.\d)?)\b': "Llama Architecture",
    r'\b(?:mistral|mixtral(?:\s*8x7b)?)\b': "Mistral Architecture",
    r'\b(?:qwen(?:\s*[12])?(?:\.\d)?)\b': "Qwen Architecture",
    r'\b(?:transformers?(?:\s+model|\s+backbone|\s+architecture)?)\b': "Transformer",
    r'\b(?:cross[\-\s]+attention)\b': "Cross-Attention",
    r'\b(?:self[\-\s]+attention)\b': "Self-Attention",
    r'\b(?:mamba|state[\-\s]+space\s+model|ssm)\b': "State Space Model (Mamba)",
    
    # Convolutional & Segmentation Architectures
    r'\b(?:cnns?|convolutional\s+neural\s+networks?)\b': "Convolutional Neural Network",
    r'\b(?:u\-?nets?|classic\s+u\-?net)\b': "UNet",
    r'\b(?:nnu\-?net|nn\s*u\-?net)\b': "nnU-Net",
    r'\b(?:res\-?nets?(?:\-?\d+)?|residual\s+networks?)\b': "ResNet",
    r'\b(?:v\-?nets?)\b': "V-Net",
    r'\b(?:densenet(?:\-?\d+)?)\b': "DenseNet",
    r'\b(?:efficientnet(?:\-?b\d+)?)\b': "EfficientNet",
    r'\b(?:mobilenet(?:\-?v\d+)?)\b': "MobileNet",
    r'\b(?:yolo(?:\s*v[1-9])?)\b': "YOLO",
    r'\b(?:faster\s+r[\-\s]*cnn)\b': "Faster R-CNN",
    r'\b(?:mask\s+r[\-\s]*cnn)\b': "Mask R-CNN",

    # Graph Neural Networks
    r'\b(?:gnns?|graph\s+neural\s+networks?)\b': "Graph Neural Network",
    r'\b(?:gcns?|graph\s+convolutional\s+networks?)\b': "Graph Convolutional Network",
    r'\b(?:gats?|graph\s+attention\s+networks?)\b': "Graph Attention Network",
    r'\b(?:graphsage)\b': "GraphSAGE",
    
    # Diffusion & Generative Models
    r'\b(?:diffusion\s+models?|ddpm|ddim)\b': "Diffusion Model",
    r'\b(?:stable\s+diffusion|latent\s+diffusion(?:\s+model)?)\b': "Latent Diffusion Model",
    r'\b(?:gans?|generative\s+adversarial\s+networks?)\b': "GAN",
    r'\b(?:vaes?|variational\s+autoencoders?)\b': "Variational Autoencoder (VAE)",
    
    # Reinforcement Learning & Optimization
    r'\b(?:reinforcement\s+learning|deep\s+rl)\b': "Reinforcement Learning",
    r'\b(?:ppo|proximal\s+policy\s+optimization)\b': "PPO",
    r'\b(?:dqn|deep\s+q[\-\s]+network)\b': "Deep Q-Network (DQN)",
    r'\b(?:sac|soft\s+actor[\-\s]+critic)\b': "Soft Actor-Critic (SAC)",
    
    # Classical Machine Learning & Tree-Based
    r'\b(?:random\s+forests?)\b': "Random Forest",
    r'\b(?:decision\s+trees?)\b': "Decision Tree",
    r'\b(?:xgboost|extreme\s+gradient\s+boosting)\b': "XGBoost",
    r'\b(?:lightgbm)\b': "LightGBM",
    r'\b(?:catboost)\b': "CatBoost",
    r'\b(?:svms?|support\s+vector\s+machines?)\b': "Support Vector Machine",
    r'\b(?:logistic\s+regression)\b': "Logistic Regression",
    r'\b(?:k[\-\s]+means(?:\s+clustering)?)\b': "K-Means Clustering",
    
    # Loss functions & Metrics
    r'\b(?:dice\s+loss)\b': "Dice Loss",
    r'\b(?:cross[\-\s]*entropy\s+loss|ce\s+loss)\b': "Cross-Entropy Loss",
    r'\b(?:focal\s+loss)\b': "Focal Loss",
    r'\b(?:contrastive\s+loss)\b': "Contrastive Loss"
}

# Multi-Domain Canonical Aliases Map for Datasets & Benchmarks
DATASET_CANONICAL_MAP: Dict[str, str] = {
    # Cybersecurity Benchmarks
    r'\b(?:ransomware[\-\s]*2024(?:\s+dataset)?)\b': "Ransomware Dataset 2024",
    r'\b(?:incident[\-\s]*2026alpha)\b': "Incident-2026Alpha",
    r'\b(?:cyberwheel)\b': "Cyberwheel",
    r'\b(?:cicmalmem[\-\s]*2022)\b': "Cicmalmem-2022",
    r'\b(?:kdd[\-\s]*cup(?:\s*99)?|nsl[\-\s]*kdd)\b': "NSL-KDD",
    r'\b(?:cic[\-\s]*ids[\-\s]*2017|cic[\-\s]*ids[\-\s]*2018)\b': "CIC-IDS Dataset",
    r'\b(?:unsw[\-\s]*nb15)\b': "UNSW-NB15",
    r'\b(?:cti[\-\s]*bench|cyber\s+threat\s+intelligence\s+benchmark)\b': "CTI Benchmark",
    
    # General AI & Vision Benchmarks
    r'\b(?:imagenet(?:\-?1k|\-?21k)?)\b': "ImageNet",
    r'\b(?:coco|ms[\-\s]*coco)\b': "MS COCO",
    r'\b(?:pascal\s*voc|voc\s*2012)\b': "PASCAL VOC",
    r'\b(?:cifar[\-\s]*(?:10|100))\b': "CIFAR",
    r'\b(?:mnist|fashion[\-\s]*mnist)\b': "MNIST",
    
    # NLP & LLM Benchmarks
    r'\b(?:mmlu|massive\s+multitask\s+language\s+understanding)\b': "MMLU",
    r'\b(?:gsm8k)\b': "GSM8K",
    r'\b(?:human_?eval|humaneval)\b': "HumanEval",
    r'\b(?:squad(?:\s*v?2\.0)?)\b': "SQuAD",
    r'\b(?:glue|superglue)\b': "GLUE Benchmark",
    r'\b(?:swe[\-\s]*bench)\b': "SWE-bench",
    
    # Medical & Scientific Datasets
    r'\b(?:synapse(?:\s+multi\-organ\s+ct)?)\b': "Synapse Multi-Organ CT",
    r'\b(?:acdc(?:\s+cardiac|\s+dataset|\s+mri)?)\b': "ACDC Cardiac MRI",
    r'\b(?:brats(?:\s*2021|\s*2020|\s*2019|\s*2018)?)\b': "BraTS 2021",
    r'\b(?:isic(?:\s*2018|\s*2019|\s*2020)?)\b': "ISIC Skin Lesion",
    r'\b(?:luna16|luna\s*16)\b': "LUNA16",
    r'\b(?:chexpert)\b': "CheXpert",
    r'\b(?:mimic(?:\-cxr|\-iv|\-iii)?)\b': "MIMIC Database",
    r'\b(?:medqa|usmle)\b': "MedQA Benchmark"
}


def is_generic_noun(text: str) -> bool:
    """
    Returns True if the candidate name is purely a generic, non-specific scientific noun.
    """
    if not text:
        return True
    
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', text).strip().lower()
    
    # Standalone single word matches blacklist
    if cleaned in GENERIC_NOUN_BLACKLIST:
        return True
    
    # Too short or just numbers/symbols
    if len(cleaned) < 3 or cleaned.isdigit():
        return True
    
    # Common generic pairs: "the approach", "our method", "a model"
    if cleaned in {
        "the model", "the method", "the approach", "the framework", "the system",
        "our model", "our method", "our approach", "our framework", "our system",
        "proposed model", "proposed method", "proposed approach", "proposed framework"
    }:
        return True
        
    return False


def normalize_method_name(raw_name: str) -> str:
    """
    Normalizes a raw method name to its canonical standardized representation.
    Filters out generic nouns and standardizes acronyms/variations.
    """
    if not raw_name or is_generic_noun(raw_name):
        return ""
    
    name_clean = raw_name.strip()
    
    # Check explicit canonical mapping
    for pattern, canonical in METHOD_CANONICAL_MAP.items():
        if re.search(pattern, name_clean, flags=re.IGNORECASE):
            return canonical
            
    # Clean leading/trailing quotes and markdown
    name_clean = re.sub(r'^[\"`\']+|[\"`\']+$', '', name_clean).strip()
    
    # Title-case if short, otherwise return clean string
    return name_clean.title() if len(name_clean) < 35 else name_clean


def normalize_dataset_name(raw_name: str) -> str:
    """
    Normalizes a raw dataset name to its canonical standardized representation.
    Filters out generic nouns and standardizes benchmark names.
    """
    if not raw_name or is_generic_noun(raw_name):
        return ""
        
    name_clean = raw_name.strip()
    
    # Check explicit canonical mapping
    for pattern, canonical in DATASET_CANONICAL_MAP.items():
        if re.search(pattern, name_clean, flags=re.IGNORECASE):
            return canonical
            
    name_clean = re.sub(r'^[\"`\']+|[\"`\']+$', '', name_clean).strip()
    return name_clean.title() if len(name_clean) < 35 else name_clean
