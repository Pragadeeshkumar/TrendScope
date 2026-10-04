import os
import sys
import shutil
import time
import argparse
import logging
import warnings
warnings.filterwarnings("ignore")
import json
import sqlite3
import numpy as np
from dotenv import load_dotenv

# Configure stdout to use UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def setup_logging(verbose: bool = False) -> None:
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/pdfs", exist_ok=True)
    os.makedirs("data/taxonomy/embeddings", exist_ok=True)
    
    file_handler = logging.FileHandler("data/trendscope.log", mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if verbose else logging.ERROR)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers = [file_handler, console_handler]
    
    # Silence chatty third-party loggers
    for logger_name in [
        "urllib3", "requests", "tenacity", "filelock", 
        "sentence_transformers", "httpx", "huggingface_hub", "google"
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

def clear_previous_data() -> None:
    """Safely resets the data directory for a fresh run."""
    print("🧹 Resetting data environment...")
    targets = [
        "data/trendscope.db", "data/retrieval.log", "data/taxonomy.log", 
        "data/trendscope.log", "data/pdfs", "data/taxonomy"
    ]
    for target in targets:
        try:
            if os.path.isfile(target):
                os.remove(target)
            elif os.path.isdir(target):
                shutil.rmtree(target)
        except Exception:
            pass
            
    # Clean manifests
    if os.path.exists("data"):
        for f in os.listdir("data"):
            if f.startswith("manifest_") and f.endswith(".json"):
                try:
                    os.remove(os.path.join("data", f))
                except Exception:
                    pass

    os.makedirs("data/pdfs", exist_ok=True)
    os.makedirs("data/taxonomy/embeddings", exist_ok=True)
    os.makedirs("scratch", exist_ok=True)
    print("✨ Clean workspace ready.\n")

def generate_markdown_report(run_id: str, domain: str, total_time: float, retrieval_time: float, taxonomy_time: float) -> str:
    """Generates a structured Markdown report of the discovered research taxonomy."""
    tax_path = f"data/taxonomy/taxonomy_{run_id}.json"
    emb_dir = "data/taxonomy/embeddings"
    emb_path = None
    if os.path.exists(emb_dir):
        for f in os.listdir(emb_dir):
            if f.startswith(f"embeddings_{run_id}") and f.endswith(".json"):
                emb_path = os.path.join(emb_dir, f)
                break
                
    if not os.path.exists(tax_path):
        return ""
        
    with open(tax_path, "r", encoding="utf-8") as f:
        tax = json.load(f)
        
    emb = {}
    if emb_path and os.path.exists(emb_path):
        with open(emb_path, "r", encoding="utf-8") as f:
            emb = json.load(f)
        
    conn = sqlite3.connect("data/trendscope.db")
    c = conn.cursor()
    c.execute("SELECT paper_id, title FROM papers WHERE run_id = ? AND (fulltext_resolved = 1 OR pdf_path IS NOT NULL)", (run_id,))
    titles = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    
    total_papers = max(1, len(titles))
    
    md_lines = []
    md_lines.append("# TrendScope Autonomous Research Discovery Report")
    md_lines.append(f"**Research Domain:** `{domain}`  ")
    md_lines.append(f"**Retrieval Run ID:** `{run_id}`  ")
    md_lines.append(f"**Taxonomy ID:** `{tax['taxonomy_id']}`  ")
    md_lines.append(f"**Total Papers:** `{total_papers}` Full-Text PDFs  ")
    md_lines.append(f"**Total Discovered Clusters:** `{len(tax['clusters'])}`  ")
    md_lines.append(f"**Remaining Unclustered Noise:** `{len(tax['noise_paper_ids'])}` papers ({len(tax['noise_paper_ids'])/total_papers*100:.1f}%)  ")
    md_lines.append(f"**Overall Silhouette Score:** `{tax['metrics'].get('silhouette_score', 0.0):+.4f}`  ")
    md_lines.append(f"**System Confidence:** `{tax['metrics'].get('system_confidence', 0.0):.4f}`  ")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## ⏱️ 1. Execution Timing Breakdown")
    md_lines.append("")
    md_lines.append("| Stage | Duration (Seconds) | Formatted Time | % of Runtime | Description |")
    md_lines.append("| :--- | :---: | :---: | :---: | :--- |")
    md_lines.append(f"| **Stage 1: Multi-Agent Retrieval** | `{retrieval_time:.2f}s` | ~{int(retrieval_time//60)}m {int(retrieval_time%60)}s | {retrieval_time/total_time*100:.1f}% | Multi-source search, MMR selection & PDF downloads |")
    md_lines.append(f"| **Stage 2: Taxonomy Induction** | `{taxonomy_time:.2f}s` | ~{int(taxonomy_time//60)}m {int(taxonomy_time%60)}s | {taxonomy_time/total_time*100:.1f}% | SPECTER2 embedding, HDBSCAN & noise subgroup analysis |")
    md_lines.append(f"| **Total End-to-End Runtime** | **`{total_time:.2f}s`** | **~{int(total_time//60)}m {int(total_time%60)}s** | **100.0%** | **Complete autonomous discovery** |")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## 📊 2. Discovered Research Taxonomy Overview")
    md_lines.append("")
    md_lines.append("| Cluster ID | Discovered Research Sub-Field | Paper Count | % of Corpus | Intra-Cluster Similarity | Top Representative Landmark Paper |")
    md_lines.append("| :---: | :--- | :---: | :---: | :---: | :--- |")
    
    for cl in tax["clusters"]:
        cid = cl["cluster_id"]
        pids = cl["paper_ids"]
        label = cl.get("label", f"Cluster {cid}")
        c_X = np.array([emb[p] for p in pids if p in emb])
        intra = float(np.mean(np.dot(c_X, c_X.T)[np.triu_indices(len(c_X), k=1)])) if len(c_X) > 1 else 1.0
        first_p = pids[0]
        first_title = titles.get(first_p, "Unknown")
        pct = len(pids) / total_papers * 100
        md_lines.append(f"| **Cluster {cid}** | {label} | **{len(pids)}** | {pct:.1f}% | `{intra:.4f}` | *{first_title[:50]}...* |")
        
    noise_count = len(tax["noise_paper_ids"])
    noise_pct = noise_count / total_papers * 100
    md_lines.append(f"| **Noise / Unassigned** | Truly Unclustered Outliers | **{noise_count}** | {noise_pct:.1f}% | `N/A` | *Isolated, non-overlapping preprints* |")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## 🔬 3. Detailed Cluster Breakdown & Landmark Papers")
    md_lines.append("")
    
    for cl in tax["clusters"]:
        cid = cl["cluster_id"]
        pids = cl["paper_ids"]
        label = cl.get("label", f"Cluster {cid}")
        desc = cl.get("description", "")
        c_X = np.array([emb[p] for p in pids if p in emb])
        intra = float(np.mean(np.dot(c_X, c_X.T)[np.triu_indices(len(c_X), k=1)])) if len(c_X) > 1 else 1.0
        pct = len(pids) / total_papers * 100
        
        md_lines.append(f"### 🔷 Cluster {cid}: {label}")
        md_lines.append(f"* **Paper Count:** `{len(pids)} papers` ({pct:.1f}% of corpus)")
        md_lines.append(f"* **Average Intra-Cluster Similarity:** `{intra:.4f}`")
        if desc:
            md_lines.append(f"* **Description:** {desc}")
        md_lines.append(f"* **Representative Landmark Papers (Sorted by Centroid Proximity):**")
        for idx, pid in enumerate(pids[:4]):
            t = titles.get(pid, "Unknown")
            md_lines.append(f"  {idx+1}. `[{pid}]` **{t}**")
        md_lines.append("")
        
    out_md_path = f"data/taxonomy/taxonomy_output_{run_id}.md"
    with open(out_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    return out_md_path

def main() -> None:
    load_dotenv(".env")
    
    parser = argparse.ArgumentParser(
        description="TrendScope: End-to-End Autonomous Research Corpus Retrieval & Taxonomy Discovery Pipeline."
    )
    parser.add_argument(
        "domain",
        type=str,
        nargs="?",
        default=None,
        help="The research domain or search query (e.g., 'Quantum Computing', 'Artificial Intelligence')."
    )
    parser.add_argument(
        "-n", "-t", "--papers",
        type=int,
        default=None,
        help="The target number of full-text PDF research papers to retrieve (default: 100)."
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear previous data before running."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging to console."
    )
    
    args = parser.parse_args()
    
    domain = args.domain
    if not domain:
        print("=" * 60)
        print("       TRENDSCOPE: END-TO-END RESEARCH DISCOVERY")
        print("=" * 60)
        domain = input("\n👉 Enter research domain / query: ").strip()
        while not domain:
            domain = input("Query cannot be empty. Enter research domain: ").strip()
            
    target_papers = args.papers
    if not target_papers:
        papers_input = input("👉 Enter target number of papers [Default: 100]: ").strip()
        if papers_input.isdigit():
            target_papers = int(papers_input)
        else:
            target_papers = 100
            
    setup_logging(verbose=args.verbose)
    
    if not args.no_clear:
        clear_previous_data()
        
    print("=" * 60)
    print(f"🚀 TRENDSCOPE AUTONOMOUS RESEARCH DISCOVERY")
    print(f"Domain:         '{domain}'")
    print(f"Target Papers:  {target_papers} Full-Text PDFs")
    print("=" * 60 + "\n")
    
    start_total = time.time()
    
    # Step 1: Multi-Agent Retrieval
    print(f"[1/3] 🔍 Searching sources and downloading {target_papers} verified PDFs...")
    start_retrieval = time.time()
    
    from retrieval.corpus import build_corpus
    run_id = build_corpus(
        domain=domain,
        target_size=target_papers,
        db_path="data/trendscope.db"
    )
    retrieval_time = time.time() - start_retrieval
    
    conn = sqlite3.connect("data/trendscope.db")
    c = conn.cursor()
    c.execute("SELECT count(*) FROM papers WHERE run_id = ? AND (fulltext_resolved = 1 OR pdf_path IS NOT NULL)", (run_id,))
    valid_pdf_count = c.fetchone()[0]
    conn.close()
    
    print(f"      ↳ Retrieved & verified {valid_pdf_count} PDFs in {retrieval_time:.1f}s")
    
    # Step 2: Full-Text Information Extraction (Stage 3)
    print(f"\n[2/3] 📑 Extracting structured methods, datasets, limitations, and future work (Stage 3)...")
    start_extraction = time.time()
    from extraction.pipeline import ExtractionPipeline
    extraction_pipe = ExtractionPipeline(db_path="data/trendscope.db", max_workers=4)
    extraction_manifest = extraction_pipe.run_for_run_id(run_id)
    extraction_time = time.time() - start_extraction
    print(
        f"      ↳ Extracted {extraction_manifest.total_methods_found} methods, "
        f"{extraction_manifest.total_datasets_found} datasets, "
        f"{extraction_manifest.total_limitations_found} limitations in {extraction_time:.1f}s"
    )
    
    # Step 3: Taxonomy Induction (Stage 4)
    print(f"\n[3/3] 🧠 Inducing semantic taxonomy & discovering research clusters (Stage 4)...")
    start_taxonomy = time.time()
    
    from taxonomy.pipeline import build_taxonomy
    taxonomy = build_taxonomy(
        run_id=run_id,
        resolved_only=True
    )
    taxonomy_time = time.time() - start_taxonomy
    total_time = time.time() - start_total
    
    print(f"      ↳ Discovered {len(taxonomy.clusters)} research categories in {taxonomy_time:.1f}s")
    
    # Step 4: Longitudinal Trend Analysis (Stage 5)
    print(f"\n[4/5] 📈 Computing longitudinal method and benchmark adoption trends (Stage 5)...")
    start_trends = time.time()
    from trends.pipeline import TrendPipeline
    trend_pipe = TrendPipeline(db_path="data/trendscope.db")
    trend_manifest = trend_pipe.run_for_run_id(run_id)
    trends_time = time.time() - start_trends
    print(
        f"      ↳ Analyzed {trend_manifest.total_unique_methods} methods, "
        f"{trend_manifest.total_unique_datasets} datasets (HHI: {trend_manifest.benchmark_concentration_hhi:.3f}) in {trends_time:.1f}s"
    )

    # Step 5: Research Limitation Evolution & Gap Detection (Stage 6)
    print(f"\n[5/5] 🎯 Tracking research limitation evolution & discovering open gaps (Stage 6)...")
    start_gaps = time.time()
    from gaps.pipeline import GapPipeline
    gap_pipe = GapPipeline(db_path="data/trendscope.db")
    gap_manifest = gap_pipe.run_for_run_id(run_id)
    gaps_time = time.time() - start_gaps
    print(
        f"      ↳ Discovered {gap_manifest.total_themes_discovered} limitation themes "
        f"({gap_manifest.open_unaddressed_gaps_count} open research gaps) in {gaps_time:.1f}s"
    )

    # Step 6: Markdown Report Generation
    total_time = time.time() - start_total
    out_md = generate_markdown_report(run_id, domain, total_time, retrieval_time, taxonomy_time)
    
    print("\n" + "=" * 60)
    print("🎉 END-TO-END RESEARCH ANALYSIS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print(f"Domain:              '{domain}'")
    print(f"Retrieval Run ID:    {run_id}")
    print(f"Taxonomy ID:         {taxonomy.taxonomy_id}")
    print(f"Full-Text PDFs:      {valid_pdf_count}")
    print(f"Valid Clusters:      {len(taxonomy.clusters)}")
    print(f"Methods Tracked:     {trend_manifest.total_unique_methods}")
    print(f"Datasets Tracked:    {trend_manifest.total_unique_datasets}")
    print(f"Limitation Themes:   {gap_manifest.total_themes_discovered}")
    print(f"Open Research Gaps:  {gap_manifest.open_unaddressed_gaps_count}")
    print("-" * 60)
    print(f"Retrieval Runtime:   {retrieval_time:.1f}s")
    print(f"Extraction Runtime:  {extraction_time:.1f}s")
    print(f"Taxonomy Runtime:    {taxonomy_time:.1f}s")
    print(f"Trends Runtime:      {trends_time:.1f}s")
    print(f"Gap Analysis Runtime:{gaps_time:.1f}s")
    print(f"Total Runtime:       {total_time:.1f}s (~{int(total_time//60)}m {int(total_time%60)}s)")
    print("-" * 60)
    print(f"📄 Markdown Report:  {out_md}")
    print(f"📋 Extraction JSON:  data/extracted/extracted_{run_id}.json")
    print(f"📋 Taxonomy JSON:    data/taxonomy/taxonomy_{run_id}.json")
    print(f"📋 Trends JSON:      data/trends/trends_{run_id}.json")
    print(f"📋 Gaps JSON:        data/gaps/gaps_{run_id}.json")
    print(f"💾 SQLite Database:  data/trendscope.db")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
