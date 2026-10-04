import logging
import numpy as np

logger = logging.getLogger("trendscope.taxonomy.representatives")

def select_representative_papers(
    paper_ids: list[str],
    embeddings_mapping: dict[str, list[float]],
    centroid: list[float],
    central_count: int = 4,
    diverse_count: int = 1
) -> list[str]:
    """
    Selects representative papers from a cluster:
    - central_count papers closest to the centroid.
    - diverse_count boundary papers furthest from the centroid.
    For small clusters, returns all papers.
    """
    total_size = len(paper_ids)
    if total_size <= (central_count + diverse_count):
        logger.debug(f"Small cluster (size={total_size}). Using all papers as representatives.")
        return list(paper_ids)
        
    centroid_arr = np.array(centroid)
    
    # Calculate cosine distance (1 - similarity) from centroid for each paper
    distances = []
    for pid in paper_ids:
        vec = np.array(embeddings_mapping[pid])
        # Cosine distance
        dist = 1.0 - np.dot(vec, centroid_arr)
        distances.append((dist, pid))
        
    # Sort by distance ascending (closest first)
    distances.sort(key=lambda x: x[0])
    
    # Extract central papers
    central_papers = [pid for dist, pid in distances[:central_count]]
    
    # Extract boundary papers (furthest from centroid)
    # We slice from the end of the list and skip any that might overlap (though overlap is unlikely given the size check)
    boundary_candidates = [pid for dist, pid in distances[central_count:]]
    # Reverse to get furthest first
    boundary_candidates.reverse()
    
    diverse_papers = boundary_candidates[:diverse_count]
    
    representatives = central_papers + diverse_papers
    logger.debug(f"Selected {len(representatives)} representatives (central={len(central_papers)}, diverse={len(diverse_papers)}) from cluster.")
    return representatives
