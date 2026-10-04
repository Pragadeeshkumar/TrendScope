import os
import sqlite3
import uuid
import logging
from taxonomy.models import PaperInput, Taxonomy, ClusterLabel, ClusterResult
from taxonomy.embeddings import generate_embeddings
from taxonomy.clustering import run_clustering
from taxonomy.representatives import select_representative_papers
from taxonomy.labeling import label_cluster
from taxonomy.validator import validate_taxonomy_metrics
from taxonomy.storage import save_taxonomy

logger = logging.getLogger("trendscope.taxonomy.pipeline")

def load_papers_from_db(
    run_id: str, 
    db_path: str = "data/trendscope.db",
    resolved_only: bool = True
) -> tuple[list[PaperInput], str]:
    """
    Loads papers and query domain for a given run ID from the SQLite database or manifest JSON fallback.
    If resolved_only is True, selects only papers with downloaded full-text PDFs.
    """
    manifest_path = f"data/manifest_{run_id}.json"
    if os.path.exists(manifest_path):
        import json
        with open(manifest_path, "r", encoding="utf-8") as f:
            m_data = json.load(f)
        domain = m_data.get("original_query", f"Research analysis for {run_id}")
        raw_papers = m_data.get("selected_papers", m_data.get("papers", []))
        papers = []
        for p in raw_papers:
            pdf_path = p.get("pdf_path")
            if resolved_only and not pdf_path:
                continue
            papers.append(PaperInput(
                paper_id=p.get("paper_id"),
                title=p.get("title", ""),
                abstract=p.get("abstract", ""),
                publication_year=p.get("publication_year") or p.get("year", 2026),
                source=p.get("source", "arxiv"),
                doi=p.get("doi"),
                arxiv_id=p.get("arxiv_id"),
                pdf_path=pdf_path
            ))
        if papers:
            logger.info(f"Loaded {len(papers)} papers from manifest '{manifest_path}' (domain: '{domain}')")
            return papers, domain

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
        
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # 1. Fetch domain query
        cursor.execute("SELECT original_query FROM retrieval_runs WHERE run_id = ?", (run_id,))
        row_run = cursor.fetchone()
        if not row_run:
            raise ValueError(f"Retrieval run ID '{run_id}' not found in database.")
        domain = row_run[0]
        
        # 2. Fetch paper candidates (PDFs only if resolved_only=True)
        sql = """
            SELECT paper_id, title, abstract, publication_year, venue, doi, arxiv_id, pdf_path
            FROM papers
            WHERE run_id = ?
        """
        if resolved_only:
            sql += " AND (fulltext_resolved = 1 OR pdf_path IS NOT NULL)"
            
        cursor.execute(sql, (run_id,))
        rows = cursor.fetchall()
        
        # Fallback to all papers if resolved_only returned 0 (e.g. if PDFs were not downloaded)
        if not rows and resolved_only:
            logger.warning(f"No resolved PDFs found for run '{run_id}'. Falling back to all candidate papers.")
            cursor.execute("""
                SELECT paper_id, title, abstract, publication_year, venue, doi, arxiv_id, pdf_path
                FROM papers
                WHERE run_id = ?
            """, (run_id,))
            rows = cursor.fetchall()
            
        papers = []
        for r in rows:
            papers.append(PaperInput(
                paper_id=r[0],
                title=r[1],
                abstract=r[2],
                publication_year=r[3],
                source=r[4],
                doi=r[5],
                arxiv_id=r[6],
                pdf_path=r[7]
            ))
            
        logger.info(f"Loaded {len(papers)} papers for run '{run_id}' (resolved_only={resolved_only}, domain: '{domain}')")
        return papers, domain
        
    finally:
        conn.close()

