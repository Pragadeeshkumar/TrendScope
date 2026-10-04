"""
Pydantic data models for Stage 6: Research Limitation Evolution & Gap Detection.
Tracks limitation themes, temporal lifecycle statuses, and sentence-level evidence links.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from extraction.models import ProvenancePointer


class LimitationInstance(BaseModel):
    """An individual limitation extracted from a specific paper."""
    paper_id: str
    paper_title: str
    publication_year: int
    text: str
    category: str
    provenance: ProvenancePointer


class EvidenceLink(BaseModel):
    """Direct citation/evidence connection linking a problem in Paper A to a solution in Paper B."""
    theme_id: str
    theme_name: Optional[str] = None
    source_paper_id: str
    source_paper_title: Optional[str] = None
    source_year: int
    source_quote: str
    source_section: Optional[str] = "Limitations"
    source_page: Optional[int] = 1
    target_paper_id: str
    target_paper_title: Optional[str] = None
    target_year: int
    target_quote: str
    target_section: Optional[str] = "Methodology"
    target_page: Optional[int] = 1
    target_method: Optional[str] = None
    relation_type: str = Field(description="'SOLVES', 'PARTIALLY_ADDRESSES', 'EXTENDS', 'CONTESTS', 'CONFIRMS'")


class LimitationTheme(BaseModel):
    """A recurring scientific limitation theme clustered across multiple research papers."""
    theme_id: str
    name: str = Field(description="Descriptive academic title of the limitation theme")
    category: str = Field(description="Category: computational_cost, data_scarcity, generalization, etc.")
    description: str = Field(description="Synthesized summary of the underlying scientific challenge")
    total_papers: int = Field(description="Number of papers reporting this limitation")
    first_year: int
    latest_year: int
    lifecycle_status: str = Field(
        description="'UNADDRESSED', 'PARTIALLY_ADDRESSED', 'CONTESTED', 'CONVERGED', 'RESOLVED'"
    )
    confidence: float = Field(default=0.85, description="Confidence in status classification (0.0 to 1.0)")
    paper_ids: List[str] = Field(default_factory=list)
    key_quotes: List[str] = Field(default_factory=list)
    resolution_evidence: Optional[str] = None
    actionable_frontier: Optional[str] = Field(default=None, description="Concrete recommended research direction / opportunity")
    affected_methods: List[str] = Field(default_factory=list, description="Method families affected by this limitation")
    affected_benchmarks: List[str] = Field(default_factory=list, description="Benchmarks where this bottleneck was observed")


class GapRunManifest(BaseModel):
    """Corpus-level container for Stage 6 Research Evolution and Gap Detection."""
    run_id: str
    timestamp: str
    total_limitations_mined: int
    total_themes_discovered: int
    open_unaddressed_gaps_count: int
    resolved_or_converged_count: int
    themes: List[LimitationTheme] = Field(default_factory=list)
    evidence_links: List[EvidenceLink] = Field(default_factory=list)
