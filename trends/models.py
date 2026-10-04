"""
Pydantic data models for Stage 5: Longitudinal Trend Analysis Subsystem (V2).
Tracks Method and Dataset trajectories, adoption dynamics, cluster cross-tabulations,
benchmark concentration (HHI), and cross-paper research gaps.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class YearlyFrequency(BaseModel):
    """Frequency count and proportion of an entity for a specific publication year."""
    year: int
    count: int
    percentage: float = Field(description="Percentage of total papers published in this year")


class MethodTrend(BaseModel):
    """Trend analysis profile for a specific scientific method or architecture family."""
    name: str = Field(description="Canonical method or architecture family name")
    category: str = Field(default="Core Methodology", description="Technical category/paradigm")
    paradigm: str = Field(default="Specialized AI Methodologies", description="High-level scientific paradigm")
    type: str = Field(default="model", description="Category: model, algorithm, loss_function, architecture, etc.")
    role_primary: str = Field(default="proposed", description="'proposed', 'baseline', 'backbone', 'component'")
    replaces_target: Optional[str] = Field(default=None, description="Predecessor technology/baseline this paradigm replaces")
    raw_aliases: List[str] = Field(default_factory=list, description="Raw variations and aliases extracted across papers")
    total_occurrences: int = Field(description="Total papers using this method")
    paper_percentage: float = Field(description="Percentage of total corpus papers using this method")
    trajectory: str = Field(description="'EMERGING', 'INCREASING', 'DOMINANT', 'STABLE', 'DECLINING', 'SPECIALIZED', 'BASELINE_COMPARATOR'")
    trajectory_reason: str = Field(default="", description="Defensible rationale for the assigned trajectory")
    growth_rate: float = Field(default=0.0, description="Percentage growth across period")
    confidence: float = Field(default=0.90, description="Confidence in trajectory assessment")
    yearly_distribution: List[YearlyFrequency] = Field(default_factory=list)
    top_paper_ids: List[str] = Field(default_factory=list)


class DatasetTrend(BaseModel):
    """Trend and concentration profile for a benchmark dataset."""
    name: str = Field(description="Canonical dataset name")
    modality: Optional[str] = Field(default=None, description="Data modality / task domain")
    raw_aliases: List[str] = Field(default_factory=list, description="Raw extracted aliases")
    total_occurrences: int = Field(description="Total papers using this dataset")
    paper_percentage: float = Field(description="Percentage of total corpus using this dataset")
    is_benchmark_monopoly: bool = Field(default=False, description="True if dataset accounts for >= 25% corpus share")
    is_synthetic: bool = Field(default=False, description="True if synthetic benchmark cohort")
    yearly_distribution: List[YearlyFrequency] = Field(default_factory=list)
    top_paper_ids: List[str] = Field(default_factory=list)


class DatasetDiversityMetrics(BaseModel):
    """Corpus-level benchmark diversity and validation metrics (Phase 8)."""
    hhi: float = Field(description="Herfindahl-Hirschman Index (0.0 to 1.0)")
    hhi_interpretation: str = Field(default="Diversified", description="'Highly Concentrated (Monopoly Risk)', 'Moderately Concentrated', 'Diversified'")
    synthetic_dataset_ratio: float = Field(default=0.0, description="Proportion of benchmarks that are synthetic")
    external_validation_ratio: float = Field(default=0.0, description="Proportion of papers evaluating on external/multi-site benchmarks")
    single_dataset_paper_ratio: float = Field(default=0.0, description="Proportion of papers using only 1 benchmark")
    top_1_dataset_share: float = Field(default=0.0)
    top_3_dataset_share: float = Field(default=0.0)


class ClusterTrendProfile(BaseModel):
    """Method and dataset distributions within a specific taxonomy cluster (Phase 9 Affinity)."""
    cluster_id: str
    cluster_name: str
    total_papers: int
    dominant_method_family: str
    emerging_paradigm: str
    top_methods: List[Dict[str, Any]] = Field(default_factory=list)
    top_datasets: List[Dict[str, Any]] = Field(default_factory=list)
    persistent_limitations: List[str] = Field(default_factory=list)
    supporting_paper_ids: List[str] = Field(default_factory=list)


class ResearchGap(BaseModel):
    """Evidence-grounded cross-paper research gap (Phase 10)."""
    gap_id: str
    title: str
    statement: str
    category: str = Field(description="'validation_deficit', 'modality_gap', 'scalability_bottleneck', 'generalization_limit', 'safety_oversight'")
    supporting_papers: List[str] = Field(default_factory=list)
    supporting_evidence_quotes: List[str] = Field(default_factory=list)
    confidence: float = 0.90
    why_insufficient: str = Field(description="Explanation of why current methodologies remain insufficient")


class TrendRunManifest(BaseModel):
    """Corpus-level trend analysis manifest."""
    run_id: str
    timestamp: str
    corpus_mode: str = Field(default="SNAPSHOT", description="'SNAPSHOT' (single year) or 'LONGITUDINAL' (multi-year)")
    total_papers: int
    year_range: List[int]
    total_unique_methods: int
    total_unique_datasets: int
    benchmark_metrics: DatasetDiversityMetrics
    emerging_methods: List[MethodTrend] = Field(default_factory=list)
    top_methods: List[MethodTrend] = Field(default_factory=list)
    top_datasets: List[DatasetTrend] = Field(default_factory=list)
    cluster_profiles: List[ClusterTrendProfile] = Field(default_factory=list)
    research_gaps: List[ResearchGap] = Field(default_factory=list)
