import os
import sys
# Configure stdout to use UTF-8 to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import logging
from dotenv import load_dotenv

def setup_logging(verbose: bool = False) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler("data/taxonomy.log", mode="a", encoding="utf-8")
        ]
    )
    # Mute chatty libraries
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TrendScope Taxonomy Induction CLI tool (Single-level HDBSCAN on Title+Abstract)."
    )
    parser.add_argument(
        "run_id",
        type=str,
        help="The retrieval run ID to cluster and induce taxonomy from."
    )
    parser.add_argument(
        "-c", "--min-cluster-size",
        type=int,
        default=None,
        help="HDBSCAN min_cluster_size parameter (default: None for adaptive search)."
    )
    parser.add_argument(
        "-s", "--min-samples",
        type=int,
        default=None,
        help="HDBSCAN min_samples parameter (default: None for adaptive search)."
    )
    parser.add_argument(
        "-e", "--embedding-model",
        type=str,
        default="allenai/specter2",
        help="HuggingFace model for document embeddings (default: allenai/specter2)."
    )
    parser.add_argument(
        "-l", "--labeling-model",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini API model for cluster interpretation (default: gemini-2.5-flash)."
    )
    parser.add_argument(
        "--force-embeddings",
        action="store_true",
        help="Regenerate and overwrite cached paper embeddings."
    )
    parser.add_argument(
        "--all-candidates",
        action="store_true",
        help="Cluster all retrieved candidates instead of only the downloaded full-text PDFs (default: False, PDFs only)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed debug logging."
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    setup_logging(args.verbose)
    
    # Ensure an API key is available
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY_1") or os.environ.get("GROQ_API_KEY")):
        print("Error: Neither GEMINI_API_KEY nor GROQ_API_KEY is configured.")
        print("Please add it to your '.env' file before running the taxonomy induction.")
        sys.exit(1)
        
    from taxonomy.pipeline import build_taxonomy
    
    try:
        taxonomy = build_taxonomy(
            run_id=args.run_id,
            min_cluster_size=args.min_cluster_size,
            min_samples=args.min_samples,
            embedding_model=args.embedding_model,
            labeling_model=args.labeling_model,
            force_regenerate_embeddings=args.force_embeddings,
            resolved_only=not args.all_candidates
        )
        
        # Output structured summary
        print("\n" + "="*50)
        print("           TAXONOMY INDUCTION COMPLETE")
        print("="*50)
        print(f"Taxonomy ID:          {taxonomy.taxonomy_id}")
        print(f"Retrieval Run ID:     {taxonomy.retrieval_run_id}")
        print(f"Domain:               \"{taxonomy.domain}\"")
        print(f"Embedding Model:      {taxonomy.embedding_model}")
        print(f"Clustering Algorithm: {taxonomy.clustering_algorithm}")
        print(f"Labeling Model:       {taxonomy.labeling_model}")
        print(f"Total Clusters:       {len(taxonomy.clusters)}")
        print(f"Noise Outliers:       {len(taxonomy.noise_paper_ids)}")
        duration = taxonomy.metrics.get("duration_seconds", 0.0)
        print(f"Time Taken:           {duration:.2f} seconds")
        
        print("\nDiscovered Research Categories:")
        for c in taxonomy.clusters:
            print(f"  Cluster {c.cluster_id}: {c.label} ({len(c.paper_ids)} papers)")
            if c.description:
                print(f"    - Description: {c.description[:90]}...")
            if c.dominant_methods:
                print(f"    - Methods:     {', '.join(c.dominant_methods)}")
                
        if taxonomy.noise_paper_ids:
            print(f"\nUnclustered Noise: {len(taxonomy.noise_paper_ids)} papers (strictly unassigned)")
            
        print("\nSaved Artifacts:")
        print(f"  📄 Markdown Report: data/taxonomy/taxonomy_output_{args.run_id}.md")
        print(f"  📋 JSON Manifest:   data/taxonomy/taxonomy_{args.run_id}.json")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\nError running taxonomy induction pipeline: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
