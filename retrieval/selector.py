import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from retrieval.ranker import get_sentence_transformer

logger = logging.getLogger("trendscope.selector")

def select_next_diverse_batch(candidates_pool: list[dict], needed: int, already_selected: list[dict], lambda_param: float = 0.5) -> list[dict]:
    """
    Selects the next 'needed' diverse papers from candidates_pool, taking into account
    the diversity constraints of already_selected papers.
    """
    if not candidates_pool:
        return []
        
    actual_needed = min(needed, len(candidates_pool))
    logger.info(f"Selecting {actual_needed} diverse papers from pool of {len(candidates_pool)} (already selected: {len(already_selected)}) using MMR...")
    
    # Combined list for vectorization
    combined = already_selected + candidates_pool
    documents = [f"{p.get('title') or ''}. {p.get('abstract') or ''}" for p in combined]
    
    model = get_sentence_transformer()
    vectors = None
    if model:
        try:
            vectors = model.encode(documents, convert_to_numpy=True)
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vectors = vectors / norms
        except Exception as e:
            logger.warning(f"Failed to generate embeddings for batch MMR: {e}. Falling back to TF-IDF.")
            vectors = None
            
    if vectors is None:
        try:
            vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
            tfidf_matrix = vectorizer.fit_transform(documents)
            vectors = np.asarray(tfidf_matrix.todense(), dtype=np.float32)
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vectors = vectors / norms
        except Exception as e:
            logger.error(f"TF-IDF vector generation for batch MMR failed: {e}")
            return candidates_pool[:actual_needed]
            
    # Normalize relevance scores of the pool
    relevance_scores = np.array([p.get("relevance_score", 0.0) for p in combined])
    min_rel, max_rel = relevance_scores.min(), relevance_scores.max()
    if max_rel > min_rel:
        norm_relevance = (relevance_scores - min_rel) / (max_rel - min_rel)
    else:
        norm_relevance = np.zeros_like(relevance_scores)
        
    # Indices in the combined list
    selected_indices = list(range(len(already_selected)))
    unselected_indices = list(range(len(already_selected), len(combined)))
    
    newly_selected_indices = []
    
    # If already_selected is empty, select highest relevance candidate as first choice
    if not selected_indices:
        unselected_rel_scores = relevance_scores[unselected_indices]
        first_choice_idx_local = int(np.argmax(unselected_rel_scores))
        first_choice = unselected_indices[first_choice_idx_local]
        selected_indices.append(first_choice)
        newly_selected_indices.append(first_choice)
        unselected_indices.remove(first_choice)
    
    # Select until we've added 'actual_needed' new papers
    while len(newly_selected_indices) < actual_needed:
        mmr_scores = []
        selected_vectors = vectors[selected_indices]
        
        for idx in unselected_indices:
            candidate_vector = vectors[idx]
            sims = np.dot(selected_vectors, candidate_vector)
            max_sim = np.max(sims) if len(sims) > 0 else 0.0
            
            rel = norm_relevance[idx]
            mmr_score = lambda_param * rel - (1 - lambda_param) * max_sim
            mmr_scores.append((mmr_score, idx))
            
        mmr_scores.sort(key=lambda x: x[0], reverse=True)
        best_idx = mmr_scores[0][1]
        
        selected_indices.append(best_idx)
        newly_selected_indices.append(best_idx)
        unselected_indices.remove(best_idx)
        
    new_selected_papers = [combined[i] for i in newly_selected_indices]
    return new_selected_papers

def select_diverse_corpus(candidates: list[dict], target_size: int, lambda_param: float = 0.5) -> list[dict]:
    """
    Selects a diverse subset of candidates using MMR (backward-compatibility wrapper).
    """
    return select_next_diverse_batch(candidates, target_size, [], lambda_param)
