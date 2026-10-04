import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("trendscope.ranker")

# Global cache for sentence transformer model to avoid reloading
_transformer_model = None

def get_sentence_transformer():
    """Attempts to load and cache the SentenceTransformer model."""
    global _transformer_model
    if _transformer_model is not None:
        return _transformer_model
        
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Attempting to load sentence-transformers model 'all-MiniLM-L6-v2'...")
        # Load lightweight model (approx 90MB)
        _transformer_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SentenceTransformer model loaded successfully.")
        return _transformer_model
    except Exception as e:
        logger.warning(f"Could not load SentenceTransformer: {e}. Falling back to TF-IDF ranker.")
        return None

def tfidf_relevance_ranking(candidates: list[dict], query: str) -> list[dict]:
    """
    Ranks papers using TF-IDF Vectorizer and Cosine Similarity.
    Completely offline and fast fallback.
    """
    logger.info("Computing relevance scores using TF-IDF Cosine Similarity...")
    if not candidates:
        return []
        
    documents = []
    for paper in candidates:
        title = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        # Combine title and abstract
        documents.append(f"{title} {abstract}")
        
    try:
        # Fit TF-IDF on all candidate documents + the query
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(documents)
        query_vector = vectorizer.transform([query])
        
        # Calculate cosine similarity
        similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()
        
        for idx, paper in enumerate(candidates):
            paper["relevance_score"] = float(similarities[idx])
            
    except Exception as e:
        logger.error(f"TF-IDF ranking failed: {e}")
        # Default fallback: assign 1.0 or 0.0
        for paper in candidates:
            paper["relevance_score"] = 0.0
            
    # Apply recency boost to prioritize newer papers
    return apply_recency_boost(candidates, recency_weight=0.3)

def apply_recency_boost(candidates: list[dict], recency_weight: float = 0.3) -> list[dict]:
    """
    Adjusts the relevance scores using a publication recency boost,
    ensuring that newer papers are prioritized while maintaining topical relevance.
    """
    if not candidates:
        return []
        
    years = [p.get("publication_year") for p in candidates if p.get("publication_year") is not None]
    if years:
        min_yr = min(years)
        max_yr = max(years)
        yr_span = max_yr - min_yr if max_yr > min_yr else 1
        
        for paper in candidates:
            yr = paper.get("publication_year") or min_yr
            # Normalize year into [0, 1]
            recency = (yr - min_yr) / yr_span
            # Combine semantic similarity and recency
            paper["relevance_score"] = (1.0 - recency_weight) * paper["relevance_score"] + recency_weight * recency
            
    # Sort by relevance score descending
    ranked = sorted(candidates, key=lambda x: x["relevance_score"], reverse=True)
    return ranked

def rank_candidates(candidates: list[dict], query: str) -> list[dict]:
    """
    Ranks candidate papers by semantic relevance to the query with a recency boost.
    Tries SentenceTransformers first, falling back to TF-IDF.
    """
    if not candidates:
        return []
        
    model = get_sentence_transformer()
    if model is None:
        return tfidf_relevance_ranking(candidates, query)
        
    logger.info("Computing relevance scores using SentenceTransformer embeddings...")
    try:
        documents = [f"{p.get('title') or ''}. {p.get('abstract') or ''}" for p in candidates]
        
        # Generate embeddings
        query_emb = model.encode(query, convert_to_numpy=True)
        doc_embs = model.encode(documents, convert_to_numpy=True)
        
        # Compute cosine similarity manually (dot product of normalized vectors)
        query_norm = query_emb / np.linalg.norm(query_emb)
        doc_norms = doc_embs / np.linalg.norm(doc_embs, axis=1, keepdims=True)
        
        similarities = np.dot(doc_norms, query_norm)
        
        for idx, paper in enumerate(candidates):
            paper["relevance_score"] = float(similarities[idx])
            
    except Exception as e:
        logger.warning(f"SentenceTransformer embedding calculation failed: {e}. Using TF-IDF fallback.")
        return tfidf_relevance_ranking(candidates, query)
        
    # Apply recency boost to prioritize newer papers
    return apply_recency_boost(candidates, recency_weight=0.3)
