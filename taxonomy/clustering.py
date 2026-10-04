import logging
import warnings
warnings.filterwarnings("ignore")
import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.metrics import silhouette_score, adjusted_rand_score
from scipy.stats import entropy
from taxonomy.models import ClusterResult

logger = logging.getLogger("trendscope.taxonomy.clustering")

def get_adaptive_parameter_grid(n_samples: int) -> list[tuple[str, int, int]]:
    """
    Generates an adaptive candidate grid of (cluster_selection_method, min_cluster_size, min_samples)
    tuned dynamically to the corpus size. Prefers denser, more coherent clusters.
    """
    if n_samples < 30:
        mcs_candidates = [2, 3, 4, 5]
        ms_candidates = [1, 2, 3]
    elif n_samples <= 80:
        mcs_candidates = [3, 4, 5, 6, 8]
        ms_candidates = [1, 2, 3, 4]
    elif n_samples <= 250:
        mcs_candidates = [4, 5, 6, 8, 10, 12, 15]
        ms_candidates = [2, 3, 4, 5, 6]
    else:
        mcs_candidates = [5, 8, 10, 12, 15, 20, 25, 30]
        ms_candidates = [3, 5, 8, 10, 12]

    grid = []
    for csm in ["eom", "leaf"]:  # eom first – usually better structure
        for mcs in mcs_candidates:
            for ms in ms_candidates:
                if ms <= mcs:
                    grid.append((csm, mcs, ms))
    return grid

def calculate_clustering_metrics(
    X: np.ndarray, 
    labels: np.ndarray, 
    paper_ids: list[str]
) -> dict:
    """
    Computes a comprehensive suite of clustering metrics on the embedding space.
    """
    n = len(paper_ids)
    unique_clusters = sorted([l for l in set(labels) if l != -1])
    k = len(unique_clusters)
    noise_count = int(np.sum(labels == -1))
    noise_ratio = float(noise_count / n) if n > 0 else 0.0
    
    if k == 0:
        return {
            "k": 0, "noise": noise_count, "noise_ratio": noise_ratio,
            "largest": 0, "largest_pct": 0.0, "smallest": 0, "avg_size": 0.0,
            "silhouette": -1.0, "avg_intra": 0.0, "avg_inter": 0.0,
            "entropy": 0.0, "composite_score": -999.0, "sizes": []
        }
        
    counts = [int(np.sum(labels == c)) for c in unique_clusters]
    largest = max(counts)
    largest_pct = float(largest / n)
    smallest = min(counts)
    avg_size = float(np.mean(counts))
    
    # Silhouette score
    non_noise_mask = (labels != -1)
    sil = -1.0
    if k > 1 and np.sum(non_noise_mask) > k:
        try:
            sil = float(silhouette_score(X[non_noise_mask], labels[non_noise_mask], metric="cosine"))
        except Exception:
            sil = -1.0
            
    # Intra-cluster similarity and Centroids
    intra_sims = []
    centroids = []
    for c in unique_clusters:
        c_X = X[labels == c]
        c_mean = np.mean(c_X, axis=0)
        norm = np.linalg.norm(c_mean)
        c_norm = (c_mean / norm) if norm > 0 else c_mean
        centroids.append(c_norm)
        
        if len(c_X) > 1:
            dot_prods = np.dot(c_X, c_X.T)[np.triu_indices(len(c_X), k=1)]
            intra_sims.append(float(np.mean(dot_prods)))
        else:
            intra_sims.append(1.0)
    avg_intra = float(np.mean(intra_sims)) if intra_sims else 0.0
    
    # Inter-cluster separation
    inter_sims = []
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            inter_sims.append(float(np.dot(centroids[i], centroids[j])))
    avg_inter = float(np.mean(inter_sims)) if inter_sims else 0.0
    
    # Size Entropy
    probs = np.array(counts, dtype=np.float32) / np.sum(counts)
    ent = float(entropy(probs)) / (np.log(k) if k > 1 else 1.0)
    
    # Improved calibrated scoring function (less harsh on noise, rewards separation)
    dom_penalty = max(0.0, (largest_pct - 0.55) * 1.5)
    noise_penalty = max(0.0, (noise_ratio - 0.30) * 2.0)
    if noise_ratio > 0.50:
        noise_penalty += (noise_ratio - 0.50) * 3.0

    k_bonus = 0.15 * min(k, 12)
    separation = avg_intra - avg_inter

    composite_score = (
        1.0 * (sil if sil > -0.5 else -0.5)
        + 2.2 * separation
        + 0.4 * ent
        + k_bonus
        - dom_penalty
        - noise_penalty
    )
    
    return {
        "k": k,
        "noise": noise_count,
        "noise_ratio": noise_ratio,
        "largest": largest,
        "largest_pct": largest_pct,
        "smallest": smallest,
        "avg_size": avg_size,
        "silhouette": sil,
        "avg_intra": avg_intra,
        "avg_inter": avg_inter,
        "entropy": ent,
        "composite_score": composite_score,
        "sizes": counts
    }

