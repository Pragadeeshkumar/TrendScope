import logging
import difflib
import numpy as np
from taxonomy.models import ClusterResult, ClusterLabel

logger = logging.getLogger("trendscope.taxonomy.validator")

def compute_inter_cluster_separation(centroids: list[list[float]]) -> float:
    """
    Computes the average separation between centroids.
    Separation = 1.0 - mean inter-centroid cosine similarity.
    """
    if len(centroids) <= 1:
        return 1.0
        
    similarities = []
    for i in range(len(centroids)):
        c1 = np.array(centroids[i])
        for j in range(i + 1, len(centroids)):
            c2 = np.array(centroids[j])
            # Cosine similarity (since centroids are normalized, it is the dot product)
            sim = np.dot(c1, c2)
            similarities.append(sim)
            
    mean_similarity = float(np.mean(similarities)) if similarities else 0.0
    # Separation is the inverse of similarity
    return max(0.0, min(1.0, 1.0 - mean_similarity))

def check_label_duplication(labels: list[ClusterLabel], threshold: float = 0.8) -> list[dict]:
    """
    Detects if any two cluster labels are highly similar using difflib.
    Returns:
        list of warning dicts
    """
    warnings = []
    for i in range(len(labels)):
        l1 = labels[i]
        for j in range(i + 1, len(labels)):
            l2 = labels[j]
            ratio = difflib.SequenceMatcher(None, l1.label.lower().strip(), l2.label.lower().strip()).ratio()
            if ratio >= threshold:
                logger.warning(
                    f"Potentially duplicate labels detected: "
                    f"Cluster {l1.cluster_id} ('{l1.label}') and Cluster {l2.cluster_id} ('{l2.label}') "
                    f"similarity={ratio:.2f}"
                )
                warnings.append({
                    "cluster_a": l1.cluster_id,
                    "label_a": l1.label,
                    "cluster_b": l2.cluster_id,
                    "label_b": l2.label,
                    "similarity": ratio
                })
    return warnings

def calculate_system_confidence(
    cohesion: float,
    separation: float,
    representative_agreement: float,
    llm_confidence: float
) -> float:
    """
    Computes a system-level taxonomy confidence indicator:
    System confidence = 0.35 * cohesion + 0.25 * separation + 0.20 * representative_agreement + 0.20 * llm_confidence
    """
    score = (
        0.35 * cohesion +
        0.25 * separation +
        0.20 * representative_agreement +
        0.20 * llm_confidence
    )
    return float(max(0.0, min(1.0, score)))

def validate_taxonomy_metrics(
    clusters: list[ClusterResult],
    labels: list[ClusterLabel],
    embeddings_mapping: dict[str, list[float]],
    total_papers: int,
    noise_count: int
) -> dict:
    """
    Calculates numerical validation metrics and system confidence indicator.
    """
    num_clusters = len(clusters)
    if num_clusters == 0:
        return {
            "silhouette_score": 0.0,
            "intra_cluster_similarity": 0.0,
            "inter_cluster_separation": 1.0,
            "noise_rate": float(noise_count) / total_papers if total_papers > 0 else 0.0,
            "system_confidence": 0.0,
            "duplicate_warnings": []
        }
        
    # 1. Cohesion (Average Intra-cluster similarity)
    cohesion = float(np.mean([c.average_intra_similarity for c in clusters if c.average_intra_similarity is not None])) if clusters else 0.0
    
    # 2. Separation (1.0 - Average inter-centroid similarity)
    centroids = [c.centroid for c in clusters if c.centroid is not None]
    separation = compute_inter_cluster_separation(centroids)
    
    # 3. Representative agreement (Average similarity of representative papers to centroids)
    agreement_scores = []
    for c in clusters:
        if not c.centroid or not c.paper_ids:
            continue
        centroid_arr = np.array(c.centroid)
        
        # We find the labels object to get representative paper ids
        label_obj = next((l for l in labels if l.cluster_id == c.cluster_id), None)
        rep_ids = label_obj.representative_paper_ids if label_obj else c.paper_ids[:3]
        
        for pid in rep_ids:
            if pid in embeddings_mapping:
                vec = np.array(embeddings_mapping[pid])
                sim = np.dot(vec, centroid_arr)
                agreement_scores.append(sim)
                
    rep_agreement = float(np.mean(agreement_scores)) if agreement_scores else cohesion
    
    # 4. LLM Confidence
    llm_conf = float(np.mean([l.confidence for l in labels])) if labels else 0.5
    
    # 5. Calculate System Confidence
    sys_confidence = calculate_system_confidence(cohesion, separation, rep_agreement, llm_conf)
    
    # 6. Overall Silhouette Score
    silhouettes = [c.silhouette_score for c in clusters if c.silhouette_score is not None]
    avg_silhouette = float(np.mean(silhouettes)) if silhouettes else 0.0
    
    # 7. Check label duplicates
    duplicate_warnings = check_label_duplication(labels)
    
    metrics = {
        "silhouette_score": avg_silhouette,
        "intra_cluster_similarity": cohesion,
        "inter_cluster_separation": separation,
        "representative_agreement": rep_agreement,
        "llm_confidence": llm_conf,
        "noise_rate": float(noise_count) / total_papers if total_papers > 0 else 0.0,
        "system_confidence": sys_confidence,
        "duplicate_warnings": duplicate_warnings
    }
    
    logger.info(f"Taxonomy validation complete. System Confidence: {sys_confidence:.4f}, Silhouette: {avg_silhouette:.4f}")
    return metrics
