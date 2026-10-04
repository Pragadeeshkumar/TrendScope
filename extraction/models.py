"""
Data models and Pydantic schemas for Stage 3: Research Information Extraction.
Enforces strict provenance tracking (sentence ID, page number, section, verbatim quote).
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ProvenancePointer(BaseModel):
    """Pointer to the exact location and verbatim evidence in the source PDF."""
    sentence_id: str = Field(description="Unique sentence identifier, e.g. S42")
    page: int = Field(description="1-indexed page number in the PDF where the sentence appears")
    section: str = Field(description="Detected section name, e.g. 'Methodology', 'Experiments'")
    quote: str = Field(description="Verbatim or near-verbatim quote from the source text")


class ExtractedMethod(BaseModel):
    """A method, algorithm, or architecture extracted from the paper."""
    name: str = Field(description="Name of the method/algorithm (e.g. 'Vision Transformer', 'Swin-UNet')")
    normalized_name: Optional[str] = Field(default=None, description="Standardized canonical name")
    type: str = Field(default="model", description="Category: 'model', 'algorithm', 'loss_function', 'architecture', 'backbone', 'technique'")
    role: str = Field(default="proposed", description="Role: 'proposed', 'baseline', 'backbone', 'component'")
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")


class ExtractedDataset(BaseModel):
    """A benchmark dataset extracted from the paper."""
    name: str = Field(description="Name of the dataset (e.g. 'Synapse', 'ACDC', 'BraTS 2021')")
    normalized_name: Optional[str] = Field(default=None, description="Standardized canonical name")
    modality: Optional[str] = Field(default=None, description="Data modality (e.g. '3D CT', 'MRI', 'Natural Images', 'Text')")
    usage: str = Field(default="evaluation", description="Usage role: 'training', 'evaluation', 'benchmark', 'pretraining', 'validation'")
    samples: Optional[str] = Field(default=None, description="Number of samples or subjects if mentioned")
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")


class ExtractedLimitation(BaseModel):
    """An explicit limitation or weakness acknowledged by the authors."""
    text: str = Field(description="Concise description of the limitation")
    category: str = Field(
        default="general", 
        description="Category: 'computational_cost', 'data_scarcity', 'generalization', 'scalability', 'interpretability', 'annotation_overhead', 'hardware_dependence', 'general'"
    )
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")


class ExtractedFutureWork(BaseModel):
    """A future research direction proposed by the authors."""
    text: str = Field(description="Concise description of the proposed future work")
    category: Optional[str] = Field(default="methodological_extension", description="Category of future work")
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")


class ExtractedFinding(BaseModel):
    """A key empirical finding, claim, or metric result."""
    finding: str = Field(description="Key takeaway or scientific claim")
    metric: Optional[str] = Field(default=None, description="Metric name (e.g. 'Dice Score', 'Accuracy', 'mIoU')")
    result: Optional[str] = Field(default=None, description="Numerical result or comparison (e.g. '79.13% (+2.4%)')")
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")


class ExtractedLiteratureSource(BaseModel):
    """A literature search database or academic indexing engine used for reviews."""
    name: str = Field(description="Name of the search source (e.g. 'PubMed', 'Scopus', 'IEEE Xplore', 'Embase')")
    normalized_name: Optional[str] = Field(default=None, description="Standardized canonical name")
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")


class PaperExtractionResult(BaseModel):
    """Complete structured extraction result for a single scientific paper."""
    paper_id: str = Field(description="Unique paper identifier")
    title: str = Field(description="Paper title")
    publication_year: Optional[int] = Field(default=None, description="Publication year")
    pdf_path: Optional[str] = Field(default=None, description="Local path to PDF file")
    status: str = Field(default="SUCCESS", description="'SUCCESS', 'PARTIAL', 'NO_PDF', 'ERROR'")
    error_message: Optional[str] = Field(default=None, description="Error message if extraction failed")
    
    methods: List[ExtractedMethod] = Field(default_factory=list)
    datasets: List[ExtractedDataset] = Field(default_factory=list)
    literature_sources: List[ExtractedLiteratureSource] = Field(default_factory=list)
    limitations: List[ExtractedLimitation] = Field(default_factory=list)
    future_work: List[ExtractedFutureWork] = Field(default_factory=list)
    findings: List[ExtractedFinding] = Field(default_factory=list)


class ConfidenceScores(BaseModel):
    """Multi-dimensional confidence scores for evidence verification and ranking."""
    extraction_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    classification_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    provenance_confidence: float = Field(default=1.00, ge=0.0, le=1.0)
    normalization_confidence: float = Field(default=0.85, ge=0.0, le=1.0)

    @property
    def composite_score(self) -> float:
        """Harmonic/weighted composite confidence."""
        return (
            0.35 * self.extraction_confidence +
            0.25 * self.classification_confidence +
            0.25 * self.provenance_confidence +
            0.15 * self.normalization_confidence
        )


class ScientificEntity(BaseModel):
    """
    Typed, evidence-grounded scientific entity (method, dataset, literature source).
    Captures fine-grained mention semantics and adoption roles.
    """
    entity_id: str = Field(description="Unique entity occurrence identifier, e.g. ent_p1_s3_m1")
    paper_id: str = Field(description="Source paper identifier")
    raw_name: str = Field(description="Verbatim entity name in paper text")
    canonical_name: Optional[str] = Field(default=None, description="Resolved canonical ontology name")
    entity_type: str = Field(description="'method', 'dataset', or 'literature_source'")
    subtype: Optional[str] = Field(default=None, description="Fine-grained category: algorithm, model, architecture, benchmark, cohort, index")
    role: str = Field(
        default="proposed",
        description="Mention semantics: 'proposed', 'used', 'trained', 'fine-tuned', 'evaluated', 'baseline', 'compared', 'criticized', 'extended', 'mentioned', 'database'"
    )
    provenance: ProvenancePointer = Field(description="Exact sentence and page location")
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)


class ScientificFinding(BaseModel):
    """Empirical finding or claim linking methods, baselines, and metrics."""
    claim_id: str = Field(description="Unique claim identifier, e.g. clm_p1_s12")
    paper_id: str = Field(description="Source paper identifier")
    claim_type: str = Field(default="performance", description="'performance', 'comparison', 'capability', 'efficiency', 'empirical'")
    text: str = Field(description="Textual representation of the claim or finding")
    method_entity_ids: List[str] = Field(default_factory=list, description="IDs of proposed or evaluated methods involved")
    baseline_entity_ids: List[str] = Field(default_factory=list, description="IDs of comparison baseline methods")
    dataset_entity_ids: List[str] = Field(default_factory=list, description="IDs of datasets or benchmarks on which claim was demonstrated")
    metric: Optional[str] = Field(default=None, description="Metric name (e.g. AUROC, Accuracy, Dice, Latency)")
    value: Optional[float] = Field(default=None, description="Numerical metric value")
    direction: Optional[str] = Field(default=None, description="'improvement', 'parity', 'degradation', 'observation'")
    provenance: ProvenancePointer = Field(description="Verbatim sentence provenance")
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)


class ScientificRelation(BaseModel):
    """Typed relationship between scientific entities extracted from paper evidence."""
    relation_id: str = Field(description="Unique relation identifier")
    paper_id: str = Field(description="Source paper identifier")
    source_entity_id: str = Field(description="ID of source ScientificEntity")
    target_entity_id: str = Field(description="ID of target ScientificEntity")
    relation_type: str = Field(
        description="'evaluated_on', 'outperforms', 'extends', 'fine_tunes', 'compares_with', 'criticizes', 'integrates_with'"
    )
    evidence_sentence_id: Optional[str] = Field(default=None)
    quote: Optional[str] = Field(default=None)
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)


class ScientificLimitation(BaseModel):
    """Evidence-grounded scientific limitation linked to affected entities."""
    limitation_id: str = Field(description="Unique limitation identifier")
    paper_id: str = Field(description="Source paper identifier")
    category: str = Field(
        default="general",
        description="'generalization', 'computational_cost', 'data_scarcity', 'scalability', 'interpretability', 'safety', 'general'"
    )
    text: str = Field(description="Verbatim or summary limitation text")
    affected_entity_ids: List[str] = Field(default_factory=list, description="Entity IDs of models/methods affected by limitation")
    provenance: ProvenancePointer = Field(description="Exact sentence location")
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)


class ScientificFutureWork(BaseModel):
    """Proposed future research direction linked to target methodologies or populations."""
    future_work_id: str = Field(description="Unique future work identifier")
    paper_id: str = Field(description="Source paper identifier")
    category: str = Field(
        default="methodological_extension",
        description="'external_validation', 'scale_up', 'multimodal_extension', 'clinical_trial', 'methodological_extension'"
    )
    text: str = Field(description="Proposed research direction text")
    target: Optional[str] = Field(default=None, description="Specific target cohort, architecture, or benchmark")
    provenance: ProvenancePointer = Field(description="Exact sentence location")
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)


class PaperEvidenceRecord(BaseModel):
    """Unified container for all validated scientific evidence of a single paper."""
    paper_id: str
    title: str
    publication_year: Optional[int] = None
    entities: List[ScientificEntity] = Field(default_factory=list)
    findings: List[ScientificFinding] = Field(default_factory=list)
    relations: List[ScientificRelation] = Field(default_factory=list)
    limitations: List[ScientificLimitation] = Field(default_factory=list)
    future_work: List[ScientificFutureWork] = Field(default_factory=list)


class ExtractionRunManifest(BaseModel):
    """Corpus-level container for a full Stage 3 extraction run."""
    run_id: str
    timestamp: str
    total_papers: int
    successful_extractions: int
    failed_extractions: int
    total_methods_found: int
    total_datasets_found: int
    total_limitations_found: int
    total_future_work_found: int
    papers: List[PaperExtractionResult] = Field(default_factory=list)
