from pydantic import BaseModel, Field

class PaperInput(BaseModel):
    paper_id: str
    title: str
    abstract: str | None = None
    publication_year: int | None = None
    source: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pdf_path: str | None = None

class PaperEmbedding(BaseModel):
    paper_id: str
    model_name: str
    dimension: int
    vector: list[float]

class ClusterResult(BaseModel):
    cluster_id: int
    paper_ids: list[str]
    size: int
    centroid: list[float] | None = None
    silhouette_score: float | None = None
    average_intra_similarity: float | None = None

class ClusterLabel(BaseModel):
    cluster_id: int
    label: str = Field(description="A concise category label for the research sub-problem")
    description: str = Field(description="A detailed description of the common research problem or direction")
    dominant_methods: list[str] = Field(default_factory=list, description="List of primary methods, tools, or models used in this cluster")
    representative_paper_ids: list[str] = Field(default_factory=list, description="IDs of representative papers used to label this cluster")
    paper_ids: list[str] = Field(default_factory=list, description="IDs of all papers assigned to this cluster")
    size: int = Field(default=0, description="Number of papers in the cluster")
    average_intra_similarity: float | None = Field(default=None, description="Average pairwise cosine similarity within the cluster")
    centroid: list[float] | None = Field(default=None, description="Centroid embedding vector")
    confidence: float = Field(default=0.85, description="Self-assessed labeling confidence score in range [0, 1]")
    rationale: str = Field(default="", description="Brief explanation of how the label was inferred from the papers")

class Taxonomy(BaseModel):
    taxonomy_id: str
    retrieval_run_id: str
    domain: str
    embedding_model: str
    clustering_algorithm: str
    labeling_model: str
    clusters: list[ClusterLabel]
    noise_paper_ids: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
