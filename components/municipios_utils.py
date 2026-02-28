import json
import os
from typing import List, Dict, Optional
import unicodedata


def load_municipios(path: str = os.path.join("components", "municipios.json")) -> List[str]:
    """Carga y aplana la lista de municipios desde el JSON.

    Devuelve una lista de nombres de ciudades/municipios (sin duplicados).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("municipiosParaguay", [])
        ciudades: List[str] = []
        for dep in items:
            for m in dep.get("municipios", []):
                if isinstance(m, str):
                    ciudades.append(m.strip())
        # Eliminar duplicados preservando orden básica
        seen = set()
        unicos: List[str] = []
        for c in ciudades:
            if c and c not in seen:
                seen.add(c)
                unicos.append(c)
        return unicos
    except Exception:
        return []


def _normalize_text(value: Optional[str]) -> str:
    try:
        s = (value or "").strip()
    except Exception:
        s = ""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    return s.lower()


def load_city_department_map(path: str = os.path.join("components", "municipios.json")) -> Dict[str, str]:
    """Carga un mapa normalizado ciudad -> departamento.

    - Claves: nombres de ciudades/municipios normalizados (sin acentos, minúsculas).
    - Valores: nombre de departamento exactamente como está en el JSON.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("municipiosParaguay", [])
        city_to_dep: Dict[str, str] = {}
        for dep in items:
            dep_name = dep.get("departamento")
            for m in dep.get("municipios", []):
                if isinstance(m, str):
                    city_to_dep[_normalize_text(m)] = dep_name
        return city_to_dep
    except Exception:
        return {}


def get_departamento_by_city(city: Optional[str], path: str = os.path.join("components", "municipios.json")) -> Optional[str]:
    """Devuelve el departamento (string) para una ciudad dada, o None si no se encuentra."""
    if not city:
        return None
    city_norm = _normalize_text(city)
    mapping = load_city_department_map(path=path)
    return mapping.get(city_norm)


def get_allowed_cities_prompt(prefix: str = None) -> str:
    """Construye el texto para el prompt con la lista de ciudades permitidas.

    Si no se puede cargar el archivo, devuelve cadena vacía.
    """
    ciudades = load_municipios()
    if not ciudades:
        return ""
    listado = ", ".join(ciudades)
    encabezado = prefix or (
        'Selecciona ÚNICAMENTE una ciudad EXACTA de la siguiente lista de municipios de Paraguay. '
        'Si no hay coincidencia clara, deja "city" vacío.'
    )
    return f"{encabezado}\nCiudades permitidas: {listado}"