def build_taxonomy(
    run_id: str,
    min_cluster_size: int = None,
    min_samples: int = None,
    embedding_model: str = "allenai/specter2",
    labeling_model: str = "gemini-2.5-flash",
    db_path: str = "data/trendscope.db",
    central_count: int = 6,
    diverse_count: int = 2,
    force_regenerate_embeddings: bool = False,
    resolved_only: bool = True
) -> Taxonomy:
    """
    Orchestrates the single-level Taxonomy Induction stage pipeline strictly following TAXONOMY_IMPLEMENTATION_PLAN.md:
    1. Loads papers (PDFs only when resolved_only=True).
    2. Generates SPECTER2 embeddings on Title + Abstract.
    3. Runs HDBSCAN clustering and records unclustered noise.
    4. Selects landmark representative papers (central + diverse).
    5. Queries Gemini to generate structured cluster labels.
    6. Validates taxonomy metrics, provenance, and system confidence.
    7. Persists taxonomy to JSON and SQLite.
    """
    import time
    start_time = time.time()
    logger.info(f"Starting Taxonomy Induction stage for run ID '{run_id}' using single-level HDBSCAN (min_cluster_size={min_cluster_size}, min_samples={min_samples})...")
    
    # 1. Load papers and domain (PDFs only)
    papers, domain = load_papers_from_db(run_id, db_path, resolved_only=resolved_only)
    if not papers:
        raise ValueError(f"No paper candidates found for run ID '{run_id}'. Cannot build taxonomy.")
        
    # Adjust min_cluster_size if dataset is too small
    if min_cluster_size is not None and len(papers) < min_cluster_size:
        logger.warning(f"Paper count ({len(papers)}) is less than min_cluster_size ({min_cluster_size}). Adjusting min_cluster_size to {max(2, len(papers)//2)}.")
        min_cluster_size = max(2, len(papers)//2)
        
    # 2. Generate dense semantic embeddings (Title + Abstract)
    embeddings_mapping = generate_embeddings(
        papers=papers,
        run_id=run_id,
        model_name=embedding_model,
        force_regenerate=force_regenerate_embeddings,
        title_only=False
    )
    
    # 3. Pure HDBSCAN clustering
    cluster_results, noise_paper_ids = run_clustering(
        embeddings_mapping=embeddings_mapping,
        min_cluster_size=min_cluster_size,
        min_samples=min_samples
    )

    # 4. Generate cluster labels using Gemini agent
    cluster_labels = []
    papers_dict = {p.paper_id: p for p in papers}
    
    for idx, c in enumerate(cluster_results):
        rep_pids = select_representative_papers(
            paper_ids=c.paper_ids,
            embeddings_mapping=embeddings_mapping,
            centroid=c.centroid,
            central_count=central_count,
            diverse_count=diverse_count
        )
        
        representative_papers_meta = []
        for pid in rep_pids:
            p = papers_dict[pid]
            representative_papers_meta.append({
                "paper_id": p.paper_id,
                "title": p.title,
                "abstract": p.abstract or ""
            })
            
        if idx > 0:
            import time
            time.sleep(4.0)
            
        label_obj = label_cluster(
            domain=domain,
            cluster_id=c.cluster_id,
            cluster_size=c.size,
            representative_papers=representative_papers_meta,
            model_name=labeling_model
        )
        label_obj.paper_ids = c.paper_ids
        label_obj.size = c.size
        label_obj.average_intra_similarity = c.average_intra_similarity
        label_obj.centroid = c.centroid
        cluster_labels.append(label_obj)
        
    logger.info(f"HDBSCAN discovered {len(cluster_labels)} valid research clusters. {len(noise_paper_ids)} papers remain as unclustered noise.")

    # 5. Compute taxonomy metrics and validation
    metrics = validate_taxonomy_metrics(
        clusters=cluster_results,
        labels=cluster_labels,
        embeddings_mapping=embeddings_mapping,
        total_papers=len(papers),
        noise_count=len(noise_paper_ids)
    )
    
    elapsed_time = time.time() - start_time
    metrics["duration_seconds"] = elapsed_time
    
    # 6. Assemble Taxonomy Pydantic model
    taxonomy = Taxonomy(
        taxonomy_id=str(uuid.uuid4())[:8],
        retrieval_run_id=run_id,
        domain=domain,
        embedding_model=embedding_model,
        clustering_algorithm=f"HDBSCAN(min_cluster_size={min_cluster_size},min_samples={min_samples})",
        labeling_model=labeling_model,
        clusters=cluster_labels,
        noise_paper_ids=noise_paper_ids,
        metrics=metrics
    )
    
    # 7. Persist to storage
    save_taxonomy(taxonomy, db_path=db_path)
    
    logger.info(f"Taxonomy Induction complete! Taxonomy ID: {taxonomy.taxonomy_id}")
    return taxonomy
