"""
Local Ollama Client for Offline High-Precision Scientific Extraction & Taxonomy.
Communicates via Ollama's native REST API (/api/chat) with strict JSON output formatting.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trendscope.ollama_client")


class OllamaLocalClient:
    """
    Client for interacting with local Ollama instances (e.g. qwen2.5:7b, llama3.1:8b).
    Provides native JSON mode and fallback extraction.
    """
    def __init__(
        self,
        model_name: str = "qwen2.5:7b",
        host: str = "http://localhost:11434",
        timeout: int = 120
    ):
        self.model_name = os.getenv("OLLAMA_MODEL", model_name)
        self.host = os.getenv("OLLAMA_HOST", host).rstrip("/")
        self.timeout = timeout
        self.is_available = self._check_health()
        
        if self.is_available:
            logger.info(f"Initialized OllamaLocalClient on {self.host} (Model: {self.model_name}).")
        else:
            logger.warning(f"Ollama instance not responding at {self.host}. Local model extraction disabled.")

    def _check_health(self) -> bool:
        """Checks if the local Ollama daemon is running."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def is_model_available(self) -> bool:
        """Checks if the requested model is downloaded locally."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                # Match e.g. "qwen2.5:7b" or "qwen2.5:latest"
                for m in models:
                    if self.model_name in m or m.startswith(self.model_name.split(":")[0]):
                        return True
            return False
        except Exception:
            return False

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 600
    ) -> Optional[Dict[str, Any]]:
        """
        Executes local chat completion with native JSON mode.
        """
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,
                "num_gpu": 0,
                "num_thread": 8
            }
        }

        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=180
            )
            
            if resp.status_code != 200:
                logger.warning(f"[Ollama {self.model_name}] Request failed with status {resp.status_code}: {resp.text[:200]}")
                return None

            result_json = resp.json()
            raw_text = result_json.get("message", {}).get("content", "")
            if not raw_text:
                return None

            # Clean markdown code fences if model enclosed JSON
            clean_json = raw_text.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            elif clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
                
            clean_json = clean_json.strip()

            try:
                return json.loads(clean_json)
            except Exception:
                # Regex fallback for outermost JSON object
                json_match = re.search(r'(\{[\s\S]*\})', clean_json)
                if json_match:
                    return json.loads(json_match.group(1))

        except Exception as e:
            logger.warning(f"[Ollama {self.model_name}] Generation error: {e}")
            return None

        return None
