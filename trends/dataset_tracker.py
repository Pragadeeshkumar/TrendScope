"""
Dataset Popularity, Benchmark Concentration, and Validation Diversity Tracker (Phase 8).
Measures benchmark utilization distributions, canonical benchmark grouping,
and calculates Herfindahl-Hirschman Index (HHI) and external validation diversity.
"""

import re
import logging
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional, Set
from .models import DatasetTrend, DatasetDiversityMetrics, YearlyFrequency
from trends.entity_resolver import HierarchicalEntityResolver

logger = logging.getLogger("trendscope.trends.datasets")

# Literature databases to rigorously exclude from benchmark concentration
LITERATURE_DATABASES = {
    "pubmed", "scopus", "web of science", "ieee xplore", "embase", "proquest",
    "google scholar", "cochrane", "cochrane library", "medline", "cinahl",
    "springerlink", "sciencedirect", "arxiv", "biorxiv", "medrxiv"
}


def compute_benchmark_diversity(
    dataset_occurrences: Dict[str, int],
    total_corpus_size: int,
    paper_dataset_counts: List[int],
    synthetic_counts: int
) -> DatasetDiversityMetrics:
    """
    Computes Herfindahl-Hirschman Index (HHI) and scientific benchmark diversity metrics.
    """
    total_uses = sum(dataset_occurrences.values())
    if total_uses == 0:
        return DatasetDiversityMetrics(
            hhi=0.0,
            hhi_interpretation="Well-Diversified",
            synthetic_dataset_ratio=0.0,
            external_validation_ratio=0.0,
            single_dataset_paper_ratio=0.0,
            top_1_dataset_share=0.0,
            top_3_dataset_share=0.0
        )

    shares = [count / total_uses for count in dataset_occurrences.values()]
    hhi = sum(s ** 2 for s in shares)
    hhi_rounded = round(hhi, 4)

    if hhi_rounded >= 0.25:
        interpretation = "Highly Concentrated (Monopoly Risk)"
    elif hhi_rounded >= 0.15:
        interpretation = "Moderately Concentrated"
    else:
        interpretation = "Well-Diversified Benchmarks"

    # Sorted shares
    sorted_shares = sorted(shares, reverse=True)
    top_1 = round(sorted_shares[0] * 100.0, 2) if sorted_shares else 0.0
    top_3 = round(sum(sorted_shares[:3]) * 100.0, 2) if len(sorted_shares) >= 3 else round(sum(sorted_shares) * 100.0, 2)

    # Multi-dataset validation vs single dataset
    single_ds_papers = sum(1 for c in paper_dataset_counts if c == 1)
    multi_ds_papers = sum(1 for c in paper_dataset_counts if c > 1)
    single_ratio = round((single_ds_papers / max(1, len(paper_dataset_counts))) * 100.0, 2)
    ext_val_ratio = round((multi_ds_papers / max(1, len(paper_dataset_counts))) * 100.0, 2)

    synth_ratio = round((synthetic_counts / max(1, total_uses)) * 100.0, 2)

    return DatasetDiversityMetrics(
        hhi=hhi_rounded,
        hhi_interpretation=interpretation,
        synthetic_dataset_ratio=synth_ratio,
        external_validation_ratio=ext_val_ratio,
        single_dataset_paper_ratio=single_ratio,
        top_1_dataset_share=top_1,
        top_3_dataset_share=top_3
    )


def compute_benchmark_hhi(dataset_occurrences: Dict[str, int]) -> Tuple[float, str]:
    """Backward compatibility wrapper returning (hhi_score, interpretation)."""
    metrics = compute_benchmark_diversity(
        dataset_occurrences=dataset_occurrences,
        total_corpus_size=sum(dataset_occurrences.values()),
        paper_dataset_counts=[],
        synthetic_counts=0
    )
    return metrics.hhi, metrics.hhi_interpretation


