"""
Analizador para OpenRouter (texto e imágenes) compatible con la interfaz usada por OllamaLocalAnalyzer.
Lee la API key desde la variable de entorno OPENROUTER_API_KEY.
"""

import base64
import json
import os
import time
from io import BytesIO
from typing import Any, Dict, Optional, Union

import requests
from dotenv import load_dotenv

# Reutilizamos los prompts por defecto para mantener consistencia
from components.ollama_analyzer import OllamaLocalAnalyzer
from components.municipios_utils import get_allowed_cities_prompt


load_dotenv()


class OpenRouterAnalyzer:
    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        timeout: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.timeout = timeout

        if not self.api_key:
            print("⚠️ OPENROUTER_API_KEY no configurada. Configúrala en el entorno.")

        print("🧠 OpenRouter configurado")
        print(f"   Base URL: {self.base_url}")
        print(f"   Timeout: {self.timeout}s")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # Opcionales recomendados por OpenRouter
        headers["HTTP-Referer"] = "https://local.app/"
        headers["X-Title"] = "Jobs Analyzer"
        return headers

    def _post_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        start = time.time()
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        elapsed = time.time() - start
        if resp.status_code != 200:
            raise Exception(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"response": content, "status": "success", "tiempo_procesamiento": elapsed}

    def _img_to_data_url(self, image: Union[str, bytes, BytesIO], mime: str = "image/webp") -> str:
        if isinstance(image, str):
            with open(image, "rb") as f:
                b = f.read()
        elif isinstance(image, bytes):
            b = image
        else:
            image.seek(0)
            b = image.read()
        b64 = base64.b64encode(b).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def analyze_image(
        self,
        image_data: Union[str, bytes, BytesIO],
        prompt: Optional[str] = None,
        additional_text: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        prompt = prompt or OllamaLocalAnalyzer.DEFAULT_JOB_PROMPT
        # Instrucción adicional: devolver también 'categorias' (1..3, ordenadas)
        try:
            extra_cats = (
                "\n\nINSTRUCCION: Además del campo 'categoria' (principal), devuelve 'categorias' "
                "como un ARRAY con 1 a 3 categorias de la lista indicada en el prompt, "
                "ordenadas por relevancia. No inventes nuevas categorias. Asegurate de que 'categoria' "
                "sea el primer elemento de 'categorias'."
            )
            prompt = f"{prompt}{extra_cats}"
        except Exception:
            pass
        # Agregar restricción de ciudades permitidas
        try:
            ciudades_txt = get_allowed_cities_prompt(
                'RESTRICCIÓN PARA EL CAMPO "city": '
                'elige SOLO una ciudad EXACTA de la lista. '
                'Si no corresponde ninguna, deja "city" vacío.'
            )
            if ciudades_txt:
                prompt = f"{prompt}\n\n{ciudades_txt}"
        except Exception:
            pass
        if additional_text:
            prompt = f"{prompt}\n\nTexto adicional proporcionado:\n{additional_text}"

        img_url = self._img_to_data_url(image_data)
        payload = {
            "model": model or "qwen/qwen2-vl-7b-instruct:free",
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": img_url}},
                ]}
            ],
            "temperature": 0.7,
        }
        if timeout is not None:
            self.timeout = timeout
        return self._post_chat(payload)

    def analyze_text(
        self,
        text: str,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        prompt = prompt or OllamaLocalAnalyzer.DEFAULT_TEXT_JOB_PROMPT
        # Instrucción adicional: devolver también 'categorias' (1..3, ordenadas)
        try:
            extra_cats = (
                "\n\nINSTRUCCION: Además del campo 'categoria' (principal), devuelve 'categorias' "
                "como un ARRAY con 1 a 3 categorias de la lista indicada en el prompt, "
                "ordenadas por relevancia. No inventes nuevas categorias. Asegurate de que 'categoria' "
                "sea el primer elemento de 'categorias'."
            )
            prompt = f"{prompt}{extra_cats}"
        except Exception:
            pass
        # Agregar restricción de ciudades permitidas
        try:
            ciudades_txt = get_allowed_cities_prompt(
                'RESTRICCIÓN PARA EL CAMPO "city": '
                'elige SOLO una ciudad EXACTA de la lista. '
                'Si no corresponde ninguna, deja "city" vacío.'
            )
            if ciudades_txt:
                prompt = f"{prompt}\n\n{ciudades_txt}"
        except Exception:
            pass
        full_prompt = f"{prompt}\n\nTexto a analizar:\n{text}"

        payload = {
            "model": model or "minimax/minimax-m2.5",
            "messages": [
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.7,
        }
        if timeout is not None:
            self.timeout = timeout
        return self._post_chat(payload)

    def parse_json_response(self, content: str) -> Dict[str, Any]:
        # Reutilizamos el parser robusto del analizador de Ollama
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        return OllamaLocalAnalyzer.parse_json_response(self, content)

    def analyze_job_image(
        self,
        image_data: Union[str, bytes, BytesIO],
        additional_text: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        res = self.analyze_image(
            image_data=image_data,
            additional_text=additional_text,
            model=model,
            timeout=timeout,
        )
        content = res.get("response", "")
        return self.parse_json_response(content)

    def analyze_job_text(
        self,
        text: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        res = self.analyze_text(text=text, model=model, timeout=timeout)
        content = res.get("response", "")
        return self.parse_json_response(content)

    def is_duplicate_job(
        self,
        new_job: Dict[str, Any],
        existing_jobs: list,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        instrucciones = (
            "Eres un evaluador de duplicados de ofertas laborales. "
            "Te daré un NUEVO_JOB y una lista JOBS_EXISTENTES. "
            "Compara por company, position, title, description, city, direction, phoneNumber, email, website. "
            "Tolera pequeñas variaciones (tildes, mayúsculas/minúsculas, sinónimos). "
            "Si encuentras uno esencialmente igual/demasiado similar (misma oferta), marca duplicado. "
            "Evita falsos positivos: si hay dudas relevantes, responde que NO es duplicado. "
            "Responde SOLO con JSON con las claves: duplicado (boolean), indice (entero 0-based o -1), similitud (0-100), explicacion (string)."
        )

        texto_datos = (
            "NUEVO_JOB:\n" + json.dumps(new_job, ensure_ascii=False) +
            "\n\nJOBS_EXISTENTES:\n" + json.dumps(existing_jobs, ensure_ascii=False)
        )

        payload = {
            "model": model or "minimax/minimax-m2.5",
            "messages": [
                {"role": "system", "content": instrucciones},
                {"role": "user", "content": texto_datos},
            ],
            "temperature": 0.3,
        }
        if timeout is not None:
            self.timeout = timeout
        res = self._post_chat(payload)
        content = res.get("response", "{}")
        return self.parse_json_response(content)
