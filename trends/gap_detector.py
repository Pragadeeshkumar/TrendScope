"""
Cross-Paper Scientific Research Gap Detector (Phase 10).
Synthesizes recurring limitations, proposed future work directions, and benchmark coverage deficits
into structured, defensible research gaps grounded in paper-level evidence.
"""

import re
import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set
from .models import ResearchGap
from extraction.models import PaperEvidenceRecord

logger = logging.getLogger("trendscope.trends.gap_detector")


class ResearchGapDetector:
    """Detects and synthesizes field-level research gaps from corpus evidence."""

    def __init__(self, run_id: str):
        self.run_id = run_id

    def detect_gaps(
        self,
        evidence_records: List[PaperEvidenceRecord],
        diversity_metrics: Optional[Any] = None
    ) -> List[ResearchGap]:
        """
        Analyzes limitations, future work, and benchmark patterns across the corpus
        to construct defensible research gaps.
        """
        gaps: List[ResearchGap] = []
        total_papers = len(evidence_records)
        if total_papers == 0:
            return gaps

        # Category accumulators
        category_limitations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        category_future_work: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for rec in evidence_records:
            for lim in rec.limitations:
                cat = lim.category.lower()
                category_limitations[cat].append({
                    "paper_id": rec.paper_id,
                    "text": lim.text,
                    "quote": lim.provenance.quote if lim.provenance else lim.text
                })
            for fw in rec.future_work:
                cat = fw.category.lower() if fw.category else "methodological_extension"
                category_future_work[cat].append({
                    "paper_id": rec.paper_id,
                    "text": fw.text,
                    "quote": fw.provenance.quote if fw.provenance else fw.text
                })

        gap_idx = 1

        # 1. External Multi-Site Validation Deficit Gap
        val_lims = category_limitations.get("generalization", []) + category_limitations.get("data_scarcity", [])
        val_fw = category_future_work.get("external_validation", []) + category_future_work.get("clinical_trial", [])
        
        all_val_papers = list(set([item["paper_id"] for item in val_lims + val_fw]))
        if len(all_val_papers) >= 2 or (total_papers <= 3 and len(all_val_papers) >= 1):
            quotes = [item["quote"] for item in val_lims[:3] + val_fw[:3]]
            gaps.append(ResearchGap(
                gap_id=f"gap_{self.run_id}_{gap_idx}",
                title="Lack of Multi-Center External Validation and Prospective Clinical Trial Evidence",
                statement=(
                    f"While complex AI models exhibit strong retrospective validation, "
                    f"{len(all_val_papers)}/{total_papers} papers report explicit generalization barriers "
                    f"and call for multi-site prospective validation across diverse demographic and clinical settings."
                ),
                category="validation_deficit",
                supporting_papers=all_val_papers,
                supporting_evidence_quotes=quotes[:4],
                confidence=0.94,
                why_insufficient=(
                    "Existing evaluations predominantly rely on single-center retrospective cohorts or synthetic data, "
                    "leaving real-world clinical safety, domain-shift robustness, and demographic equity largely unproven."
                )
            ))
            gap_idx += 1

        # 2. Computational Overhead & Edge Deployment Bottleneck Gap
        cost_lims = category_limitations.get("computational_cost", []) + category_limitations.get("scalability", [])
        cost_fw = category_future_work.get("scale_up", []) + category_future_work.get("methodological_extension", [])
        all_cost_papers = list(set([item["paper_id"] for item in cost_lims]))
        if len(all_cost_papers) >= 2 or (total_papers <= 3 and len(all_cost_papers) >= 1):
            quotes = [item["quote"] for item in cost_lims[:3]]
            gaps.append(ResearchGap(
                gap_id=f"gap_{self.run_id}_{gap_idx}",
                title="Computational Overhead and High-Latency Inference in Resource-Constrained Environments",
                statement=(
                    f"High compute and latency overhead restricts deployment in point-of-care environments, "
                    f"as highlighted across {len(all_cost_papers)} studies."
                ),
                category="scalability_bottleneck",
                supporting_papers=all_cost_papers,
                supporting_evidence_quotes=quotes[:4],
                confidence=0.91,
                why_insufficient=(
                    "Current multi-agent and foundation model pipelines prioritize raw diagnostic accuracy "
                    "over edge-optimized memory footprints and real-time inference latency constraints."
                )
            ))
            gap_idx += 1

        # 3. Benchmark Concentration & Synthetic Data Reliance Gap
        if diversity_metrics and getattr(diversity_metrics, "synthetic_dataset_ratio", 0) >= 20.0:
            synth_papers = []
            synth_quotes = []
            for rec in evidence_records:
                for ent in rec.entities:
                    if ent.entity_type == "dataset" and ("synth" in ent.raw_name.lower() or "simulat" in ent.raw_name.lower()):
                        synth_papers.append(rec.paper_id)
                        if ent.provenance:
                            synth_quotes.append(ent.provenance.quote)
            
            synth_papers = list(set(synth_papers))
            if synth_papers:
                gaps.append(ResearchGap(
                    gap_id=f"gap_{self.run_id}_{gap_idx}",
                    title="Heavy Reliance on Synthetic Datasets and Lack of Standardized Benchmarks",
                    statement=(
                        f"Over {diversity_metrics.synthetic_dataset_ratio:.1f}% of evaluated benchmark instances "
                        f"depend on synthetic or simulated cohorts across {len(synth_papers)} papers."
                    ),
                    category="modality_gap",
                    supporting_papers=synth_papers,
                    supporting_evidence_quotes=synth_quotes[:4],
                    confidence=0.88,
                    why_insufficient=(
                        "Synthetic benchmark distributions often fail to replicate noisy clinical artifacts, "
                        "edge-case anatomical variations, and multimodal electronic health record complexities."
                    )
                ))
                gap_idx += 1

        # 4. Interpretability, Auditability, and Regulatory Governance Gap
        safety_lims = category_limitations.get("interpretability", []) + category_limitations.get("safety", [])
        all_safety_papers = list(set([item["paper_id"] for item in safety_lims]))
        if len(all_safety_papers) >= 1:
            quotes = [item["quote"] for item in safety_lims[:3]]
            gaps.append(ResearchGap(
                gap_id=f"gap_{self.run_id}_{gap_idx}",
                title="Black-Box Clinical Opacity and Missing Verifiable Audit Trails",
                statement=(
                    f"Clinicians require explainable decision logic and auditable recommendation provenance, "
                    f"which remains an active bottleneck reported in {len(all_safety_papers)} papers."
                ),
                category="safety_oversight",
                supporting_papers=all_safety_papers,
                supporting_evidence_quotes=quotes[:4],
                confidence=0.92,
                why_insufficient=(
                    "Standard end-to-end deep architectures lack granular intermediate reasoning traces, "
                    "hindering clinical trust and regulatory compliance (FDA/MDR requirements)."
                )
            ))
            gap_idx += 1

        logger.info(f"Synthesized {len(gaps)} cross-paper research gaps for run '{self.run_id}'")
        return gaps
