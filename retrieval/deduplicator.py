import logging
import difflib
import json

logger = logging.getLogger("trendscope.deduplicator")

def clean_title(title: str) -> str:
    """Helper to clean a title string for matching."""
    if not title:
        return ""
    return "".join(c.lower() for c in title if c.isalnum())

def get_first_author_token(authors: list) -> str:
    """Helper to get a normalized token of the first author's last name."""
    if not authors or not authors[0]:
        return ""
    name = authors[0].strip()
    if "," in name:
        # Format: Last, First (e.g. "Kargupta, A.")
        last_name = name.split(",")[0].strip()
    else:
        # Format: First Last (e.g. "Aniket Kargupta")
        # Take the last word as the last name
        parts = name.split()
        last_name = parts[-1].strip() if parts else ""
        
    return "".join(c.lower() for c in last_name if c.isalnum())

def are_fuzzy_duplicate(t1: str, t2: str, threshold: float = 0.90) -> bool:
    """Uses difflib to check if titles are fuzzy duplicates."""
    c1 = clean_title(t1)
    c2 = clean_title(t2)
    if not c1 or not c2:
        return False
    # If titles are identical when cleaned
    if c1 == c2:
        return True
    
    # Calculate similarity ratio
    ratio = difflib.SequenceMatcher(None, c1, c2).ratio()
    return ratio >= threshold

def merge_records(r1: dict, r2: dict) -> dict:
    """
    Merges two duplicate records, retaining the most complete fields.
    """
    # Pick canonical source fields
    merged = dict(r1)
    
    # Merge sources list
    sources_set = set(r1.get("sources", [r1.get("source")]))
    sources_set.update(r2.get("sources", [r2.get("source")]))
    merged["sources"] = sorted(list(filter(None, sources_set)))
    
    # Choose longest abstract
    abs1 = r1.get("abstract") or ""
    abs2 = r2.get("abstract") or ""
    merged["abstract"] = abs1 if len(abs1) >= len(abs2) else abs2
    
    # Choose title (prefer non-empty)
    merged["title"] = r1.get("title") or r2.get("title")
    
    # Fill missing identifiers
    for key in ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "venue", "publication_year"]:
        if not r1.get(key) and r2.get(key):
            merged[key] = r2[key]
            
    # Choose canonical paper_id
    # Priority: OpenAlex ID -> DOI -> arXiv ID -> SS ID
    cand_id = None
    if merged.get("openalex_id"):
        cand_id = merged["openalex_id"]
    elif merged.get("doi"):
        # Hash/sanitize DOI as a clean ID
        clean_doi = "".join(c for c in merged["doi"] if c.isalnum())
        cand_id = f"doi_{clean_doi}"
    elif merged.get("arxiv_id"):
        cand_id = f"arxiv_{merged['arxiv_id']}"
    elif merged.get("semantic_scholar_id"):
        cand_id = f"ss_{merged['semantic_scholar_id']}"
    else:
        cand_id = r1.get("paper_id")
        
    merged["paper_id"] = cand_id
    
    return merged

def deduplicate_records(records: list) -> tuple[list[dict], list[dict]]:
    """
    Deduplicates a list of PaperRecords using hierarchical logic:
    1. DOI Match
    2. arXiv ID Match
    3. Title + First Author + Year match
    4. Fuzzy Title Match
    
    Returns:
        (canonical_records, deduplication_manifest_logs)
    """
    logger.info(f"Starting deduplication of {len(records)} candidate records...")
    
    canonical = []
    manifest_logs = []
    
    for record in records:
        # Pre-populate sources list if not present
        if "sources" not in record:
            record["sources"] = [record.get("source")]
            
        doi = record.get("doi")
        arxiv_id = record.get("arxiv_id")
        title = record.get("title")
        authors = record.get("authors") or []
        year = record.get("publication_year")
        
        # Check against existing canonical papers
        matched_idx = -1
        match_method = None
        
        for idx, canon in enumerate(canonical):
            # 1. DOI Match
            if doi and canon.get("doi") and (doi.lower().strip() == canon.get("doi").lower().strip()):
                matched_idx = idx
                match_method = "doi_match"
                break
                
            # 2. arXiv ID Match
            if arxiv_id and canon.get("arxiv_id") and (arxiv_id == canon.get("arxiv_id")):
                matched_idx = idx
                match_method = "arxiv_id_match"
                break
                
            # 3. Title + First Author + Year Match
            first_auth_canon = get_first_author_token(canon.get("authors", []))
            first_auth_rec = get_first_author_token(authors)
            if clean_title(title) == clean_title(canon.get("title")) and first_auth_canon == first_auth_rec and year == canon.get("publication_year"):
                matched_idx = idx
                match_method = "title_author_year_match"
                break
                
            # 4. Fuzzy Title Match (+/- 1 year tolerance)
            if year and canon.get("publication_year") and abs(year - canon.get("publication_year")) <= 1:
                if are_fuzzy_duplicate(title, canon.get("title"), threshold=0.92):
                    matched_idx = idx
                    match_method = "fuzzy_title_match"
                    break
                    
        if matched_idx != -1:
            # Found duplicate! Merge it
            canon_paper = canonical[matched_idx]
            merged = merge_records(canon_paper, record)
            canonical[matched_idx] = merged
            
            manifest_logs.append({
                "duplicate_title": record.get("title"),
                "duplicate_source": record.get("source"),
                "duplicate_id": record.get("paper_id"),
                "canonical_title": canon_paper.get("title"),
                "canonical_id": merged.get("paper_id"),
                "match_method": match_method
            })
            logger.debug(f"Merged duplicate found via '{match_method}': {record.get('title')[:40]}")
        else:
            # New unique record
            canonical.append(dict(record))
            
    logger.info(f"Deduplication finished. Unique records remaining: {len(canonical)} (removed {len(manifest_logs)} duplicates)")
    return canonical, manifest_logs
