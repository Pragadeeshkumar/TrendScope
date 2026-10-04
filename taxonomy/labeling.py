import os
import json
import logging
import re
import warnings
warnings.filterwarnings("ignore")
from taxonomy.models import ClusterLabel, PaperInput

logger = logging.getLogger("trendscope.taxonomy.labeling")

from extraction.llm_rotator import GroqKeyRotator
from extraction.ollama_client import OllamaLocalClient

# Shared clients for taxonomy labeling
_ollama_labeler = None
_groq_labeler = None

def get_ollama_labeler():
    global _ollama_labeler
    if _ollama_labeler is None:
        _ollama_labeler = OllamaLocalClient(model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"), timeout=5)
    return _ollama_labeler

def get_groq_labeler():
    global _groq_labeler
    if _groq_labeler is None:
        _groq_labeler = GroqKeyRotator(model_name=os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
    return _groq_labeler

def extract_fallback_label(representative_papers: list[dict], domain: str, cluster_id: int) -> tuple[str, str, list[str]]:
    """
    Derives an informative, extractive scientific label from the top centroid papers
    when Gemini API quota is exhausted. (Executes in 0ms without network latency).
    """
    if not representative_papers:
        return f"Cluster {cluster_id}", f"Discovered research group in {domain}", []
        
    top_title = representative_papers[0].get("title", f"Cluster {cluster_id}")
    # Extract clean theme from top paper title
    clean_title = re.sub(r"^(A|An|The|Towards|On)\s+", "", top_title, flags=re.IGNORECASE)
    if ":" in clean_title:
        label = clean_title.split(":")[0].strip()
    elif " for " in clean_title.lower():
        label = clean_title.split(" for ")[0].strip()
    elif " via " in clean_title.lower():
        label = clean_title.split(" via ")[0].strip()
    elif " using " in clean_title.lower():
        label = clean_title.split(" using ")[0].strip()
    else:
        label = clean_title[:45].strip()
        
    desc = f"Discovered research theme centered around '{top_title[:80]}'."
    methods = [p.get("title", "")[:40] for p in representative_papers[:3]]
    return label, desc, methods

_GEMINI_QUOTA_EXHAUSTED = False

def label_cluster(
    domain: str,
    cluster_id: int,
    cluster_size: int,
    representative_papers: list[dict],
    model_name: str | None = None,
    temperature: float = 0.2
) -> ClusterLabel:
    """
    Queries Groq (or Gemini backup) to label a discovered cluster based on its representative papers.
    """
    global _GEMINI_QUOTA_EXHAUSTED
    
    representative_ids = [p.get("paper_id") for p in representative_papers]

    # Construct papers context for prompt
    papers_context = []
    for idx, paper in enumerate(representative_papers):
        pid = paper.get("paper_id")
        title = paper.get("title", "Untitled")
        abstract = paper.get("abstract", "No abstract available.")
        papers_context.append(f"--- Representative Paper {idx + 1} ---\nPaper ID: {pid}\nTitle: {title}\nAbstract: {abstract}\n")
        
    papers_text = "\n".join(papers_context)
    schema = ClusterLabel.model_json_schema()
    
    prompt = f"""
You are an expert research taxonomist specializing in scientific literature.

Domain: "{domain}"
Cluster size: {cluster_size} papers

### Representative Papers (most central first)
{papers_text}

### Task
1. Identify the **core shared research problem / technical direction** that unites these papers.
2. Create a precise taxonomy label.

### Label Requirements
- 3 to 7 words
- Highly specific (never use broad terms like "Machine Learning", "Deep Learning", "AI", "Neural Networks", "Applications of X")
- Prefer noun-phrase style (e.g. "Contrastive Learning for Medical Imaging", "Retrieval-Augmented Generation for Code")
- Must be useful as a node in a research taxonomy

### Also provide
- A clear 1–2 sentence description of the research theme
- 4–6 dominant methods / models / techniques
- Confidence score between 0.0 and 1.0
- Short reasoning

### Output
Return ONLY a valid JSON object matching this schema:
{json.dumps(schema, indent=2)}

Important:
- cluster_id must be {cluster_id}
- representative_paper_ids must be exactly {json.dumps(representative_ids)}
"""

    # 1. Try Groq Multi-Key Fallback Client first (fastest)
    groq_rot = get_groq_labeler()
    if groq_rot.clients:
        for attempt in range(3):
            try:
                logger.info(f"Querying Groq ({groq_rot.model_name}) for cluster {cluster_id} (attempt {attempt+1})...")
                sys_prompt = "You are an expert research taxonomist. Output strictly valid JSON matching the requested schema."
                data = groq_rot.generate_json(
                    system_prompt=sys_prompt,
                    user_prompt=prompt,
                    temperature=temperature
                )
                if data:
                    data["cluster_id"] = cluster_id
                    data["representative_paper_ids"] = representative_ids
                    cluster_label = ClusterLabel(**data)
                    logger.info(f"Successfully labeled cluster {cluster_id} using Groq: '{cluster_label.label}'")
                    return cluster_label
            except Exception as e:
                logger.warning(f"Groq labeling attempt {attempt+1} failed for cluster {cluster_id}: {e}")
            import time
            time.sleep(3.5)

    # 2. Try Ollama Local Client second
    ollama_labeler = get_ollama_labeler()
    if ollama_labeler.is_available:
        try:
            logger.info(f"Querying Ollama ({ollama_labeler.model_name}) for cluster {cluster_id}...")
            sys_prompt = "You are an expert research taxonomist. Output strictly valid JSON matching the requested schema."
            data = ollama_labeler.generate_json(
                system_prompt=sys_prompt,
                user_prompt=prompt,
                temperature=temperature
            )
            if data:
                data["cluster_id"] = cluster_id
                data["representative_paper_ids"] = representative_ids
                cluster_label = ClusterLabel(**data)
                logger.info(f"Successfully labeled cluster {cluster_id} using Ollama: '{cluster_label.label}'")
                return cluster_label
        except Exception as e:
            logger.warning(f"Ollama labeling failed for cluster {cluster_id}: {e}")

    # 3. Try Gemini backup
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            models_to_try = [model_name] if model_name else ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
            for candidate_model in models_to_try:
                try:
                    logger.info(f"Querying Gemini ({candidate_model}) for cluster {cluster_id}...")
                    model = genai.GenerativeModel(candidate_model)
                    response = model.generate_content(
                        prompt,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": temperature
                        }
                    )
                    data = json.loads(response.text)
                    data["cluster_id"] = cluster_id
                    data["representative_paper_ids"] = representative_ids
                    
                    cluster_label = ClusterLabel(**data)
                    logger.info(f"Successfully labeled cluster {cluster_id} using {candidate_model}: '{cluster_label.label}'")
                    return cluster_label
                except Exception as e:
                    logger.warning(f"Gemini error on {candidate_model}: {e}")
                    continue
        except Exception as e:
            pass

    # 3. Fallback to fast extractive landmark labeling
    ext_label, ext_desc, ext_methods = extract_fallback_label(representative_papers, domain, cluster_id)
    return ClusterLabel(
        cluster_id=cluster_id,
        label=ext_label,
        description=ext_desc,
        dominant_methods=ext_methods,
        representative_paper_ids=representative_ids,
        confidence=0.75,
        rationale="Extractive landmark-centroid labeling applied."
    )