def run_stability_analysis(
    X: np.ndarray, 
    csm: str, 
    mcs: int, 
    ms: int, 
    n_folds: int = 5, 
    subsample_ratio: float = 0.85
) -> float:
    """
    Evaluates clustering stability across sub-samples using Adjusted Rand Index (ARI).
    """
    n = len(X)
    if n < 10:
        return 1.0
        
    full_hdb = HDBSCAN(min_cluster_size=mcs, min_samples=ms, cluster_selection_method=csm)
    full_labels = full_hdb.fit_predict(X)
    
    aris = []
    np.random.seed(42)
    for _ in range(n_folds):
        sub_size = max(5, int(subsample_ratio * n))
        sub_indices = np.random.choice(n, size=sub_size, replace=False)
        X_sub = X[sub_indices]
        
        sub_hdb = HDBSCAN(min_cluster_size=mcs, min_samples=ms, cluster_selection_method=csm)
        sub_labels = sub_hdb.fit_predict(X_sub)
        
        ari = adjusted_rand_score(full_labels[sub_indices], sub_labels)
        aris.append(ari)
        
    return float(np.mean(aris))

def apply_umap_reduction(
    X: np.ndarray, 
    n_neighbors: int = None, 
    n_components: int = None, 
    random_state: int = 42
) -> np.ndarray:
    """
    Reduces high-dimensional embeddings (e.g. 1024-D BGE) into a compact topological manifold
    optimized for HDBSCAN density clustering.
    """
    n_samples, n_features = X.shape
    if n_samples < 6 or n_features <= 15:
        return X
        
    try:
        import umap
        neighbors = n_neighbors or min(15, max(3, n_samples - 1))
        components = n_components or min(10, max(2, n_samples // 4))
        
        reducer = umap.UMAP(
            n_neighbors=neighbors,
            n_components=components,
            min_dist=0.0,
            metric="cosine",
            random_state=random_state
        )
        X_reduced = reducer.fit_transform(X)
        logger.info(f"[UMAP] Reduced {n_samples} vectors from {n_features}-D -> {components}-D (n_neighbors={neighbors}, metric=cosine)")
        return X_reduced
    except Exception as e:
        logger.warning(f"[UMAP] Reduction failed or unavailable ({e}). Using full {n_features}-D vectors.")
        return X

def evaluate_subclustering(
    paper_ids: list[str], 
    X_sub: np.ndarray, 
    parent_intra: float = 0.75
) -> dict | None:
    """
    Evaluates candidate HDBSCAN clusterings on a subset of papers (e.g. noise set).
    Returns the best candidate if valid.
    """
    n_sub = len(paper_ids)
    if n_sub < 4:
        return None
        
    grid = get_adaptive_parameter_grid(n_sub)
    X_sub_cluster = apply_umap_reduction(X_sub, n_components=min(5, max(2, n_sub // 2)))
    best_candidate = None
    best_score = -999.0
    
    for csm, mcs, ms in grid:
        try:
            hdb = HDBSCAN(min_cluster_size=mcs, min_samples=ms, cluster_selection_method=csm)
            labels = hdb.fit_predict(X_sub_cluster)
            metrics = calculate_clustering_metrics(X_sub, labels, paper_ids)
            
            if metrics["k"] < 2 or metrics["smallest"] < 2:
                continue
                
            metrics["csm"] = csm
            metrics["mcs"] = mcs
            metrics["ms"] = ms
            metrics["labels"] = labels
            
            if metrics["composite_score"] > best_score:
                best_score = metrics["composite_score"]
                best_candidate = metrics
        except Exception:
            pass
            
    return best_candidate

def run_clustering(
    embeddings_mapping: dict[str, list[float]], 
    min_cluster_size: int = None, 
    min_samples: int = None,
    noise_trigger_threshold: float = 0.0,
    use_umap: bool = True
) -> tuple[list[ClusterResult], list[str]]:
    """
    Executes Regular HDBSCAN on UMAP manifold for all papers.
    Always executes an extra recursive HDBSCAN on the noise set to extract genuine dense subgroups.
    Nothing else is recursively split.
    """
    if not embeddings_mapping:
        logger.warning("Empty embeddings mapping provided to clustering.")
        return [], []
        
    paper_ids = list(embeddings_mapping.keys())
    X = np.array([embeddings_mapping[pid] for pid in paper_ids])
    n_samples = len(paper_ids)
    
    # 0. Apply UMAP if enabled and dimension > 15
    X_cluster = apply_umap_reduction(X) if use_umap else X
    
    # 1. Regular HDBSCAN on entire corpus
    if min_cluster_size is not None and min_samples is not None:
        grid = [("eom", min_cluster_size, min_samples), ("leaf", min_cluster_size, min_samples)]
    else:
        grid = get_adaptive_parameter_grid(n_samples)
        
    logger.info(f"Running Regular HDBSCAN parameter search across {len(grid)} configurations on {n_samples} papers...")
    
    evaluated_configs = []
    for csm, mcs, ms in grid:
        try:
            hdb = HDBSCAN(min_cluster_size=mcs, min_samples=ms, cluster_selection_method=csm)
            labels = hdb.fit_predict(X_cluster)
            metrics = calculate_clustering_metrics(X, labels, paper_ids)
            metrics["csm"] = csm
            metrics["mcs"] = mcs
            metrics["ms"] = ms
            metrics["labels"] = labels
            evaluated_configs.append(metrics)
        except Exception:
            pass
            
    if not evaluated_configs:
        logger.warning("No valid HDBSCAN configuration found.")
        return [], paper_ids
        
    evaluated_configs = sorted(evaluated_configs, key=lambda x: x["composite_score"], reverse=True)
    
    # Prefer configs that pass basic quality gates
    best_config = None
    for cfg in evaluated_configs:
        if (cfg["k"] >= 2 
            and cfg["smallest"] >= 3 
            and cfg["noise_ratio"] < 0.55 
            and cfg["silhouette"] > 0.05 
            and (cfg["avg_intra"] - cfg["avg_inter"]) > 0.08):
            best_config = cfg
            break
    if best_config is None:
        best_config = evaluated_configs[0]
    
    best_labels = best_config["labels"]
    best_csm = best_config["csm"]
    best_mcs = best_config["mcs"]
    best_ms = best_config["ms"]
    
    root_stability = run_stability_analysis(X, best_csm, best_mcs, best_ms)
    logger.info(
        f"Selected Regular HDBSCAN: {best_csm.upper()}(mcs={best_mcs}, ms={best_ms}) | "
        f"Score: {best_config['composite_score']:+.4f} | "
        f"Clusters: {best_config['k']} | Noise: {best_config['noise']} ({best_config['noise_ratio']*100:.1f}%) | "
        f"Silhouette: {best_config['silhouette']:+.4f} | Stability ARI: {root_stability:.4f}"
    )
    
    # 2. Build Regular Clusters
    unique_root_clusters = sorted([l for l in set(best_labels) if l != -1])
    final_cluster_results = []
    accumulated_noise = [paper_ids[i] for i in range(n_samples) if best_labels[i] == -1]
    
    for cluster_id in unique_root_clusters:
        cluster_mask = (best_labels == cluster_id)
        c_pids = [paper_ids[i] for i in range(n_samples) if cluster_mask[i]]
        c_X = X[cluster_mask]
        
        # Calculate centroid
        c_mean = np.mean(c_X, axis=0)
        norm = np.linalg.norm(c_mean)
        c_centroid = (c_mean / norm) if norm > 0 else c_mean
        
        # Sort papers by proximity to centroid
        sims_to_centroid = np.dot(c_X, c_centroid)
        sorted_indices = np.argsort(-sims_to_centroid)
        sorted_pids = [c_pids[i] for i in sorted_indices]
        
        # Intra-cluster similarity
        if len(c_X) > 1:
            dot_prods = np.dot(c_X, c_X.T)[np.triu_indices(len(c_X), k=1)]
            intra_sim = float(np.mean(dot_prods))
        else:
            intra_sim = 1.0
            
        new_cluster_id = len(final_cluster_results)
        final_cluster_results.append(ClusterResult(
            cluster_id=new_cluster_id,
            paper_ids=sorted_pids,
            size=len(sorted_pids),
            centroid=c_centroid.tolist(),
            silhouette_score=best_config.get("silhouette"),
            average_intra_similarity=intra_sim
        ))
        
    # 3. Always run recursive HDBSCAN on the noise set
    noise_ratio = len(accumulated_noise) / n_samples if n_samples > 0 else 0.0
    if len(accumulated_noise) >= 4:
        logger.info(
            f"[Noise-Only Recursive HDBSCAN] Running recursive analysis on {len(accumulated_noise)} noise papers ({noise_ratio*100:.1f}%)..."
        )
        noise_X = np.array([embeddings_mapping[pid] for pid in accumulated_noise])
        noise_candidate = evaluate_subclustering(accumulated_noise, noise_X, parent_intra=0.75)
        
        if noise_candidate:
            n_k = noise_candidate["k"]
            n_intra = noise_candidate["avg_intra"]
            n_inter = noise_candidate["avg_inter"]
            n_sil = noise_candidate["silhouette"]
            n_csm = noise_candidate["csm"]
            n_mcs = noise_candidate["mcs"]
            n_ms = noise_candidate["ms"]
            
            n_stability = run_stability_analysis(noise_X, n_csm, n_mcs, n_ms)
            n_margin = n_intra - n_inter
            
            logger.info(
                f"[Noise Recursive HDBSCAN] Candidate in noise ({n_csm.upper()} mcs={n_mcs}, ms={n_ms}):\n"
                f"  - Discovered Subgroups: {n_k} (sizes={noise_candidate['sizes']}, remaining noise={noise_candidate['noise']})\n"
                f"  - Intra-Sim: {n_intra:.4f} | Inter-Sim: {n_inter:.4f} | Separation Margin: {n_margin:+.4f}\n"
                f"  - Silhouette: {n_sil:+.4f} | Stability ARI: {n_stability:.4f}"
            )
            
            # Stricter acceptance criteria
            if (n_sil >= 0.15 
                and n_stability >= 0.35 
                and n_margin > 0.12 
                and noise_candidate["smallest"] >= 3):
                logger.info(f"[Noise Recursive HDBSCAN] >>> DECISION: ACCEPTED {n_k} DENSE SUBGROUPS FROM NOISE.")
                n_labels = noise_candidate["labels"]
                unique_n_ids = sorted([l for l in set(n_labels) if l != -1])
                remaining_noise = [accumulated_noise[i] for i in range(len(accumulated_noise)) if n_labels[i] == -1]
                
                for sub_idx in unique_n_ids:
                    sub_mask = (n_labels == sub_idx)
                    sub_pids = [accumulated_noise[i] for i in range(len(accumulated_noise)) if sub_mask[i]]
                    sub_X = noise_X[sub_mask]
                    
                    sub_mean = np.mean(sub_X, axis=0)
                    sub_norm = np.linalg.norm(sub_mean)
                    sub_centroid = (sub_mean / sub_norm) if sub_norm > 0 else sub_mean
                    
                    sub_sims = np.dot(sub_X, sub_centroid)
                    sub_sorted_idx = np.argsort(-sub_sims)
                    sub_sorted_pids = [sub_pids[i] for i in sub_sorted_idx]
                    
                    sub_intra = float(np.mean(np.dot(sub_X, sub_X.T)[np.triu_indices(len(sub_X), k=1)])) if len(sub_X) > 1 else 1.0
                    
                    new_cluster_id = len(final_cluster_results)
                    final_cluster_results.append(ClusterResult(
                        cluster_id=new_cluster_id,
                        paper_ids=sub_sorted_pids,
                        size=len(sub_sorted_pids),
                        centroid=sub_centroid.tolist(),
                        silhouette_score=n_sil,
                        average_intra_similarity=sub_intra
                    ))
                accumulated_noise = remaining_noise
            else:
                logger.info("[Noise Recursive HDBSCAN] >>> DECISION: Candidate did not meet density threshold. Preserving as unclustered noise.")
        else:
            logger.info("[Noise Recursive HDBSCAN] No multi-cluster partition in noise set.")
    else:
        logger.info(f"Noise level is normal ({len(accumulated_noise)} papers, {noise_ratio*100:.1f}%). Skipping noise recursion.")
        
    # Re-index cluster IDs sequentially
    for idx, c in enumerate(final_cluster_results):
        c.cluster_id = idx
        
    return final_cluster_results, accumulated_noise