# model_integration.py
import json  # Import the json library
import os
import re  # Import the re library for regex
from typing import Dict, List, Optional, Tuple  # Add Tuple

import requests
from dotenv import load_dotenv
from langchain.llms.base import LLM

import logging_manager  # Importar para usar log_debug

load_dotenv()  # Carga las variables de entorno
API_KEY = os.getenv("GEMINI_API_KEY")

class GeminiLLM(LLM):
    model_name: str = "gemini-2.0-flash-001"
    api_key: str = API_KEY
    # Suponemos un endpoint para la API de Gemini; ajústalo según la documentación real.
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-001:generateContent"

    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return "gemini_custom"

    @property
    def _identifying_params(self) -> Dict:
        return {"model_name": self.model_name}

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "maxOutputTokens": 512
            }
        }
        params = {
            "key": self.api_key
        }
        logging_manager.log_debug("Prompt Enviado", prompt) # Log prompt
        response = requests.post(self.endpoint, headers=headers, json=data, params=params)
        response.raise_for_status()
        result = response.json()

        # Extract the raw text response
        raw_text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        logging_manager.log_debug("Respuesta Cruda Modelo", raw_text) # Log raw response

        # Clean and parse the response
        cleaned_text = self._clean_and_parse_response(raw_text)
        logging_manager.log_debug("Respuesta Limpia Modelo", cleaned_text) # Log cleaned response
        return cleaned_text

    def _clean_and_parse_response(self, raw_text: str) -> str:
        """
        Cleans the raw text response from Gemini robustly.
        Prioritizes finding the label, handles markdown fences correctly,
        corrects colons, and infers label if missing.
        """
        text = raw_text.strip()

        # 1. Find the first valid label, ignoring potential fences around it
        match = re.search(r"(consulta mongo|respuesta usuario):", text, re.IGNORECASE)

        if match:
            label_start_index = match.start()
            label_end_index = match.end()
            label = match.group(1).strip()

            # Extract content starting right after the matched label and colon
            content_part = text[label_end_index:].lstrip()

            # Find the start of the *next* potential label, if any
            next_label_match = re.search(r"(consulta mongo|respuesta usuario):", content_part, re.IGNORECASE)
            if next_label_match:
                # If another label is found, take content only up to that point
                content = content_part[:next_label_match.start()].strip()
            else:
                # No other label found, take all remaining content
                content = content_part.strip()

            # Clean residual markdown fences from the extracted content
            content = re.sub(r"```", "", content).strip()

            return f"{label}: {content}"
        else:
            # 2. No label found - Fallback: Remove all fences and infer
            # print(f"Debug: No label found directly, removing fences and inferring from: {text}") # Optional debug
            text_no_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()

            if not text_no_fences:
                 return "respuesta usuario: (Respuesta vacía o solo markdown del modelo)"

            # Infer label based on content
            if re.search(r"\bdb\.|show\s+|use\s+", text_no_fences, re.IGNORECASE):
                return f"consulta mongo: {text_no_fences}"
            else:
                return f"respuesta usuario: {text_no_fences}"

# La función get_model_response ya no es necesaria,
# Langchain ConversationChain se encarga de la interacción con el LLM.
