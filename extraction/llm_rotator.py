"""
Multi-Key LLM Load Balancer & Fallback Client for High-Throughput Stage 3 Extraction and Taxonomy Labeling.
Implements thread-safe Round-Robin key balancing across Groq keys with automatic rate-limit failover
and accurate cumulative token accounting.
"""

import os
import re
import json
import time
import logging
import threading
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trendscope.llm_rotator")


class GroqFallbackClient:
    """
    Thread-safe Groq client with Round-Robin load distribution across multiple API keys.
    Distributes tokens evenly across the keys' TPM windows and automatically fails over upon 429 rate limits.
    """
    def __init__(
        self, 
        model_name: str = "openai/gpt-oss-20b",
        api_keys: Optional[List[str]] = None
    ):
        self.model_name = os.getenv("GROQ_MODEL", model_name)
        self.lock = threading.Lock()
        self.request_counter = 0
        
        # Token metrics tracking
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_requests = 0
        self.key_usage = {}
        
        # Collect Groq API keys from environment
        if api_keys:
            self.api_keys = [k.strip() for k in api_keys if k and k.strip()]
        else:
            self.api_keys = []
            for var in ["GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY"]:
                val = os.getenv(var)
                if val and val.strip() and val.strip() not in self.api_keys:
                    self.api_keys.append(val.strip())
            
            multi_keys = os.getenv("GROQ_API_KEYS")
            if multi_keys:
                for k in multi_keys.split(","):
                    k_clean = k.strip()
                    if k_clean and k_clean not in self.api_keys:
                        self.api_keys.append(k_clean)

        self.clients = []
        self.client_keys = []
        
        try:
            from groq import Groq
            for key in self.api_keys:
                self.clients.append(Groq(api_key=key, max_retries=0))
                preview = key[:8] + "..."
                self.client_keys.append(preview)
                self.key_usage[preview] = {"requests": 0, "tokens": 0}
            logger.info(f"Initialized GroqFallbackClient with {len(self.clients)} Round-Robin keys (Model: {self.model_name}).")
        except Exception as e:
            logger.warning(f"Could not initialize Groq clients: {e}")

    def generate_json(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        temperature: float = 0.1,
        max_tokens: int = 900
    ) -> Optional[Dict[str, Any]]:
        """
        Executes chat completion with JSON parsing, distributing requests across keys via Round-Robin
        with automatic failover to sibling keys.
        """
        if not self.clients:
            return None

        # Guarantee 'json' keyword is in the prompt
        if "json" not in system_prompt.lower():
            system_prompt += "\nOutput your response strictly in valid JSON format."

        num_clients = len(self.clients)
        with self.lock:
            start_idx = self.request_counter % num_clients
            self.request_counter += 1

        # Multi-Model Fallback Pool: Active verified Groq models
        model_pool = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        if self.model_name and self.model_name not in model_pool:
            model_pool.insert(0, self.model_name)

        for current_model in model_pool:
            for offset in range(num_clients):
                idx = (start_idx + offset) % num_clients
                client = self.clients[idx]
                key_preview = self.client_keys[idx]
                
                try:
                    kwargs = {
                        "model": current_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }
                    
                    response = client.chat.completions.create(**kwargs)
                    raw_text = response.choices[0].message.content
                    if not raw_text:
                        continue
                    
                    # Track token metrics
                    usage = getattr(response, "usage", None)
                    p_tok = usage.prompt_tokens if usage else 0
                    c_tok = usage.completion_tokens if usage else 0
                    tot_tok = usage.total_tokens if usage else (p_tok + c_tok)
                    
                    with self.lock:
                        self.total_requests += 1
                        self.total_prompt_tokens += p_tok
                        self.total_completion_tokens += c_tok
                        self.total_tokens += tot_tok
                        if key_preview in self.key_usage:
                            self.key_usage[key_preview]["requests"] += 1
                            self.key_usage[key_preview]["tokens"] += tot_tok

                    parsed = self._repair_and_parse_json(raw_text)
                    if parsed is not None:
                        return parsed

                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "rate" in err_str or "limit" in err_str or "tpm" in err_str or "otpm" in err_str:
                        logger.warning(f"[Groq Key #{idx+1} ({key_preview}) | Model {current_model}] 429 Rate limit, failing over...")
                        continue
                    logger.warning(f"[Groq Key #{idx+1} ({key_preview}) | Model {current_model}] {e}")
                    continue

        return None

    def get_token_usage_stats(self) -> Dict[str, Any]:
        """Returns cumulative token metrics across all invocations."""
        with self.lock:
            return {
                "total_requests": self.total_requests,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens,
                "key_distribution": dict(self.key_usage)
            }

    def _repair_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Robust multi-pass JSON parser that handles trailing commas, markdown fences, and minor syntax anomalies."""
        clean = raw_text.strip()
        clean = re.sub(r'^```(?:json)?\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*```$', '', clean)
        clean = clean.strip()

        # Pass 1: standard load
        try:
            return json.loads(clean)
        except Exception:
            pass

        # Pass 2: Remove trailing commas before } or ]
        fixed = re.sub(r',\s*([\}\]])', r'\1', clean)
        try:
            return json.loads(fixed)
        except Exception:
            pass

        # Pass 3: Extract outermost { ... }
        match = re.search(r'(\{[\s\S]*\})', fixed)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # Pass 4: Truncate at last closing brace
        last_brace = fixed.rfind('}')
        if last_brace > 0:
            try:
                return json.loads(fixed[:last_brace+1])
            except Exception:
                pass

        return None


# Backward-compatible alias
GroqKeyRotator = GroqFallbackClient
