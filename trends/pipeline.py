"""
Pipeline orchestrator for Stage 5: Longitudinal Trend Analysis (TrendScope V2).
Executes hierarchical method tracking, benchmark concentration analysis,
cluster affinity mapping, research gap synthesis, and report generation.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import sqlite3
from .models import TrendRunManifest
from .method_tracker import track_method_trends
from .dataset_tracker import track_dataset_trends
from .cluster_analyzer import analyze_cluster_trends
from .gap_detector import ResearchGapDetector
from .entity_resolver import HierarchicalEntityResolver
from .evidence_graph import EvidenceGraphBuilder
from .storage import save_trend_manifest
from extraction.models import PaperExtractionResult
from extraction.storage import convert_extraction_result_to_evidence
from extraction.validator import validate_paper_evidence_record

logger = logging.getLogger("trendscope.trends.pipeline")


class TrendPipeline:
    """Executes Stage 5 Trend Analysis across an extracted scientific corpus."""

    def __init__(self, db_path: str = "data/trendscope.db"):
        self.db_path = db_path

    def _lookup_domain(self, run_id: str, taxonomy_data: Optional[Dict[str, Any]] = None) -> str:
        """Looks up domain title from taxonomy or SQLite."""
        if taxonomy_data and taxonomy_data.get("domain"):
            return taxonomy_data["domain"]
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT original_query FROM retrieval_runs WHERE run_id = ?", (run_id,))
            row = c.fetchone()
            conn.close()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
        return "Clinical Artificial Intelligence"

    def run_for_run_id(self, run_id: str) -> TrendRunManifest:
        """
        Runs trend analytics for a given run_id by reading extracted JSON and taxonomy JSON.
        """
        extracted_path = f"data/extracted/extracted_{run_id}.json"
        if not os.path.exists(extracted_path):
            raise FileNotFoundError(f"Extracted JSON manifest not found: {extracted_path}")

        with open(extracted_path, "r", encoding="utf-8") as f:
            extracted_data = json.load(f)

        papers = extracted_data.get("papers", [])
        if not papers:
            raise ValueError(f"No extracted papers found in {extracted_path}")

        # Optional: Load Stage 4 Taxonomy
        taxonomy_data = None
        taxonomy_path = f"data/taxonomy/taxonomy_{run_id}.json"
        if os.path.exists(taxonomy_path):
            with open(taxonomy_path, "r", encoding="utf-8") as f:
                taxonomy_data = json.load(f)

        return self.run_for_extracted_papers(run_id=run_id, papers=papers, taxonomy_data=taxonomy_data)

    def run_for_extracted_papers(
        self,
        run_id: str,
        papers: list,
        taxonomy_data: Optional[Dict[str, Any]] = None
    ) -> TrendRunManifest:
        """
        Processes list of extracted paper dictionaries to produce a TrendRunManifest.
        """
        logger.info(f"=== Starting Stage 5 Trend Analysis for run: {run_id} ({len(papers)} papers) ===")

        # 1. Year range & Domain lookup
        years = [p.get("publication_year") for p in papers if p.get("publication_year")]
        year_range = [min(years), max(years)] if years else [2026, 2026]
        domain = self._lookup_domain(run_id, taxonomy_data)
        corpus_mode = "SNAPSHOT" if (year_range[1] - year_range[0]) <= 1 else "LONGITUDINAL"

        # 2. Convert to PaperEvidenceRecord and validate evidence
        evidence_records = []
        for p in papers:
            res = PaperExtractionResult(**p) if isinstance(p, dict) else p
            ev = convert_extraction_result_to_evidence(res, run_id=run_id)
            val_ev, _ = validate_paper_evidence_record(ev)
            evidence_records.append(val_ev)

        # 3. Hierarchical Entity Resolution (Phase 4)
        resolver = HierarchicalEntityResolver(run_id=run_id, db_path=self.db_path)
        resolved_evidence, ontology = resolver.resolve_corpus_evidence(evidence_records)
        resolver.save_ontology_decisions_to_json(f"data/trends/canonical_ontology_{run_id}.json")

        # 4. Construct Scientific Evidence Graph (Phase 5)
        graph_builder = EvidenceGraphBuilder(run_id=run_id)
        evidence_graph = graph_builder.build_graph(resolved_evidence)
        graph_builder.save_graph_to_json(evidence_graph, f"data/trends/evidence_graph_{run_id}.json")

        # Convert validated evidence back to paper dicts for trackers
        validated_paper_dicts = []
        for ev in resolved_evidence:
            validated_paper_dicts.append({
                "paper_id": ev.paper_id,
                "title": ev.title,
                "publication_year": ev.publication_year,
                "methods": [{"name": e.canonical_name, "role": e.role, "type": e.subtype} for e in ev.entities if e.entity_type == "method"],
                "datasets": [{"name": e.canonical_name, "modality": e.subtype, "usage": e.role} for e in ev.entities if e.entity_type == "dataset"],
                "limitations": [{"text": l.text, "category": l.category} for l in ev.limitations],
                "future_work": [{"text": fw.text, "category": fw.category} for fw in ev.future_work],
                "findings": [{"text": f.text, "metric": f.metric, "value": f.value, "direction": f.direction} for f in ev.findings]
            })

        # 5. Track Method Trends (Phase 7)
        method_trends = track_method_trends(validated_paper_dicts, resolver=resolver)
        emerging_methods = [m for m in method_trends if m.trajectory in ["EMERGING", "INCREASING"]]

        # 6. Track Dataset Trends & Benchmark Diversity HHI (Phase 8)
        dataset_trends, diversity_metrics = track_dataset_trends(validated_paper_dicts, resolver=resolver)

        # 7. Sub-Problem x Method Affinity Matrix (Phase 9)
        cluster_profiles = analyze_cluster_trends(validated_paper_dicts, taxonomy_data, resolver=resolver)

        # 8. Cross-Paper Research Gap Detection (Phase 10)
        gap_detector = ResearchGapDetector(run_id=run_id)
        research_gaps = gap_detector.detect_gaps(resolved_evidence, diversity_metrics=diversity_metrics)

        # 9. Build TrendRunManifest
        manifest = TrendRunManifest(
            run_id=run_id,
            timestamp=datetime.utcnow().isoformat(),
            corpus_mode=corpus_mode,
            total_papers=len(papers),
            year_range=year_range,
            total_unique_methods=len(method_trends),
            total_unique_datasets=len(dataset_trends),
            benchmark_metrics=diversity_metrics,
            emerging_methods=emerging_methods,
            top_methods=method_trends[:20],
            top_datasets=dataset_trends[:20],
            cluster_profiles=cluster_profiles,
            research_gaps=research_gaps
        )

        # 10. Save Manifest, SQLite tables, and 13-section report (Phase 11)
        save_trend_manifest(
            manifest=manifest,
            evidence_records=resolved_evidence,
            domain=domain,
            db_path=self.db_path,
            output_dir="data/trends"
        )

        logger.info(
            f"=== Completed Stage 5 Trend Analysis for {run_id}: "
            f"{len(method_trends)} methods, {len(dataset_trends)} datasets, "
            f"HHI={diversity_metrics.hhi:.4f}, {len(research_gaps)} research gaps. ==="
        )
        return manifest
