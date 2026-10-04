"""
Hierarchical Scientific Entity Resolver and Canonical Ontology Manager (Phase 4).
Implements a 3-level hierarchy: Raw Mention -> Canonical Entity -> Technical Family -> Scientific Paradigm.
Logs inspectable canonicalization decisions with confidence and supporting evidence.
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from collections import defaultdict, Counter
from pydantic import BaseModel, Field

from extraction.models import ScientificEntity, PaperEvidenceRecord

logger = logging.getLogger("trendscope.trends.entity_resolver")


class CanonicalDecision(BaseModel):
    """Auditable, inspectable canonicalization decision for an entity alias."""
    canonical_id: str
    canonical_name: str
    alias: str
    entity_type: str
    family: str
    paradigm: str
    reason: str
    confidence: float
    supporting_paper_ids: List[str] = Field(default_factory=list)


class ScientificOntology(BaseModel):
    """Full 3-level scientific ontology container."""
    canonical_entities: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    families: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    paradigms: Dict[str, List[str]] = Field(default_factory=dict)
    decisions: List[CanonicalDecision] = Field(default_factory=list)


# Established Base Ontology Rules: (Regex/Abbreviation -> Canonical Name, Family, Paradigm)
METHOD_ONTOLOGY_RULES: List[Tuple[str, str, str, str, str]] = [
    # (Pattern, Canonical Name, Family, Paradigm, Reason)
    (r"\b(?:rf|random\s+forest(?:\s+classifier)?)\b", "Random Forest", "Tree & Ensemble Learning", "Classical Predictive ML", "Exact morphological/abbreviation match"),
    (r"\b(?:xgb|xgboost|extreme\s+gradient\s+boosting)\b", "XGBoost", "Tree & Ensemble Learning", "Classical Predictive ML", "Exact algorithmic abbreviation match"),
    (r"\b(?:svm|support\s+vector\s+machine)\b", "Support Vector Machine", "Kernel Methods", "Classical Predictive ML", "Exact algorithmic abbreviation match"),
    (r"\b(?:lr|logistic\s+regression)\b", "Logistic Regression", "Generalized Linear Models", "Classical Predictive ML", "Exact statistical model match"),
    (r"\b(?:cnn|convolutional\s+neural\s+network)\b", "Convolutional Neural Network", "Convolutional Architectures", "Deep Learning & Representation Learning", "Standard DL architecture match"),
    (r"\b(?:resnet(?:\-\d+)?|residual\s+network)\b", "ResNet", "Convolutional Architectures", "Deep Learning & Representation Learning", "Standard backbone architecture match"),
    (r"\b(?:u\-?net|classic\s+u\-?net)\b", "UNet", "Biomedical Segmentation", "Deep Learning & Representation Learning", "Standard biomedical segmentation architecture"),
    (r"\b(?:nnunet|nn\s*u\-?net)\b", "nnU-Net", "Biomedical Segmentation", "Deep Learning & Representation Learning", "Automated framework match"),
    (r"\b(?:vit|vision\s+transformer)\b", "Vision Transformer", "Vision Transformers", "Deep Learning & Representation Learning", "Attention backbone match"),
    (r"\b(?:swin(?:\s+transformer|\-t|\-b|\-unet)?)\b", "Swin Transformer", "Hierarchical Vision Transformers", "Deep Learning & Representation Learning", "Shifted window transformer match"),
    (r"\b(?:transformer(?:\s+model|\s+architecture)?)\b", "Transformer", "Attention Architectures", "Deep Learning & Representation Learning", "Base attention architecture"),
    (r"\b(?:bert|biomedbert|biobert|clinicalbert)\b", "Biomedical BERT", "Encoder Language Models", "Foundation Models & LLMs", "Pretrained clinical encoder"),
    (r"\b(?:gpt(?:\-4|\-3\.5|\-4o)?|chatgpt|pediatricsgpt|medpalm(?:\-2)?)\b", "Clinical Large Language Model", "Clinical Foundation LLMs", "Foundation Models & LLMs", "Generative clinical LLM"),
    (r"\b(?:caregraph|missing\-context\s+agent|recommendation\s+safety\s+agent|patient\s+interface\s+agent)\b", "CareGraph Multi-Agent Architecture", "Agentic Clinical Systems", "Agentic Clinical AI", "Multi-agent clinical workflow framework"),
    (r"\b(?:frac\-mas|four\-agent\s+workflow|multi\-agent\s+deep\s+learning)\b", "FRAC-MAS Multi-Agent System", "Agentic Clinical Systems", "Agentic Clinical AI", "Collaborative diagnostic agent system"),
    (r"\b(?:diffusion\s+model(?:s)?|ddpm|ddim|latent\s+diffusion)\b", "Diffusion Generative Model", "Generative Models", "Generative AI & Synthesis", "Denoising diffusion architecture"),
    (r"\b(?:mamba|state\-space\s+model|ssm)\b", "State Space Model (Mamba)", "Linear Attention & State Space", "Next-Gen Sequence Modeling", "Selective state space model")
]

DATASET_ONTOLOGY_RULES: List[Tuple[str, str, str, str, str]] = [
    (r"\b(?:synapse(?:\s+multi\-organ\s+ct)?)\b", "Synapse Multi-Organ CT", "Abdominal Multi-Organ CT", "Radiological Benchmarks", "Standard benchmark dataset"),
    (r"\b(?:acdc(?:\s+cardiac|\s+dataset|\s+mri)?)\b", "ACDC Cardiac MRI", "Cardiac Cine-MRI", "Radiological Benchmarks", "Standard cardiac MRI benchmark"),
    (r"\b(?:brats(?:\s*2021|\s*2020|\s*2019|\s*2018)?)\b", "BraTS Brain Tumor MRI", "Multimodal Brain Tumor MRI", "Radiological Benchmarks", "Standard brain segmentation benchmark"),
    (r"\b(?:mimic(?:\-iv|\-iii|\-cxr)?)\b", "MIMIC Clinical Database", "Intensive Care EHR & Chest X-Ray", "Clinical EHR & Multimodal Data", "Standard intensive care clinical benchmark"),
    (r"\b(?:medqa|usmle(?:\s+bar)?)\b", "MedQA / USMLE Medical Exam", "Medical Question Answering", "Clinical NLP & Reasoning Benchmarks", "Clinical reasoning exam benchmark"),
    (r"\b(?:chexpert)\b", "CheXpert", "Chest Radiograph Multi-Label", "Radiological Benchmarks", "Standard chest radiograph dataset"),
    (r"\b(?:isic(?:\s*2018|\s*2019|\s*2020)?)\b", "ISIC Skin Lesion", "Dermoscopic Skin Lesion", "Dermatological Image Benchmarks", "Standard dermoscopy benchmark")
]


class HierarchicalEntityResolver:
    """
    Resolves extracted entities into a 3-level hierarchy with full provenance and audit logging.
    """

    def __init__(self, run_id: str, db_path: str = "data/trendscope.db"):
        self.run_id = run_id
        self.db_path = db_path
        self.decisions: List[CanonicalDecision] = []
        self.canonical_map: Dict[str, CanonicalDecision] = {}

    def resolve_entity(
        self,
        raw_name: str,
        entity_type: str,
        paper_id: str = "unknown"
    ) -> CanonicalDecision:
        """
        Resolves a raw entity string to its canonical entity, family, and paradigm.
        """
        clean_name = raw_name.strip()
        lookup_key = f"{entity_type}_{clean_name.lower()}"

        # 1. Check if already resolved in this run
        if lookup_key in self.canonical_map:
            decision = self.canonical_map[lookup_key]
            if paper_id not in decision.supporting_paper_ids:
                decision.supporting_paper_ids.append(paper_id)
            return decision

        # 2. Check deterministic ontology rules
        rules = METHOD_ONTOLOGY_RULES if entity_type == "method" else DATASET_ONTOLOGY_RULES
        for pattern, canonical_name, family, paradigm, reason in rules:
            if re.search(pattern, clean_name, flags=re.IGNORECASE):
                decision = CanonicalDecision(
                    canonical_id=f"canon_{entity_type}_{re.sub(r'[^\w]', '_', canonical_name.lower())}",
                    canonical_name=canonical_name,
                    alias=clean_name,
                    entity_type=entity_type,
                    family=family,
                    paradigm=paradigm,
                    reason=reason,
                    confidence=0.98,
                    supporting_paper_ids=[paper_id]
                )
                self.canonical_map[lookup_key] = decision
                self.decisions.append(decision)
                return decision

        # 3. Dynamic synthesis fallback (for novel domain terms)
        clean_title = clean_name.title() if len(clean_name) < 40 else clean_name
        fallback_family = f"{clean_title} Methods" if entity_type == "method" else f"{clean_title} Benchmarks"
        fallback_paradigm = "Specialized AI Methodologies" if entity_type == "method" else "Domain-Specific Resources"

        decision = CanonicalDecision(
            canonical_id=f"canon_{entity_type}_{re.sub(r'[^\w]', '_', clean_title.lower())}",
            canonical_name=clean_title,
            alias=clean_name,
            entity_type=entity_type,
            family=fallback_family,
            paradigm=fallback_paradigm,
            reason="Direct morphological normalization",
            confidence=0.85,
            supporting_paper_ids=[paper_id]
        )
        self.canonical_map[lookup_key] = decision
        self.decisions.append(decision)
        return decision

    def resolve_corpus_evidence(
        self,
        evidence_records: List[PaperEvidenceRecord]
    ) -> Tuple[List[PaperEvidenceRecord], ScientificOntology]:
        """
        Applies hierarchical entity resolution across a complete corpus of PaperEvidenceRecords.
        Updates each entity's canonical_name and generates a full ScientificOntology report.
        """
        for record in evidence_records:
            for ent in record.entities:
                decision = self.resolve_entity(
                    raw_name=ent.raw_name,
                    entity_type=ent.entity_type,
                    paper_id=record.paper_id
                )
                ent.canonical_name = decision.canonical_name
                ent.subtype = decision.family

        # Build complete ontology structure
        ontology = ScientificOntology()
        ontology.decisions = self.decisions

        for dec in self.decisions:
            # Index canonical entities
            if dec.canonical_name not in ontology.canonical_entities:
                ontology.canonical_entities[dec.canonical_name] = {
                    "canonical_id": dec.canonical_id,
                    "entity_type": dec.entity_type,
                    "family": dec.family,
                    "paradigm": dec.paradigm,
                    "aliases": [dec.alias],
                    "paper_count": len(dec.supporting_paper_ids)
                }
            else:
                if dec.alias not in ontology.canonical_entities[dec.canonical_name]["aliases"]:
                    ontology.canonical_entities[dec.canonical_name]["aliases"].append(dec.alias)

            # Index families
            if dec.family not in ontology.families:
                ontology.families[dec.family] = {
                    "paradigm": dec.paradigm,
                    "entity_type": dec.entity_type,
                    "canonical_members": [dec.canonical_name]
                }
            else:
                if dec.canonical_name not in ontology.families[dec.family]["canonical_members"]:
                    ontology.families[dec.family]["canonical_members"].append(dec.canonical_name)

            # Index paradigms
            if dec.paradigm not in ontology.paradigms:
                ontology.paradigms[dec.paradigm] = [dec.family]
            else:
                if dec.family not in ontology.paradigms[dec.paradigm]:
                    ontology.paradigms[dec.paradigm].append(dec.family)

        return evidence_records, ontology

    def save_ontology_decisions_to_json(
        self,
        output_path: str = "data/trends/canonical_ontology.json"
    ) -> None:
        """Saves all inspectable canonicalization decisions to JSON."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([d.dict() for d in self.decisions], f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.decisions)} canonical ontology decisions to {output_path}")
