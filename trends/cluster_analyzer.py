"""
Sub-Problem Cluster Cross-Analyzer and Taxonomy x Method Affinity Subsystem (Phase 9).
Maps canonical method families, emerging paradigms, and persistent limitations
onto Stage 4 taxonomy sub-problems.
"""

import re
import logging
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set
from .models import ClusterTrendProfile
from trends.entity_resolver import HierarchicalEntityResolver

logger = logging.getLogger("trendscope.trends.cluster_analyzer")

LITERATURE_DATABASES = {
    "pubmed", "scopus", "web of science", "ieee xplore", "embase", "proquest",
    "google scholar", "cochrane", "cochrane library", "medline", "cinahl"
}


def analyze_cluster_trends(
    papers: List[Dict[str, Any]], 
    taxonomy_data: Optional[Dict[str, Any]] = None,
    resolver: Optional[HierarchicalEntityResolver] = None
) -> List[ClusterTrendProfile]:
    """
    Computes method and benchmark affinity partitioned by Stage 4 taxonomy sub-problems.
    Maps dominant method family, emerging paradigm, and persistent limitations per sub-problem.
    """
    if not taxonomy_data or "clusters" not in taxonomy_data:
        logger.warning("No taxonomy data provided for cluster trend cross-analysis.")
        return []

    if resolver is None:
        resolver = HierarchicalEntityResolver(run_id="default")

    paper_lookup = {p.get("paper_id"): p for p in papers}
    profiles: List[ClusterTrendProfile] = []

    for cl in taxonomy_data.get("clusters", []):
        cid = str(cl.get("cluster_id"))
        cname = cl.get("name") or cl.get("label") or f"Cluster {cid}"
        pids = cl.get("paper_ids", [])

        method_family_counts: Dict[str, int] = defaultdict(int)
        method_paradigm_counts: Dict[str, int] = defaultdict(int)
        dataset_counts: Dict[str, int] = defaultdict(int)
        cluster_limitations: Set[str] = set()

        for pid in pids:
            p = paper_lookup.get(pid)
            if not p:
                continue

            # Methods in this paper
            seen_m_in_paper = set()
            for m in p.get("methods", []):
                raw_m = m.get("name") or ""
                raw_m = raw_m.strip()
                if not raw_m or len(raw_m) < 3:
                    continue

                decision = resolver.resolve_entity(raw_m, entity_type="method", paper_id=pid)
                canonical_m = decision.canonical_name
                family = decision.family
                paradigm = decision.paradigm

                if canonical_m not in seen_m_in_paper:
                    seen_m_in_paper.add(canonical_m)
                    method_family_counts[family] += 1
                    method_paradigm_counts[paradigm] += 1

            # Datasets in this paper
            seen_d_in_paper = set()
            for d in p.get("datasets", []):
                raw_d = d.get("name") or ""
                raw_d = raw_d.strip()
                if not raw_d or len(raw_d) < 3:
                    continue
                if raw_d.lower() in LITERATURE_DATABASES or any(db in raw_d.lower() for db in LITERATURE_DATABASES):
                    continue

                decision = resolver.resolve_entity(raw_d, entity_type="dataset", paper_id=pid)
                canonical_d = decision.canonical_name

                if canonical_d not in seen_d_in_paper:
                    seen_d_in_paper.add(canonical_d)
                    dataset_counts[canonical_d] += 1

            # Limitations in this paper
            for lim in p.get("limitations", []):
                lim_text = lim.get("text", "")
                if lim_text and len(lim_text) > 10:
                    cluster_limitations.add(lim_text[:120])

        # Compute Dominant Method Family & Emerging Paradigm
        dominant_family = "Specialized Methodologies"
        if method_family_counts:
            dominant_family = max(method_family_counts.items(), key=lambda x: x[1])[0]

        emerging_paradigm = "Adaptive Scientific AI"
        if method_paradigm_counts:
            emerging_paradigm = max(method_paradigm_counts.items(), key=lambda x: x[1])[0]

        top_methods = [
            {"name": name, "count": cnt, "percentage": round((cnt / max(1, len(pids))) * 100, 1)}
            for name, cnt in sorted(method_family_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        top_datasets = [
            {"name": name, "count": cnt, "percentage": round((cnt / max(1, len(pids))) * 100, 1)}
            for name, cnt in sorted(dataset_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        profiles.append(ClusterTrendProfile(
            cluster_id=cid,
            cluster_name=cname,
            total_papers=len(pids),
            dominant_method_family=dominant_family,
            emerging_paradigm=emerging_paradigm,
            top_methods=top_methods,
            top_datasets=top_datasets,
            persistent_limitations=list(cluster_limitations)[:4],
            supporting_paper_ids=pids
        ))

    return profiles
