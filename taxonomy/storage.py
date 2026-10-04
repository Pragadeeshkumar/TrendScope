import os
import json
import sqlite3
import logging
from datetime import datetime
from taxonomy.models import Taxonomy, ClusterLabel

logger = logging.getLogger("trendscope.taxonomy.storage")

def init_taxonomy_table(db_path: str = "data/trendscope.db") -> None:
    """Initializes the SQLite taxonomies table if it doesn't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS taxonomies (
                taxonomy_id TEXT PRIMARY KEY,
                retrieval_run_id TEXT,
                domain TEXT,
                embedding_model TEXT,
                clustering_algorithm TEXT,
                labeling_model TEXT,
                clusters TEXT,
                noise_paper_ids TEXT,
                metrics TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()
        logger.debug("Taxonomies database table initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize taxonomies table: {e}")
        raise e
    finally:
        conn.close()

def save_taxonomy(taxonomy: Taxonomy, db_path: str = "data/trendscope.db") -> None:
    """
    Saves the taxonomy object to a JSON file and SQLite database.
    """
    init_taxonomy_table(db_path)
    
    # 1. Save to JSON file
    json_dir = "data/taxonomy"
    os.makedirs(json_dir, exist_ok=True)
    json_path = os.path.join(json_dir, f"taxonomy_{taxonomy.retrieval_run_id}.json")
    
    # Convert model to dict
    tax_dict = taxonomy.model_dump()
    
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(tax_dict, f, indent=4, ensure_ascii=False)
        logger.info(f"Taxonomy JSON saved successfully to {json_path}")
    except Exception as e:
        logger.error(f"Failed to save taxonomy JSON: {e}")
        
    # 2. Save to SQLite database
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Serialize fields to JSON strings
        clusters_json = json.dumps(tax_dict["clusters"], ensure_ascii=False)
        noise_json = json.dumps(tax_dict["noise_paper_ids"], ensure_ascii=False)
        metrics_json = json.dumps(tax_dict["metrics"], ensure_ascii=False)
        timestamp = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO taxonomies (
                taxonomy_id, retrieval_run_id, domain, embedding_model, 
                clustering_algorithm, labeling_model, clusters, 
                noise_paper_ids, metrics, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            taxonomy.taxonomy_id,
            taxonomy.retrieval_run_id,
            taxonomy.domain,
            taxonomy.embedding_model,
            taxonomy.clustering_algorithm,
            taxonomy.labeling_model,
            clusters_json,
            noise_json,
            metrics_json,
            timestamp
        ))
        conn.commit()
        logger.info(f"Taxonomy {taxonomy.taxonomy_id} saved to SQLite table.")
    except Exception as e:
        logger.error(f"Failed to save taxonomy in SQLite: {e}")
        raise e
    finally:
        conn.close()
        
    # 3. Automatically export Markdown Summary Report
    try:
        export_taxonomy_markdown(taxonomy, db_path)
    except Exception as e:
        logger.warning(f"Failed to export taxonomy markdown report: {e}")

def export_taxonomy_markdown(taxonomy: Taxonomy, db_path: str = "data/trendscope.db") -> str:
    """Exports a formatted Markdown summary report for the taxonomy."""
    run_id = taxonomy.retrieval_run_id
    domain = taxonomy.domain
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT paper_id, title FROM papers WHERE run_id = ? AND (fulltext_resolved = 1 OR pdf_path IS NOT NULL)", (run_id,))
    titles = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    
    total_papers = max(1, len(titles))
    duration = taxonomy.metrics.get("duration_seconds", 0.0)
    
    md_lines = []
    md_lines.append("# TrendScope Autonomous Research Discovery Report")
    md_lines.append(f"**Research Domain:** `{domain}`  ")
    md_lines.append(f"**Retrieval Run ID:** `{run_id}`  ")
    md_lines.append(f"**Taxonomy ID:** `{taxonomy.taxonomy_id}`  ")
    md_lines.append(f"**Embedding Model:** `{taxonomy.embedding_model}`  ")
    md_lines.append(f"**Total Papers:** `{total_papers}` Full-Text PDFs  ")
    md_lines.append(f"**Total Discovered Clusters:** `{len(taxonomy.clusters)}`  ")
    md_lines.append(f"**Remaining Unclustered Noise:** `{len(taxonomy.noise_paper_ids)}` papers ({len(taxonomy.noise_paper_ids)/total_papers*100:.1f}%)  ")
    md_lines.append(f"**Overall Silhouette Score:** `{taxonomy.metrics.get('silhouette_score', 0.0):+.4f}`  ")
    md_lines.append(f"**System Confidence:** `{taxonomy.metrics.get('system_confidence', 0.0):.4f}`  ")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## ⏱️ 1. Execution Timing Breakdown")
    md_lines.append("")
    md_lines.append("| Stage | Duration (Seconds) | Formatted Time | Description |")
    md_lines.append("| :--- | :---: | :---: | :--- |")
    md_lines.append(f"| **Taxonomy Induction & Discovery** | `{duration:.2f}s` | ~{int(duration//60)}m {int(duration%60)}s | SPECTER2/BGE embedding, UMAP manifold reduction & HDBSCAN clustering |")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## 📊 2. Discovered Research Taxonomy Overview")
    md_lines.append("")
    md_lines.append("| Cluster ID | Discovered Research Sub-Field | Paper Count | % of Corpus | Intra-Cluster Similarity | Top Representative Landmark Paper |")
    md_lines.append("| :---: | :--- | :---: | :---: | :---: | :--- |")
    
    for cl in taxonomy.clusters:
        cid = cl.cluster_id
        pids = cl.paper_ids
        label = cl.label or f"Cluster {cid}"
        intra = cl.average_intra_similarity or 1.0
        first_p = pids[0] if pids else ""
        first_title = titles.get(first_p, "Unknown")
        pct = len(pids) / total_papers * 100
        md_lines.append(f"| **Cluster {cid}** | {label} | **{len(pids)}** | {pct:.1f}% | `{intra:.4f}` | *{first_title[:50]}...* |")
        
    noise_count = len(taxonomy.noise_paper_ids)
    noise_pct = noise_count / total_papers * 100
    md_lines.append(f"| **Noise / Unassigned** | Truly Unclustered Outliers | **{noise_count}** | {noise_pct:.1f}% | `N/A` | *Isolated, non-overlapping preprints* |")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## 🔬 3. Detailed Cluster Breakdown & Landmark Papers")
    md_lines.append("")
    
    for cl in taxonomy.clusters:
        cid = cl.cluster_id
        pids = cl.paper_ids
        label = cl.label or f"Cluster {cid}"
        desc = cl.description or ""
        intra = cl.average_intra_similarity or 1.0
        pct = len(pids) / total_papers * 100
        
        md_lines.append(f"### 🔷 Cluster {cid}: {label}")
        md_lines.append(f"* **Paper Count:** `{len(pids)} papers` ({pct:.1f}% of corpus)")
        md_lines.append(f"* **Average Intra-Cluster Similarity:** `{intra:.4f}`")
        if desc:
            md_lines.append(f"* **Description:** {desc}")
        if cl.dominant_methods:
            md_lines.append(f"* **Key Methods & Concepts:** {', '.join(cl.dominant_methods)}")
        md_lines.append(f"* **Representative Landmark Papers:**")
        for idx, pid in enumerate(pids[:4]):
            t = titles.get(pid, "Unknown")
            md_lines.append(f"  {idx+1}. `[{pid}]` **{t}**")
        md_lines.append("")
        
    out_md_path = f"data/taxonomy/taxonomy_output_{run_id}.md"
    os.makedirs(os.path.dirname(out_md_path), exist_ok=True)
    with open(out_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    logger.info(f"Taxonomy Markdown Report generated at {out_md_path}")
    return out_md_path

def load_taxonomy(run_id: str, db_path: str = "data/trendscope.db") -> Taxonomy | None:
    """
    Loads a taxonomy object for a given retrieval run ID from SQLite or JSON cache.
    """
    # Try from SQLite first
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT taxonomy_id, retrieval_run_id, domain, embedding_model, 
                       clustering_algorithm, labeling_model, clusters, 
                       noise_paper_ids, metrics
                FROM taxonomies
                WHERE retrieval_run_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (run_id,))
            row = cursor.fetchone()
            if row:
                # Deserialize
                clusters = [ClusterLabel(**c) for c in json.loads(row[6])]
                noise_paper_ids = json.loads(row[7])
                metrics = json.loads(row[8])
                
                return Taxonomy(
                    taxonomy_id=row[0],
                    retrieval_run_id=row[1],
                    domain=row[2],
                    embedding_model=row[3],
                    clustering_algorithm=row[4],
                    labeling_model=row[5],
                    clusters=clusters,
                    noise_paper_ids=noise_paper_ids,
                    metrics=metrics
                )
        except Exception as e:
            logger.warning(f"Failed to load taxonomy from SQLite: {e}. Trying JSON...")
        finally:
            conn.close()
            
    # Try from JSON file
    json_path = f"data/taxonomy/taxonomy_{run_id}.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Reconstruct Pydantic
            clusters = [ClusterLabel(**c) for c in data.get("clusters", [])]
            return Taxonomy(
                taxonomy_id=data["taxonomy_id"],
                retrieval_run_id=data["retrieval_run_id"],
                domain=data["domain"],
                embedding_model=data["embedding_model"],
                clustering_algorithm=data["clustering_algorithm"],
                labeling_model=data["labeling_model"],
                clusters=clusters,
                noise_paper_ids=data.get("noise_paper_ids", []),
                metrics=data.get("metrics", {})
            )
        except Exception as e:
            logger.error(f"Failed to load taxonomy JSON: {e}")
            
    return None
