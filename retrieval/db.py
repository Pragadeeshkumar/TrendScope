import sqlite3
import os
import json
import logging

logger = logging.getLogger("trendscope.db")

def init_db(db_path: str = "data/trendscope.db") -> None:
    """
    Initializes the SQLite database, creating papers and retrieval_runs tables if they do not exist.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    logger.info(f"Initializing database at: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Create papers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT,
                abstract TEXT,
                authors TEXT,
                publication_year INTEGER,
                doi TEXT,
                arxiv_id TEXT,
                openalex_id TEXT,
                semantic_scholar_id TEXT,
                venue TEXT,
                sources TEXT,
                pdf_path TEXT,
                fulltext_resolved BOOLEAN,
                resolution_method TEXT,
                relevance_score REAL,
                run_id TEXT
            );
        """)
        
        # Create retrieval_runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retrieval_runs (
                run_id TEXT PRIMARY KEY,
                original_query TEXT,
                normalized_query TEXT,
                search_strategies TEXT,
                candidate_count INTEGER,
                deduplicated_count INTEGER,
                selected_count INTEGER,
                valid_pdf_count INTEGER,
                reproducibility_manifest TEXT,
                timestamp TEXT
            );
        """)
        
        conn.commit()
        logger.info("Database schemas verified successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise e
    finally:
        conn.close()

def insert_paper(paper: dict, db_path: str = "data/trendscope.db") -> None:
    """
    Inserts a PaperRecord into the SQLite database. Overwrites on duplicate.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Serialize list of authors and sources to JSON/comma strings
        authors_val = json.dumps(paper.get("authors", []))
        sources_val = json.dumps(paper.get("sources", []))
        
        cursor.execute("""
            INSERT OR REPLACE INTO papers (
                paper_id, title, abstract, authors, publication_year, doi, arxiv_id, 
                openalex_id, semantic_scholar_id, venue, sources, pdf_path, 
                fulltext_resolved, resolution_method, relevance_score, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            paper.get("paper_id"),
            paper.get("title"),
            paper.get("abstract"),
            authors_val,
            paper.get("publication_year"),
            paper.get("doi"),
            paper.get("arxiv_id"),
            paper.get("openalex_id"),
            paper.get("semantic_scholar_id"),
            paper.get("venue"),
            sources_val,
            paper.get("pdf_path"),
            paper.get("fulltext_resolved"),
            paper.get("resolution_method"),
            paper.get("relevance_score"),
            paper.get("run_id")
        ))
        conn.commit()
        logger.debug(f"Inserted paper: {paper.get('paper_id')}")
    except Exception as e:
        logger.error(f"Failed to insert paper {paper.get('paper_id')}: {e}")
        raise e
    finally:
        conn.close()

def insert_run(run: dict, db_path: str = "data/trendscope.db") -> None:
    """
    Inserts a retrieval run record into the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        strategies_val = json.dumps(run.get("search_strategies", []))
        manifest_val = json.dumps(run.get("reproducibility_manifest", {}))
        
        cursor.execute("""
            INSERT OR REPLACE INTO retrieval_runs (
                run_id, original_query, normalized_query, search_strategies,
                candidate_count, deduplicated_count, selected_count, valid_pdf_count,
                reproducibility_manifest, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            run.get("run_id"),
            run.get("original_query"),
            run.get("normalized_query"),
            strategies_val,
            run.get("candidate_count"),
            run.get("deduplicated_count"),
            run.get("selected_count"),
            run.get("valid_pdf_count"),
            manifest_val,
            run.get("timestamp")
        ))
        conn.commit()
        logger.info(f"Inserted run manifest: {run.get('run_id')}")
    except Exception as e:
        logger.error(f"Failed to insert run {run.get('run_id')}: {e}")
        raise e
    finally:
        conn.close()
