"""
Canonical Normalizer for scientific concepts, method architectures, and dataset names.
Standardizes variations (e.g. 'ViT' -> 'Vision Transformer', 'Synapse multi-organ CT' -> 'Synapse Multi-Organ CT').
"""

import re
import logging
from typing import Dict, Optional

logger = logging.getLogger("trendscope.extraction.normalizer")

# Canonical aliases map for methods
METHOD_CANONICAL_MAP: Dict[str, str] = {
    # Vision Transformers & Attention
    r'\b(?:vit|vision\s+transformer(?:\s+architecture)?)\b': "Vision Transformer",
    r'\b(?:swin(?:\s+transformer|\-t|\-b|\-l|\-unet)?)\b': "Swin Transformer",
    r'\b(?:transunet|trans\-unet)\b': "TransUNet",
    r'\b(?:segformer|seg\-former)\b': "SegFormer",
    r'\b(?:transformer(?:\s+model|\s+backbone|\s+architecture)?)\b': "Transformer",
    r'\b(?:cross\-attention|cross\s+attention)\b': "Cross-Attention",
    r'\b(?:self\-attention|self\s+attention)\b': "Self-Attention",
    r'\b(?:mamba|state\-space\s+model|ssm)\b': "State Space Model (Mamba)",
    
    # Convolutional & Classic UNet
    r'\b(?:u\-?net|classic\s+u\-?net)\b': "UNet",
    r'\b(?:nnunet|nn\s*u\-?net)\b': "nnU-Net",
    r'\b(?:res\-?net|residual\s+network)\b': "ResNet",
    r'\b(?:v\-?net)\b': "V-Net",
    r'\b(?:cnn|convolutional\s+neural\s+network)\b': "CNN",
    
    # Diffusion & Generative
    r'\b(?:diffusion\s+model(?:s)?|ddpm|ddim)\b': "Diffusion Model",
    r'\b(?:gan|generative\s+adversarial\s+network)\b': "GAN",
    
    # Loss functions
    r'\b(?:dice\s+loss)\b': "Dice Loss",
    r'\b(?:cross\-?entropy\s+loss|ce\s+loss)\b': "Cross-Entropy Loss",
    r'\b(?:focal\s+loss)\b': "Focal Loss"
}

# Canonical aliases map for datasets
DATASET_CANONICAL_MAP: Dict[str, str] = {
    r'\b(?:synapse(?:\s+multi\-organ\s+ct)?)\b': "Synapse Multi-Organ CT",
    r'\b(?:acdc(?:\s+cardiac|\s+dataset|\s+mri)?)\b': "ACDC Cardiac MRI",
    r'\b(?:brats(?:\s*2021|\s*2020|\s*2019|\s*2018)?)\b': "BraTS 2021",
    r'\b(?:imagenet(?:\-?1k|\-?21k)?)\b': "ImageNet",
    r'\b(?:coco|ms\-?coco)\b': "MS COCO",
    r'\b(?:pascal\s*voc|voc\s*2012)\b': "PASCAL VOC",
    r'\b(?:isic(?:\s*2018|\s*2019|\s*2020)?)\b': "ISIC Skin Lesion",
    r'\b(?:luna16|luna\s*16)\b': "LUNA16",
    r'\b(?:covid\-?19\s+ct|covid\s+ct)\b': "COVID-19 CT Dataset",
    r'\b(?:chexpert)\b': "CheXpert",
    r'\b(?:mimic(?:\-cxr)?)\b': "MIMIC-CXR",
    r'\b(?:drive|stare)\b': "DRIVE Retinal Dataset"
}


def normalize_method_name(raw_name: str) -> str:
    """
    Normalizes a raw method name to its canonical standardized representation.
    """
    if not raw_name:
        return ""
    
    name_clean = raw_name.strip()
    
    for pattern, canonical in METHOD_CANONICAL_MAP.items():
        if re.search(pattern, name_clean, flags=re.IGNORECASE):
            return canonical
            
    # Fallback: title-cased trimmed name
    return name_clean.title() if len(name_clean) < 30 else name_clean


def normalize_dataset_name(raw_name: str) -> str:
    """
    Normalizes a raw dataset name to its canonical standardized representation.
    """
    if not raw_name:
        return ""
        
    name_clean = raw_name.strip()
    
    for pattern, canonical in DATASET_CANONICAL_MAP.items():
        if re.search(pattern, name_clean, flags=re.IGNORECASE):
            return canonical
            
    return name_clean.title() if len(name_clean) < 30 else name_clean