def track_dataset_trends(
    papers: List[Dict[str, Any]], 
    min_occurrences: int = 1,
    resolver: Optional[HierarchicalEntityResolver] = None
) -> Tuple[List[DatasetTrend], DatasetDiversityMetrics]:
    """
    Aggregates datasets across papers using canonical benchmark consolidation,
    excludes literature search indexes, and computes concentration analytics.
    """
    total_corpus_size = len(papers)
    total_papers_per_year: Dict[int, int] = defaultdict(int)
    
    dataset_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "modality": "Standard Benchmark",
        "aliases": set(),
        "is_synthetic": False,
        "yearly_counts": defaultdict(int),
        "paper_ids": []
    })

    if resolver is None:
        resolver = HierarchicalEntityResolver(run_id="default")

    paper_dataset_counts: List[int] = []
    synthetic_uses = 0

    # 1. Process and consolidate datasets per paper
    for p in papers:
        year = p.get("publication_year") or 2026
        paper_id = p.get("paper_id", "unknown")
        total_papers_per_year[year] += 1

        seen_families_in_paper: Set[str] = set()
        datasets_in_paper_count = 0

        for d in p.get("datasets", []):
            raw_name = d.get("name", "").strip()
            if not raw_name:
                continue

            # Strict exclusion of literature indexing databases
            raw_lower = raw_name.lower()
            if raw_lower in LITERATURE_DATABASES or any(db in raw_lower for db in LITERATURE_DATABASES):
                continue

            decision = resolver.resolve_entity(raw_name, entity_type="dataset", paper_id=paper_id)
            canonical_name = decision.canonical_name
            modality = decision.family

            is_synth = "synth" in raw_lower or "simulat" in raw_lower

            if canonical_name in seen_families_in_paper:
                dataset_data[canonical_name]["aliases"].add(raw_name)
                continue

            seen_families_in_paper.add(canonical_name)
            datasets_in_paper_count += 1
            if is_synth:
                synthetic_uses += 1

            dataset_data[canonical_name]["modality"] = modality
            dataset_data[canonical_name]["is_synthetic"] = is_synth or dataset_data[canonical_name]["is_synthetic"]
            dataset_data[canonical_name]["aliases"].add(raw_name)
            dataset_data[canonical_name]["yearly_counts"][year] += 1
            if paper_id not in dataset_data[canonical_name]["paper_ids"]:
                dataset_data[canonical_name]["paper_ids"].append(paper_id)

        paper_dataset_counts.append(datasets_in_paper_count)

    # 2. Compute Benchmark HHI & Diversity Metrics
    counts_map = {name: len(d["paper_ids"]) for name, d in dataset_data.items()}
    diversity_metrics = compute_benchmark_diversity(
        dataset_occurrences=counts_map,
        total_corpus_size=total_corpus_size,
        paper_dataset_counts=paper_dataset_counts,
        synthetic_counts=synthetic_uses
    )

    # 3. Build DatasetTrend profiles
    all_years = sorted(total_papers_per_year.keys())
    trends: List[DatasetTrend] = []

    for name, data in dataset_data.items():
        total_occ = len(data["paper_ids"])
        if total_occ < min_occurrences:
            continue

        paper_pct = round((total_occ / max(1, total_corpus_size)) * 100.0, 2)
        is_monopoly = paper_pct >= 25.0

        yearly_dist = [
            YearlyFrequency(
                year=y,
                count=data["yearly_counts"].get(y, 0),
                percentage=round((data["yearly_counts"].get(y, 0) / max(1, total_papers_per_year.get(y, 1))) * 100.0, 2)
            )
            for y in all_years
        ]

        trends.append(DatasetTrend(
            name=name,
            modality=data["modality"],
            raw_aliases=sorted(list(data["aliases"])),
            total_occurrences=total_occ,
            paper_percentage=paper_pct,
            is_benchmark_monopoly=is_monopoly,
            is_synthetic=data["is_synthetic"],
            yearly_distribution=yearly_dist,
            top_paper_ids=data["paper_ids"][:10]
        ))

    trends.sort(key=lambda x: x.total_occurrences, reverse=True)
    return trends, diversity_metrics