"""
Method Adoption Tracker for Stage 5 Trend Analysis (Phase 7).
Computes longitudinal time-series frequencies, canonical method consolidation,
and rigorous snapshot/longitudinal trajectory classifications with defensible reasons.
"""

import logging
from collections import defaultdict
from typing import List, Dict, Any, Tuple, Optional
from .models import MethodTrend, YearlyFrequency
from trends.entity_resolver import HierarchicalEntityResolver

logger = logging.getLogger("trendscope.trends.methods")


def classify_trajectory(
    yearly_counts: Dict[int, int], 
    total_papers_per_year: Dict[int, int],
    total_corpus_size: int,
    total_occurrences: int,
    primary_role: str = "proposed",
    first_year: int = 2026,
    latest_year: int = 2026
) -> Tuple[str, float, str, float]:
    """
    Classifies the method adoption trajectory distinguishing between snapshot mode
    and longitudinal mode. Returns (trajectory, growth_rate, reason, confidence).
    """
    sorted_years = sorted(total_papers_per_year.keys())
    corpus_share = (total_occurrences / max(1, total_corpus_size)) * 100.0

    # 1. Snapshot Mode (Year span <= 1 year)
    if len(sorted_years) <= 1:
        if primary_role in ["baseline", "compared"]:
            return (
                "BASELINE_COMPARATOR",
                0.0,
                f"Serves as standardized comparative baseline across {total_occurrences} paper(s) ({corpus_share:.1f}% share).",
                0.95
            )
        elif corpus_share >= 25.0:
            return (
                "DOMINANT",
                0.0,
                f"High-frequency foundational methodology appearing in {corpus_share:.1f}% of papers in current corpus snapshot.",
                0.90
            )
        elif total_occurrences >= 2:
            return (
                "STABLE",
                0.0,
                f"Consistently validated methodology adopted across {total_occurrences} independent papers ({corpus_share:.1f}% share).",
                0.85
            )
        else:
            return (
                "SPECIALIZED",
                0.0,
                f"Domain-specific proposed methodology introduced in single study ({corpus_share:.1f}% share).",
                0.80
            )

    # 2. Longitudinal Mode (Multi-year coverage)
    proportions = [
        yearly_counts.get(y, 0) / max(1, total_papers_per_year.get(y, 1))
        for y in sorted_years
    ]

    half = max(1, len(sorted_years) // 2)
    early_slice = proportions[:half]
    late_slice = proportions[half:]

    early_avg = sum(early_slice) / max(1, len(early_slice))
    late_avg = sum(late_slice) / max(1, len(late_slice))

    if early_avg == 0:
        growth_rate = 100.0 if late_avg > 0 else 0.0
    else:
        growth_rate = ((late_avg - early_avg) / early_avg) * 100.0

    # Longitudinal classification rules
    if corpus_share >= 30.0 and late_avg >= 0.25:
        return (
            "DOMINANT",
            round(growth_rate, 2),
            f"Dominant core architecture maintaining {corpus_share:.1f}% overall adoption share and high latest-period penetration ({late_avg:.1%}).",
            0.95
        )
    elif early_avg == 0 and late_avg > 0 and primary_role == "proposed":
        return (
            "EMERGING",
            round(growth_rate, 2),
            f"Novel emerging paradigm introduced in {sorted_years[-1]} with zero earlier historical representation, exhibiting rapid adoption ({late_avg:.1%}).",
            0.92
        )
    elif growth_rate > 25.0:
        return (
            "INCREASING",
            round(growth_rate, 2),
            f"Accelerating adoption growth of +{growth_rate:.1f}% from early period ({early_avg:.1%}) to late period ({late_avg:.1%}).",
            0.90
        )
    elif growth_rate < -25.0:
        return (
            "DECLINING",
            round(growth_rate, 2),
            f"Deprecating adoption trajectory (-{abs(growth_rate):.1f}% decline) superseded by newer foundation architectures.",
            0.88
        )
    else:
        return (
            "STABLE",
            round(growth_rate, 2),
            f"Stable steady-state longitudinal adoption ({early_avg:.1%} early vs {late_avg:.1%} late).",
            0.85
        )


def track_method_trends(
    papers: List[Dict[str, Any]], 
    min_occurrences: int = 1,
    resolver: Optional[HierarchicalEntityResolver] = None
) -> List[MethodTrend]:
    """
    Aggregates methods across papers using 3-level hierarchical canonicalization
    and computes structured trend analytics.
    """
    total_corpus_size = len(papers)
    total_papers_per_year: Dict[int, int] = defaultdict(int)
    
    # Store aggregated method families
    method_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "category": "Core Methodology",
        "paradigm": "Specialized AI Methodologies",
        "type": "model",
        "role_counts": defaultdict(int),
        "aliases": set(),
        "yearly_counts": defaultdict(int),
        "paper_ids": []
    })

    if resolver is None:
        resolver = HierarchicalEntityResolver(run_id="default")

    # 1. Process and consolidate methods per paper
    for p in papers:
        year = p.get("publication_year") or 2026
        paper_id = p.get("paper_id", "unknown")
        total_papers_per_year[year] += 1

        # Track unique methods per paper to prevent duplicate counting in same paper
        seen_in_paper: Set[str] = set()

        for m in p.get("methods", []):
            raw_name = m.get("name", "").strip()
            if not raw_name:
                continue

            decision = resolver.resolve_entity(raw_name, entity_type="method", paper_id=paper_id)
            canonical_name = decision.canonical_name
            family = decision.family
            paradigm = decision.paradigm
            role = m.get("role", "proposed")
            m_type = m.get("type", "model")

            if canonical_name not in seen_in_paper:
                seen_in_paper.add(canonical_name)
                entry = method_data[canonical_name]
                entry["category"] = family
                entry["paradigm"] = paradigm
                entry["type"] = m_type
                entry["role_counts"][role] += 1
                entry["aliases"].add(raw_name)
                entry["yearly_counts"][year] += 1
                if paper_id not in entry["paper_ids"]:
                    entry["paper_ids"].append(paper_id)

    # 2. Build MethodTrend profiles
    trends: List[MethodTrend] = []
    sorted_years = sorted(total_papers_per_year.keys())

    for canonical_name, data in method_data.items():
        total_occ = len(data["paper_ids"])
        if total_occ < min_occurrences:
            continue

        paper_pct = round((total_occ / max(1, total_corpus_size)) * 100.0, 2)
        
        # Determine primary role
        primary_role = "proposed"
        if data["role_counts"]:
            primary_role = max(data["role_counts"].items(), key=lambda x: x[1])[0]

        # Yearly distribution
        yearly_dist = [
            YearlyFrequency(
                year=y,
                count=data["yearly_counts"].get(y, 0),
                percentage=round((data["yearly_counts"].get(y, 0) / max(1, total_papers_per_year.get(y, 1))) * 100.0, 2)
            )
            for y in sorted_years
        ]

        traj, growth, reason, conf = classify_trajectory(
            yearly_counts=data["yearly_counts"],
            total_papers_per_year=total_papers_per_year,
            total_corpus_size=total_corpus_size,
            total_occurrences=total_occ,
            primary_role=primary_role,
            first_year=sorted_years[0] if sorted_years else 2026,
            latest_year=sorted_years[-1] if sorted_years else 2026
        )

        trends.append(MethodTrend(
            name=canonical_name,
            category=data["category"],
            paradigm=data["paradigm"],
            type=data["type"],
            role_primary=primary_role,
            raw_aliases=sorted(list(data["aliases"])),
            total_occurrences=total_occ,
            paper_percentage=paper_pct,
            trajectory=traj,
            trajectory_reason=reason,
            growth_rate=growth,
            confidence=conf,
            yearly_distribution=yearly_dist,
            top_paper_ids=data["paper_ids"][:10]
        ))

    # Sort by total occurrences descending
    trends.sort(key=lambda x: x.total_occurrences, reverse=True)
    return trends
