import json
import os
from typing import Any, Dict


DEFAULT_CONFIG: Dict[str, Any] = {
    "image": {"provider": "ollama", "model": "qwen3-vl:235b-cloud"},
    "text": {"provider": "ollama", "model": "minimax-m2:cloud"},
    "providers": {
        "ollama": {"api_url": "http://localhost:11434/api/generate", "timeout": 60},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1", "timeout": 60},
    },
}


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def load_ai_config(path: str = "ai_config.json") -> Dict[str, Any]:
    """
    Carga la configuración de IA desde ai_config.json.
    Si el archivo no existe o está corrupto, usa valores por defecto seguros.
    """
    cfg = DEFAULT_CONFIG
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg = _deep_update(DEFAULT_CONFIG, user_cfg)
        except Exception:
            # Mantener defaults
            pass
    return cfg

