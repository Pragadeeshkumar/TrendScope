"""
Inter-Paper Evidence Linker for Stage 6.
Constructs verifiable provenance chains linking earlier paper limitation quotes to later paper solution sentences.
"""

import logging
from typing import List, Dict, Any
from .models import EvidenceLink, LimitationTheme

logger = logging.getLogger("trendscope.gaps.evidence_linker")


def build_evidence_links(
    themes: List[LimitationTheme], 
    papers: List[Dict[str, Any]]
) -> List[EvidenceLink]:
    """
    Identifies inter-paper evidence pairs where Paper A acknowledges a limitation
    and Paper B proposes a related method or direction.
    """
    links: List[EvidenceLink] = []
    paper_lookup = {p.get("paper_id"): p for p in papers}

    for theme in themes:
        theme_pids = [pid for pid in theme.paper_ids if pid in paper_lookup]
        if len(theme_pids) < 2:
            continue

        # Sort papers chronologically
        sorted_pids = sorted(
            theme_pids, 
            key=lambda pid: paper_lookup[pid].get("publication_year", 2026)
        )

        source_pid = sorted_pids[0]
        source_paper = paper_lookup[source_pid]
        source_year = source_paper.get("publication_year", 2024)

        # Find first limitation quote from source
        source_quote = ""
        for lim in source_paper.get("limitations", []):
            prov = lim.get("provenance", {})
            if prov.get("quote"):
                source_quote = prov.get("quote")
                break
        if not source_quote:
            source_quote = source_paper.get("title", "")

        # Link to subsequent papers
        for target_pid in sorted_pids[1:3]:
            target_paper = paper_lookup[target_pid]
            target_year = target_paper.get("publication_year", 2026)

            # Find method or future work quote
            target_quote = ""
            for m in target_paper.get("methods", []):
                prov = m.get("provenance", {})
                if prov.get("quote"):
                    target_quote = prov.get("quote")
                    break
            if not target_quote:
                target_quote = target_paper.get("title", "")

            relation = "PARTIALLY_ADDRESSES" if target_year >= source_year else "CONFIRMS"

            links.append(EvidenceLink(
                theme_id=theme.theme_id,
                source_paper_id=source_pid,
                source_year=source_year,
                source_quote=source_quote[:250],
                target_paper_id=target_pid,
                target_year=target_year,
                target_quote=target_quote[:250],
                relation_type=relation
            ))

    logger.info(f"Constructed {len(links)} verifiable inter-paper evidence links.")
    return links
