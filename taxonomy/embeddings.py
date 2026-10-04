import os
import json
import logging
import numpy as np
from taxonomy.models import PaperInput, PaperEmbedding

logger = logging.getLogger("trendscope.taxonomy.embeddings")

def get_gemini_embeddings(texts: list[str]) -> list[list[float]]:
    """Generates embeddings using Gemini's gemini-embedding-001 cloud API in batches."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY is not configured in the environment.")
        
    import google.generativeai as genai
    genai.configure(api_key=gemini_key)
    
    # Batch texts to prevent payload limits and respect the 100 requests/minute quota limit
    batch_size = 50
    all_vectors = []
    
    logger.info(f"Generating {len(texts)} embeddings in batches of {batch_size} using Gemini API (gemini-embedding-001)...")
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        response = genai.embed_content(
            model="models/gemini-embedding-001",
            content=batch_texts,
            task_type="clustering"
        )
        # For list inputs, the SDK returns a dict with key "embedding" containing a list of vector lists
        all_vectors.extend(response["embedding"])
        
    return all_vectors

def get_transformers_embeddings(texts: list[str], model_name: str) -> list[list[float]]:
    """Generates dense semantic embeddings locally using SentenceTransformers or HuggingFace Transformers."""
    try:
        from sentence_transformers import SentenceTransformer
        # Resolve model name: if specter or specter2 is specified, use allenai/specter2_base
        if "specter" in model_name.lower():
            st_name = "allenai/specter2_base"
        elif "minilm" in model_name.lower():
            st_name = "sentence-transformers/all-MiniLM-L6-v2"
        else:
            st_name = model_name
            
        logger.info(f"Loading SentenceTransformer model '{st_name}'...")
        st_model = SentenceTransformer(st_name, trust_remote_code=True)
        embeddings = st_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()
    except Exception as e:
        logger.warning(f"SentenceTransformer loading failed ({e}). Falling back to AutoTokenizer/AutoModel...")
        from transformers import AutoTokenizer, AutoModel
        import torch
        
        hf_name = "allenai/specter2_base" if "specter" in model_name.lower() else model_name
        tokenizer = AutoTokenizer.from_pretrained(hf_name)
        model = AutoModel.from_pretrained(hf_name)
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device)
        
        all_vectors = []
        batch_size = 16
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            inputs = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt"
            ).to(device)
            
            with torch.no_grad():
                outputs = model(**inputs)
                embeddings = outputs.last_hidden_state[:, 0, :]
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                all_vectors.extend(embeddings.cpu().numpy().tolist())
                
        return all_vectors

def get_tfidf_embeddings_fallback(texts: list[str]) -> list[list[float]]:
    """Fallback offline TF-IDF representation if both Transformers and Gemini are unavailable."""
    logger.warning("Falling back to local offline TF-IDF vector embeddings...")
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(max_features=768, stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(texts)
    # L2 normalize
    from sklearn.preprocessing import normalize
    normalized_matrix = normalize(tfidf_matrix, norm='l2', axis=1)
    return normalized_matrix.toarray().tolist()

def generate_embeddings(
    papers: list[PaperInput], 
    run_id: str, 
    model_name: str = "allenai/specter2", 
    force_regenerate: bool = False,
    title_only: bool = False
) -> dict[str, list[float]]:
    """
    Orchestrates embedding generation using strictly Paper Title + Abstract.
    Handles persistence/caching and outputs complete diagnostic verification.
    """
    embeddings_dir = "data/taxonomy/embeddings"
    os.makedirs(embeddings_dir, exist_ok=True)
    suffix = "_title_only" if title_only else ""
    model_slug = model_name.replace("/", "_").replace(":", "_").replace("-", "_")
    cache_path = os.path.join(embeddings_dir, f"embeddings_{run_id}_{model_slug}{suffix}.json")
    legacy_cache_path = os.path.join(embeddings_dir, f"embeddings_{run_id}{suffix}.json")
    
    # 1. Load cached embeddings if available
    active_cache = cache_path if os.path.exists(cache_path) else (legacy_cache_path if (os.path.exists(legacy_cache_path) and "specter" in model_name.lower()) else None)
    if not force_regenerate and active_cache and os.path.exists(active_cache):
        logger.info(f"Loading cached embeddings from {active_cache}")
        try:
            with open(active_cache, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            # Verify correct paper counts
            if len(cached_data) == len(papers):
                sample_vec = next(iter(cached_data.values()))
                logger.info(f"[Embedding Diagnostics] Loaded {len(cached_data)} cached vectors | Dim: {len(sample_vec)} | L2 Normalized: True")
                return cached_data
            else:
                logger.warning("Cached embeddings paper count mismatch. Regenerating...")
        except Exception as e:
            logger.warning(f"Failed to load cached embeddings: {e}. Regenerating...")
            
    # 2. Build text representation strictly from Title and Abstract
    texts = []
    paper_ids = []
    missing_abstracts = 0
    
    for paper in papers:
        title = (paper.title or "").strip()
        abstract = (paper.abstract or "").strip()
        
        if not abstract:
            missing_abstracts += 1
            text = title
        elif title_only:
            text = title
        else:
            text = f"{title}. {abstract}"
            
        texts.append(text)
        paper_ids.append(paper.paper_id)
        
    logger.info(f"[Embedding Input Diagnostics] Total papers: {len(papers)} | Missing abstracts: {missing_abstracts} | Text mode: {'Title Only' if title_only else 'Title + Abstract'}")
    
    # 3. Generate embeddings based on availability
    vectors = None
    
    # Check model preference: if user explicitly configures gemini
    use_gemini = "gemini" in model_name.lower() or "text-embedding" in model_name.lower()
    
    if not use_gemini:
        try:
            import transformers
            import torch
            vectors = get_transformers_embeddings(texts, model_name)
        except Exception as e:
            logger.warning(f"Transformers embedding failed ({e}). Falling back to Gemini or TF-IDF...")
            use_gemini = True
            model_name = "models/gemini-embedding-001"
            
    if use_gemini:
        try:
            vectors = get_gemini_embeddings(texts)
        except Exception as e:
            logger.error(f"Gemini embedding generation failed: {e}")
            vectors = None
            
    if vectors is None:
        vectors = get_tfidf_embeddings_fallback(texts)
        model_name = "tfidf_fallback"
        
    # Ensure vectors are strictly L2 normalized
    normalized_vectors = []
    for vec in vectors:
        arr = np.array(vec, dtype=np.float32)
        norm = float(np.linalg.norm(arr))
        if norm > 0:
            arr = arr / norm
        normalized_vectors.append(arr.tolist())
        
    # 4. Map paper_id to vector and validate
    embedding_mapping = {}
    dim = len(normalized_vectors[0]) if normalized_vectors else 0
    all_l2_normalized = True
    
    for pid, vec in zip(paper_ids, normalized_vectors):
        if any(np.isnan(vec)) or any(np.isinf(vec)):
            raise ValueError(f"Generated embedding vector contains NaN or infinite values for paper {pid}.")
        if len(vec) != dim:
            raise ValueError(f"Inconsistent vector dimensions detected: expected {dim}, got {len(vec)} for paper {pid}.")
        v_norm = float(np.linalg.norm(np.array(vec)))
        if abs(v_norm - 1.0) > 1e-4:
            all_l2_normalized = False
        embedding_mapping[pid] = vec
        
    logger.info(f"[Embedding Output Diagnostics] Total papers embedded: {len(embedding_mapping)} | Vector Dim: {dim} | Strictly L2-Normalized: {all_l2_normalized}")
        
    # 5. Persist to disk
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(embedding_mapping, f, indent=4)
        logger.info(f"Persisted {len(embedding_mapping)} embeddings to {cache_path}")
    except Exception as e:
        logger.error(f"Failed to persist embeddings to disk: {e}")
        
    return embedding_mapping
