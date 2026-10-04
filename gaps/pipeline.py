"""
Pipeline orchestrator for Stage 6: Research Limitation Evolution & Gap Detection.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

from .models import GapRunManifest
from .theme_clusterer import cluster_limitation_themes
from .lifecycle_classifier import classify_theme_lifecycles
from .evidence_linker import build_evidence_links
from .storage import save_gap_manifest

logger = logging.getLogger("trendscope.gaps.pipeline")


class GapPipeline:
    """Executes Stage 6 Research Evolution and Gap Detection across the extracted scientific corpus."""

    def __init__(self, db_path: str = "data/trendscope.db"):
        self.db_path = db_path

    def run_for_run_id(self, run_id: str) -> GapRunManifest:
        """
        Runs gap analysis for a given run_id by reading extracted JSON manifest.
        """
        extracted_path = f"data/extracted/extracted_{run_id}.json"
        if not os.path.exists(extracted_path):
            raise FileNotFoundError(f"Extracted JSON manifest not found: {extracted_path}")

        with open(extracted_path, "r", encoding="utf-8") as f:
            extracted_data = json.load(f)

        papers = extracted_data.get("papers", [])
        if not papers:
            raise ValueError(f"No extracted papers found in {extracted_path}")

        return self.run_for_extracted_papers(run_id=run_id, papers=papers)

    def run_for_extracted_papers(
        self,
        run_id: str,
        papers: List[Dict[str, Any]]
    ) -> GapRunManifest:
        """
        Processes extracted paper list to produce GapRunManifest.
        """
        logger.info(f"=== Starting Stage 6 Research Gap Analysis for run: {run_id} ({len(papers)} papers) ===")

        # 1. Cluster Limitation Themes
        raw_themes = cluster_limitation_themes(papers)

        # 2. Classify Temporal Lifecycles
        classified_themes = classify_theme_lifecycles(raw_themes, papers)

        # 3. Build Inter-Paper Evidence Links
        evidence_links = build_evidence_links(classified_themes, papers)

        # 4. Summary metrics
        total_lims = sum(len(p.get("limitations", [])) for p in papers)
        open_gaps = sum(1 for t in classified_themes if t.lifecycle_status in ["UNADDRESSED", "PARTIALLY_ADDRESSED"])
        resolved_count = sum(1 for t in classified_themes if t.lifecycle_status in ["RESOLVED", "CONVERGED"])

        manifest = GapRunManifest(
            run_id=run_id,
            timestamp=datetime.utcnow().isoformat(),
            total_limitations_mined=total_lims,
            total_themes_discovered=len(classified_themes),
            open_unaddressed_gaps_count=open_gaps,
            resolved_or_converged_count=resolved_count,
            themes=classified_themes,
            evidence_links=evidence_links
        )

        # 5. Persist to SQLite & JSON
        save_gap_manifest(manifest, db_path=self.db_path)
        logger.info(
            f"=== Completed Stage 6 Gap Analysis for {run_id}. "
            f"Discovered {len(classified_themes)} themes ({open_gaps} open research gaps). ==="
        )
        return manifest
