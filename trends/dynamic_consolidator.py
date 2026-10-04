"""
Dynamic LLM-Driven Domain Entity Consolidator for Stage 5 Trend Analysis.
Automatically synthesizes canonical technical paradigms, legacy predecessors, and noise filters
for ANY arbitrary scientific research domain using 1-shot Groq LLM inference.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from extraction.llm_rotator import GroqKeyRotator
from extraction.ollama_client import OllamaLocalClient

logger = logging.getLogger("trendscope.trends.dynamic_consolidator")


DYNAMIC_CONSOLIDATION_PROMPT = """You are an expert scientific domain taxonomist and bibliometrician.
Your goal is to analyze all raw extracted method and dataset names from research papers in the domain: "{domain}".

Perform rigorous scientific taxonomy consolidation:
1. "canonical_methods":
   - Group ALL raw synonymous or domain-specific method tokens into 6 to 15 standardized Canonical Method Families.
   - Assign an informative technical "category" (e.g. "Foundation Models & LLMs", "Decision Trees & Rule-Based Systems", "Neuro-Symbolic AI", "Optimization & Alignment", "Agentic Systems", "Classical Baselines", "Survey & Evaluation Frameworks").
   - State what legacy predecessor paradigm or baseline this method replaces or improves upon ("replaces", e.g. "Manual Clinical Rules", "Static Closed-Book LLMs", "Standard Decision Trees", "Recurrent Neural Networks (RNNs)").
   - Flag "is_classical_baseline": true for traditional legacy baselines (e.g. Random Forest, Logistic Regression, SVM, XGBoost, basic CNNs, linear models).
   - List the matching raw candidate strings in "aliases".

2. "canonical_datasets":
   - Group ALL raw dataset, registry, cohort, and trial tokens into 5 to 12 standardized Benchmark Families.
   - Identify "modality" (e.g. "Clinical Trial Data", "Electronic Health Records (EHR)", "Synthetic Clinical Benchmarks", "Clinical Text / Question Answering", "Healthcare Survey Cohorts").
   - List the matching raw candidate strings in "aliases".

3. "rejected_noise":
   - List only strictly non-informative placeholder terms:
     * Literature review guidelines (PRISMA, scoping review, PCC framework).
     * Python libraries (numpy, pandas, pytorch, scikit-learn).
     * Non-entity fragments (e.g. "figure 1", "table 2", "section 3").

Output strictly valid JSON matching this schema:
{
  "canonical_methods": [
    {
      "family": "Canonical Family Name",
      "category": "Technical Category",
      "replaces": "Predecessor / Legacy Paradigm",
      "is_classical_baseline": false,
      "aliases": ["raw_alias_1", "raw_alias_2"]
    }
  ],
  "canonical_datasets": [
    {
      "family": "Canonical Benchmark Name",
      "modality": "Modality / Type",
      "aliases": ["raw_dataset_1"]
    }
  ],
  "rejected_noise": ["prisma guidelines", "numpy", "figure 1"]
}
"""


class DynamicDomainConsolidator:
    """
    Performs dynamic domain-adaptive entity consolidation using Groq LLM.
    Zero hardcoded rules required across any research domain.
    """

    def __init__(self, run_id: str, domain: str = "Artificial Intelligence", cache_dir: str = "data/trends"):
        self.run_id = run_id
        self.domain = domain
        self.cache_path = os.path.join(cache_dir, f"consolidation_cache_{run_id}.json")
        self.mapping_data: Dict[str, Any] = {}
        self.method_lookup: Dict[str, Dict[str, Any]] = {}
        self.dataset_lookup: Dict[str, Dict[str, Any]] = {}
        self.noise_set: set = set()

    def build_or_load_mapping(
        self, 
        raw_methods: List[str], 
        raw_datasets: List[str]
    ) -> None:
        """Loads cached mapping or queries Groq to consolidate raw entity candidates."""
        # 1. Try loading from cache
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.mapping_data = json.load(f)
                logger.info(f"Loaded cached dynamic consolidation mapping from {self.cache_path}")
                self._index_mapping()
                return
            except Exception as e:
                logger.warning(f"Failed to load consolidation cache: {e}. Recomputing with Groq...")

        # 2. Get top candidate tokens
        method_counts = Counter([m.strip() for m in raw_methods if m and len(m.strip()) > 2])
        dataset_counts = Counter([d.strip() for d in raw_datasets if d and len(d.strip()) > 2])

        top_method_candidates = [m for m, _ in method_counts.most_common(120)]
        top_dataset_candidates = [d for d, _ in dataset_counts.most_common(80)]

        user_prompt = f"""Research Domain: "{self.domain}"

### Extracted Raw Method Candidates:
{json.dumps(top_method_candidates, indent=2)}

