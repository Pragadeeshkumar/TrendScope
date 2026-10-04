import os
import json
import logging
import re
import warnings
warnings.filterwarnings("ignore")

logger = logging.getLogger("trendscope.agents")

def rule_based_query_planner(domain: str, max_strategies: int = 5) -> dict:
    """
    Fallback deterministic query planner. Splits the domain into terms and creates
    3-5 basic keyword search query strings.
    """
    logger.info("Using rule-based query planner (no LLM key found).")
    
    # Normalize query: strip extra spaces
    normalized = " ".join(domain.split())
    
    # Simple keyword extraction: remove common stop words
    stop_words = {"for", "in", "of", "and", "the", "a", "an", "with", "on", "using", "to", "by"}
    words = [w for w in re.split(r'[^a-zA-Z0-9]', normalized) if w]
    cleaned_words = [w for w in words if w.lower() not in stop_words]
    
    # Formulate simple strategies
    strategies = []
    
    # Strategy 1: Full cleaned phrase
    if cleaned_words:
        strategies.append(" ".join(cleaned_words))
        
    # Strategy 2: Break domain by 'for' or 'in' or 'using' if present
    lower_domain = normalized.lower()
    split_words = ["for", "in", "using", "with"]
    split_found = False
    for sw in split_words:
        if f" {sw} " in lower_domain:
            parts = normalized.split(f" {sw} ")
            if len(parts) >= 2:
                # E.g. "Vision Transformers" AND "medical image segmentation"
                p1, p2 = parts[0].strip(), parts[1].strip()
                strategies.append(f"{p1} {p2}")
                # Shorten parts
                p1_words = [w for w in p1.split() if w.lower() not in stop_words]
                p2_words = [w for w in p2.split() if w.lower() not in stop_words]
                if p1_words and p2_words:
                    strategies.append(f"{p1_words[-1]} {p2_words[0]}")
                split_found = True
                break
                
    # Strategy 3: Individual key phrase parts
    if len(cleaned_words) > 3:
        strategies.append(" ".join(cleaned_words[:3]))
        strategies.append(" ".join(cleaned_words[-3:]))
        
    # De-duplicate strategies and limit size
    unique_strategies = []
    for s in strategies:
        s_clean = s.strip()
        if s_clean and s_clean not in unique_strategies:
            unique_strategies.append(s_clean)
            
    # Add simple keyword if pool is small
    if len(unique_strategies) < max_strategies and len(cleaned_words) >= 2:
        alt = f"{cleaned_words[0]} {cleaned_words[-1]}"
        if alt not in unique_strategies:
            unique_strategies.append(alt)
            
    unique_strategies = unique_strategies[:max_strategies]
    
    return {
        "normalized_domain": normalized,
        "concepts": cleaned_words,
        "synonyms": [],
        "search_strategies": unique_strategies,
        "exclusion_terms": []
    }

def plan_search(domain: str, max_strategies: int = 5) -> dict:
    """
    Direct deterministic search query planner. Bypasses LLMs to conserve quota
    and executes fast direct retrieval.
    """
    return rule_based_query_planner(domain, max_strategies=max_strategies)
