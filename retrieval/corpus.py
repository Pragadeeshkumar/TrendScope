import os
import logging
import time
import json
import uuid
from datetime import datetime
from retrieval.agents import plan_search
from retrieval.workers import execute_worker_queries
from retrieval.merger import merge_and_deduplicate
from retrieval.ranker import rank_candidates
from retrieval.selector import select_diverse_corpus, select_next_diverse_batch
from retrieval.resolver import resolve_corpus_pdfs
from retrieval.db import init_db, insert_run, insert_paper

logger = logging.getLogger("trendscope.corpus")

def build_corpus(domain: str, target_size: int = 150, db_path: str = "data/trendscope.db", start_year: int = None, end_year: int = None) -> None:
    """
    Orchestrates the entire Multi-Agent Corpus Retrieval pipeline:
    1. Plan search strategies (LLM / Rule-based).
    2. Retrieve papers from multiple workers concurrently with year filtering.
    3. Merge metadata and deduplicate deterministically.
    4. Rank candidates by semantic relevance (all-MiniLM-L6-v2 / TF-IDF).
    5. Select a diverse corpus subset using Maximal Marginal Relevance (MMR).
    6. Resolve and download PDFs concurrently with magic byte validation.
    7. Generate reproducibility manifest and store results in SQLite.
    8. Print coverage summary.
    """
    timestamp = datetime.now().isoformat()
    run_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    logger.info(f"Starting retrieval run {run_id} for domain: '{domain}' (target={target_size}, years={start_year}-{end_year})")
    
    # Initialize DB
    init_db(db_path)
    
    # Configurable limits dynamically scaled to target size
    MAX_SEARCH_STRATEGIES = 5
    MAX_SEARCH_ROUNDS = 2
    MIN_CANDIDATE_POOL = max(10, min(200, int(target_size * 1.5)))
    limit_per_source = max(10, min(100, int(target_size * 1.2)))
    
    # 1. Search Orchestrator / Query Planner Agent
    plan = plan_search(domain, max_strategies=MAX_SEARCH_STRATEGIES)
    search_strategies = plan.get("search_strategies", [])
    normalized_query = plan.get("normalized_domain", domain)
    logger.info(f"Planned search strategies: {search_strategies}")
    
    raw_candidates = []
    round_strategies_used = []
    
    # Multi-round search logic
    for round_idx in range(1, MAX_SEARCH_ROUNDS + 1):
        logger.info(f"--- Search Round {round_idx} ---")
        
        # Determine strategies for this round
        if round_idx == 1:
            current_strategies = search_strategies[:3]
        else:
            current_strategies = search_strategies[3:]
            
        if not current_strategies:
            break
            
        round_strategies_used.extend(current_strategies)
        
        # Execute queries across sources concurrently
        logger.info(f"Executing queries for strategies: {current_strategies}")
        records = execute_worker_queries(current_strategies, limit_per_source=limit_per_source, start_year=start_year, end_year=end_year)
        raw_candidates.extend(records)
        
        # Deduplicate candidates so far to see pool size
        temp_unique, _ = merge_and_deduplicate(raw_candidates)
        logger.info(f"Pool status: {len(temp_unique)} unique candidates found so far.")
        
        # Early stopping condition: if we have enough candidates, skip remaining rounds
        if len(temp_unique) >= MIN_CANDIDATE_POOL:
            logger.info("Candidate pool size target satisfied. Stopping search rounds.")
            break
            
    # 2. Merger and Deduplication
    canonical_candidates, deduplication_logs = merge_and_deduplicate(raw_candidates)
    
    # Add run_id to candidates
    for p in canonical_candidates:
        p["run_id"] = run_id
        
    candidate_count = len(raw_candidates)
    deduplicated_count = len(canonical_candidates)
    
    if deduplicated_count == 0:
        logger.error("No candidates found across all workers. Aborting retrieval run.")
        print(f"Error: No candidates found for query '{domain}'. Please try a different query.")
        return
        
    # 3. Relevance Ranking
    ranked_candidates = rank_candidates(canonical_candidates, normalized_query)
    
    # 4. Iterative Selection and Concurrent Resolution
    selected_papers = []
    unselected_pool = list(ranked_candidates)
    pdf_dir = "data/pdfs"
    
    logger.info("Starting batch-based concurrent PDF resolution loop to hit exact target size...")
    
    while len(selected_papers) < target_size and unselected_pool:
        needed = target_size - len(selected_papers)
        
        # Select next 'needed' candidates matching diversity of already selected
        candidates_batch = select_next_diverse_batch(
            unselected_pool,
            needed=needed,
            already_selected=selected_papers,
            lambda_param=0.6
        )
        
        if not candidates_batch:
            break
            
        # Remove selected batch from unselected pool
        for p in candidates_batch:
            unselected_pool = [item for item in unselected_pool if item["paper_id"] != p["paper_id"]]
            
        # Resolve PDFs for this batch concurrently
        resolved_batch = resolve_corpus_pdfs(candidates_batch, pdf_dir=pdf_dir, max_workers=40)
        
        # Filter successful and failed resolutions
        for paper in resolved_batch:
            if paper.get("fulltext_resolved"):
                selected_papers.append(paper)
                logger.info(f"Accepted into corpus: '{paper.get('title')[:40]}...' (resolved={len(selected_papers)}/{target_size})")
            else:
                # Store failed resolution attempts as unresolved in database
                insert_paper(paper, db_path)
                
    selected_count = len(selected_papers)
    valid_pdf_count = selected_count
    
    # Store only the selected/resolved papers in SQLite database for this run
    logger.info(f"Storing {len(selected_papers)} selected papers in SQLite database...")
    for paper in selected_papers:
        insert_paper(paper, db_path)
        
    duration_seconds = time.time() - start_time
    
    # 6. Generate Reproducibility Manifest
    manifest = {
        "retrieval_run_id": run_id,
        "original_query": domain,
        "normalized_query": normalized_query,
        "search_strategies": round_strategies_used,
        "sources": ["openalex", "semantic_scholar", "arxiv"],
        "api_parameters": {
            "max_strategies": MAX_SEARCH_STRATEGIES,
            "max_search_rounds": MAX_SEARCH_ROUNDS,
            "min_candidate_pool": MIN_CANDIDATE_POOL,
            "target_size": target_size,
            "start_year": start_year,
            "end_year": end_year
        },
        "candidate_count": candidate_count,
        "deduplicated_count": deduplicated_count,
        "selected_count": selected_count,
        "valid_pdf_count": valid_pdf_count,
        "excluded_count": deduplicated_count - selected_count,
        "papers": selected_papers,
        "api_failures": [], # Add details if worker threw exceptions
        "timestamp": timestamp,
        "duration_seconds": duration_seconds,
        "deduplication_logs": deduplication_logs
    }
    
    # Write manifest file
    manifest_path = f"data/manifest_{run_id}.json"
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)
        logger.info(f"Manifest written to {manifest_path}")
    except Exception as e:
        logger.error(f"Failed to write manifest file: {e}")
        
    # Store run details in database
    run_record = {
        "run_id": run_id,
        "original_query": domain,
        "normalized_query": normalized_query,
        "search_strategies": round_strategies_used,
        "candidate_count": candidate_count,
        "deduplicated_count": deduplicated_count,
        "selected_count": selected_count,
        "valid_pdf_count": valid_pdf_count,
        "reproducibility_manifest": manifest,
        "timestamp": timestamp
    }
    insert_run(run_record, db_path)
    
    # 7. Print final coverage summary report
    print("\n" + "="*50)
    print("           MULTI-AGENT RETRIEVAL COVERAGE REPORT")
    print("="*50)
    print(f"Run ID:                {run_id}")
    print(f"Domain Query:          \"{domain}\"")
    print(f"Normalized Domain:     \"{normalized_query}\"")
    print(f"Search Strategies:     {len(round_strategies_used)}")
    print(f"Raw Candidates:        {candidate_count}")
    print(f"Deduplicated Pool:     {deduplicated_count}")
    print(f"Selected Subset:       {selected_count}")
    print(f"Full-text Resolved:    {valid_pdf_count}")
    print(f"Time Taken:            {duration_seconds:.2f} seconds")
    
    # Resolution method stats
    method_stats = {}
    for p in selected_papers:
        method = p.get("resolution_method", "unresolved")
        method_stats[method] = method_stats.get(method, 0) + 1
        
    print("\nResolution Breakdown:")
    for method, count in method_stats.items():
        if method != "unresolved":
            print(f"  - {method}: " + " "*(18 - len(method)) + f"{count}")
    print(f"  - Unresolved:        {method_stats.get('unresolved', 0)}")
    
    print("\nReproducibility Manifest saved at:")
    print(f"  {manifest_path}")
    print("="*50 + "\n")
    return run_id