### Extracted Raw Dataset / Benchmark Candidates:
{json.dumps(top_dataset_candidates, indent=2)}
"""
        logger.info(f"Synthesizing dynamic entity taxonomy for domain '{self.domain}' using LLM (Ollama / Groq)...")
        sys_prompt = DYNAMIC_CONSOLIDATION_PROMPT.replace("{domain}", self.domain)
        mapping = None

        # 1. Try Groq Multi-Key Fallback Client first (fastest)
        rotator = GroqKeyRotator(model_name=os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
        if rotator.clients:
            try:
                mapping = rotator.generate_json(
                    system_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    temperature=0.1
                )
            except Exception as e:
                logger.warning(f"Groq dynamic consolidation failed: {e}")

        # 2. Try local Ollama client second
        if not mapping:
            ollama_client = OllamaLocalClient(model_name=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
            if ollama_client.is_available:
                try:
                    mapping = ollama_client.generate_json(
                        system_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        temperature=0.1
                    )
                except Exception as e:
                    logger.warning(f"Ollama dynamic consolidation failed: {e}")

        if not mapping:
            logger.warning("Dynamic LLM consolidation returned empty payload. Using fallback passthrough.")
            mapping = {
                "canonical_methods": [],
                "canonical_datasets": [],
                "rejected_noise": []
            }

        self.mapping_data = mapping
        
        # Save cache if non-empty
        if mapping.get("canonical_methods") or mapping.get("canonical_datasets"):
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2)

        self._index_mapping()
        logger.info(
            f"Dynamic Consolidation complete for '{self.domain}': "
            f"{len(mapping.get('canonical_methods', []))} method families, "
            f"{len(mapping.get('canonical_datasets', []))} dataset families, "
            f"{len(mapping.get('rejected_noise', []))} noise patterns rejected."
        )

    def _index_mapping(self) -> None:
        """Indexes aliases into fast O(1) hash maps for real-time lookups."""
        self.noise_set = {
            item.lower().strip() 
            for item in self.mapping_data.get("rejected_noise", [])
        }
        
        # Common generic fallbacks
        self.noise_set.update({
            "machine learning", "deep learning", "artificial intelligence", "ai", "ml",
            "model", "algorithm", "approach", "methodology", "dataset", "benchmark",
            "our approach", "proposed model", "various datasets", "none", "n/a", "null"
        })

        # Method lookup
        self.method_lookup = {}
        for m in self.mapping_data.get("canonical_methods", []):
            family = m.get("family", "Core Method")
            category = m.get("category", "Domain Methodology")
            replaces = m.get("replaces", "Prior Baselines")
            is_baseline = bool(m.get("is_classical_baseline", False))
            
            # Map canonical name itself
            self.method_lookup[family.lower().strip()] = {
                "family": family,
                "category": category,
                "replaces": replaces,
                "is_baseline": is_baseline
            }
            # Map aliases
            for alias in m.get("aliases", []):
                self.method_lookup[alias.lower().strip()] = {
                    "family": family,
                    "category": category,
                    "replaces": replaces,
                    "is_baseline": is_baseline
                }

        # Dataset lookup
        self.dataset_lookup = {}
        for d in self.mapping_data.get("canonical_datasets", []):
            family = d.get("family", "Benchmark Dataset")
            modality = d.get("modality", "Standard Benchmark")
            
            self.dataset_lookup[family.lower().strip()] = {
                "family": family,
                "modality": modality
            }
            for alias in d.get("aliases", []):
                self.dataset_lookup[alias.lower().strip()] = {
                    "family": family,
                    "modality": modality
                }

    def resolve_method(self, raw_name: str) -> Optional[Dict[str, Any]]:
        """Resolves a raw method string into its canonical metadata, or None if rejected as noise."""
        clean = raw_name.strip().lower()
        if not clean or clean in self.noise_set:
            return None

        # Check direct alias lookup
        if clean in self.method_lookup:
            return self.method_lookup[clean]

        # Partial substring match
        for key, val in self.method_lookup.items():
            if len(key) >= 4 and (key in clean or clean in key):
                return val

        # Fallback to normalized title
        return {
            "family": raw_name.strip().title(),
            "category": "Domain Methodology",
            "replaces": "Prior Baselines",
            "is_baseline": False
        }

    def resolve_dataset(self, raw_name: str) -> Optional[Dict[str, Any]]:
        """Resolves a raw dataset string into its canonical benchmark metadata, or None if noise."""
        clean = raw_name.strip().lower()
        if not clean or clean in self.noise_set:
            return None

        if clean in self.dataset_lookup:
            return self.dataset_lookup[clean]

        for key, val in self.dataset_lookup.items():
            if len(key) >= 4 and (key in clean or clean in key):
                return val

        return {
            "family": raw_name.strip().title(),
            "modality": "Standard Benchmark"
        }
