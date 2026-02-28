"""
Analizador de anuncios de empleo usando Ollama Cloud y Firebase.
VersiÃ³n con GeolocalizaciÃ³n antes de subir a Firestore.
"""

from typing import Dict, Any, List
import json
import os
from datetime import datetime, timedelta
import unicodedata
import re

# Componentes modulares
from components.image_converter import ImageConverter
from components.firebase_manager import FirebaseManager
from components.ollama_analyzer import OllamaLocalAnalyzer
from components.openrouter_analyzer import OpenRouterAnalyzer
from components.ai_config import load_ai_config

# âœ… NUEVO: geolocalizaciÃ³n
from components.geolocation import get_location_details
from components.municipios_utils import load_municipios, get_departamento_by_city

DATA_DIR = os.getenv("DATA_DIR", ".")
DEFAULT_RESULTS_DIR = os.path.join(DATA_DIR, "resultados")
DEFAULT_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")


class JobAnalyzerFirebase:

    def __init__(self, service_account_path: str = DEFAULT_SERVICE_ACCOUNT_PATH):
        self.image_converter = ImageConverter()
        self.ollama_analyzer = OllamaLocalAnalyzer()
        # ConfiguraciÃ³n y proveedores de IA
        self.ai_config = load_ai_config()
        try:
            ollama_cfg = self.ai_config.get('providers', {}).get('ollama', {})
            if 'api_url' in ollama_cfg:
                self.ollama_analyzer.api_url = ollama_cfg['api_url']
            if 'timeout' in ollama_cfg:
                self.ollama_analyzer.timeout = ollama_cfg['timeout']
        except Exception:
            pass
        # Preparar OpenRouter (solo se usa si estÃ¡ seleccionado en config)
        openrouter_cfg = self.ai_config.get('providers', {}).get('openrouter', {})
        self.openrouter_analyzer = OpenRouterAnalyzer(
            base_url=openrouter_cfg.get('base_url', 'https://openrouter.ai/api/v1'),
            timeout=openrouter_cfg.get('timeout', 60)
        )
        self.firebase_manager = FirebaseManager(service_account_path)
        print("âœ… JobAnalyzerFirebase inicializado")

    def _load_local_jobs(self) -> List[Dict[str, Any]]:
        path = os.path.join(DEFAULT_RESULTS_DIR, 'jobs_subidos.json')
        # Asegurar que exista carpeta y archivo
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        if not os.path.isfile(path):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_local_jobs(self, jobs: List[Dict[str, Any]]):
        path = os.path.join(DEFAULT_RESULTS_DIR, 'jobs_subidos.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)

    def _append_local_job(self, job: Dict[str, Any]):
        jobs = self._load_local_jobs()
        # Agregar marca de tiempo local de creaciÃ³n
        try:
            job = dict(job)
        except Exception:
            pass
        if isinstance(job, dict) and 'createdAt' not in job and 'createdAtLocal' not in job:
            job['createdAt'] = datetime.now().isoformat()
        jobs.append(job)
        self._save_local_jobs(jobs)

    def _simplify_for_compare(self, job: Dict[str, Any]) -> Dict[str, Any]:
        keys = [
            'position', 'title', 'company', 'city', 'direction',
            'phoneNumber', 'email', 'website', 'description',
            'categoria', 'salary_range'
        ]
        return {k: job.get(k, '') for k in keys}

    def _normalize_text(self, value: Any) -> str:
        try:
            s = (value or "").strip()
        except Exception:
            s = ""
        s = unicodedata.normalize('NFD', s)
        s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
        return s.lower()

    def _ensure_categorias(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        """Asegura que 'categorias' sea un array (mÃ¡x. 3) y sincroniza 'categoria'."""
        try:
            cats = datos.get('categorias')
            if isinstance(cats, str):
                parts = [p.strip() for p in cats.replace(';', ',').split(',') if p.strip()]
                cats = parts
            elif isinstance(cats, list):
                cleaned = []
                for c in cats:
                    if isinstance(c, str):
                        t = c.strip()
                        if t and t not in cleaned:
                            cleaned.append(t)
                cats = cleaned
            else:
                cats = []

            if not cats:
                cat = datos.get('categoria')
                if isinstance(cat, str) and cat.strip():
                    cats = [cat.strip()]

            datos['categorias'] = cats[:3]
            if datos['categorias']:
                datos['categoria'] = datos['categorias'][0]
            return datos
        except Exception:
            return datos

    def _looks_like_manual_description(self, texto: Any) -> bool:
        if not isinstance(texto, str):
            return False
        cleaned = texto.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(cleaned) < 30:
            return False
        letters = sum(ch.isalpha() for ch in cleaned)
        digits = sum(ch.isdigit() for ch in cleaned)
        return letters > digits
    
    def _validate_description_against_flyer(
        self,
        datos_job: Dict[str, Any],
        manual_text: str,
        timeout_ia: int = 60,
    ) -> Dict[str, Any]:
        """
        Usa el analizador de TEXTO configurado para determinar si la descripción
        manual realmente describe el empleo del flyer.
        """
        resultado = {
            "checked": False,
            "es_descripcion_empleo": False,
            "coincide_con_flyer": False,
        }
        try:
            payload = {
                "flyer_job": {
                    key: datos_job.get(key)
                    for key in [
                        "position",
                        "title",
                        "company",
                        "description",
                        "city",
                        "direction",
                        "requeriments",
                        "categoria",
                        "salary_range",
                    ]
                },
                "descripcion_manual": manual_text,
            }
            prompt = (
                "Evalúa si el campo 'descripcion_manual' describe una oferta laboral "
                "y si corresponde al MISMO empleo descrito en 'flyer_job'. "
                "Responde SOLO en JSON con las claves exactas: "
                "{\"es_descripcion_empleo\": true|false, "
                "\"coincide_con_flyer\": true|false, "
                "\"razon\": \"explicacion breve\"}. "
                "Marca coincide_con_flyer como true únicamente si el texto menciona "
                "el mismo puesto, empresa, funciones o requisitos del flyer. "
                "Si hay dudas razonables, responde false."
            )
            text_provider = (self.ai_config.get("text", {}) or {}).get("provider", "ollama").lower()
            text_model = (self.ai_config.get("text", {}) or {}).get("model")
            payload_text = json.dumps(payload, ensure_ascii=False)
            if text_provider == "openrouter":
                res = self.openrouter_analyzer.analyze_text(
                    text=payload_text,
                    prompt=prompt,
                    model=text_model,
                    timeout=timeout_ia,
                )
                content = res.get("response", "{}")
                parsed = self.openrouter_analyzer.parse_json_response(content)
            else:
                res = self.ollama_analyzer.analyze_text(
                    text=payload_text,
                    prompt=prompt,
                    model=text_model,
                    timeout=timeout_ia,
                )
                content = res.get("response", "{}")
                parsed = self.ollama_analyzer.parse_json_response(content)
            resultado["checked"] = True
            resultado["es_descripcion_empleo"] = bool(
                parsed.get("es_descripcion_empleo", parsed.get("es_descripcion"))
            )
            resultado["coincide_con_flyer"] = bool(parsed.get("coincide_con_flyer"))
            resultado["razon"] = parsed.get("razon") or parsed.get("reason") or ""
            resultado["raw_model_response"] = parsed
            return resultado
        except Exception as exc:
            resultado["error"] = str(exc)
            return resultado
    
    def _apply_manual_description(
        self,
        datos: Dict[str, Any],
        manual_text: Any,
        require_match_with_flyer: bool = False,
        timeout_ia: int = 60,
    ) -> Dict[str, Any]:
        if not self._looks_like_manual_description(manual_text):
            return datos
        raw_text = manual_text if isinstance(manual_text, str) else ""
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = normalized.strip()
        final_text = normalized if normalized else cleaned
        validation_result = None
        if require_match_with_flyer:
            validation_result = self._validate_description_against_flyer(
                datos, final_text, timeout_ia=timeout_ia
            )
            datos["manual_description_validation"] = validation_result
            is_valid = (
                validation_result.get("es_descripcion_empleo")
                and validation_result.get("coincide_con_flyer")
            )
            validation_result["aceptada"] = bool(is_valid)
            if not is_valid:
                return datos
        original = datos.get("description")
        if original and original != final_text:
            datos["description_original_model"] = original
        datos["description"] = final_text
        datos["description_text_source"] = "whatsapp_message"
        return datos

    # --- Validaciones y utilidades de geolocalizaciÃ³n ---

    def _get_cities_map(self):
        """Carga perezosa del mapa de ciudades normalizadas -> original."""
        if getattr(self, '_allowed_cities_norm_map', None):
            return self._allowed_cities_norm_map
        try:
            allowed = load_municipios() or []
        except Exception:
            allowed = []
        norm_map = {}
        try:
            for c in allowed:
                key = self._normalize_text(c)
                if key and key not in norm_map:
                    norm_map[key] = c
        except Exception:
            pass
        self._allowed_cities_norm_map = norm_map
        return self._allowed_cities_norm_map

    def _extract_city_from_text(self, text: Any) -> str:
        """Intenta detectar una ciudad vÃ¡lida dentro de un texto libre.

        Busca coincidencias por substring normalizado contra el listado de
        municipios de Paraguay. Devuelve la ciudad en su forma original, o '' si no hay.
        """
        try:
            s = self._normalize_text(text)
            if not s:
                return ""
            for norm, original in self._get_cities_map().items():
                if norm and norm in s:
                    return original
        except Exception:
            pass
        return ""

    def _determine_expected_city(self, datos: Dict[str, Any]) -> str:
        """Determina la ciudad esperada usando prioridad:
        1) Campo 'city' del anuncio
        2) Ciudad detectada en 'direction'

        Devuelve cadena (posiblemente vacÃ­a si no se puede determinar).
        """
        city = (datos.get('city') or '').strip()
        if city:
            return city
        direction = (datos.get('direction') or '').strip()
        detected = self._extract_city_from_text(direction)
        return detected or ''

    def _cities_match(self, a: Any, b: Any) -> bool:
        """Compara ciudades ignorando acentos y mayÃºsculas."""
        na = self._normalize_text(a)
        nb = self._normalize_text(b)
        if not na or not nb:
            return False
        return na == nb

    def _address_tokens(self, value: Any) -> List[str]:
        """Tokeniza direcciones normalizadas eliminando palabras muy cortas."""
        norm = self._normalize_text(value)
        if not norm:
            return []
        parts = re.split(r'[^a-z0-9]+', norm)
        return [p for p in parts if len(p) >= 4]

    def _addresses_look_related(self, original: Any, candidate: Any) -> bool:
        """Heurística ligera para saber si dos direcciones parecen referirse al mismo lugar."""
        norm_original = self._normalize_text(original)
        norm_candidate = self._normalize_text(candidate)
        if not norm_original or not norm_candidate:
            return False
        if norm_original in norm_candidate or norm_candidate in norm_original:
            return True
        tokens_original = set(self._address_tokens(original))
        tokens_candidate = set(self._address_tokens(candidate))
        if not tokens_original or not tokens_candidate:
            return False
        overlap = len(tokens_original & tokens_candidate)
        min_required = max(1, int(len(tokens_original) * 0.4))
        return overlap >= min_required

    def _ai_compare_addresses(self, input_address: str, geo: Dict[str, Any]) -> Dict[str, Any]:
        """Pide al proveedor de texto que confirme si la dirección buscada coincide con el resultado de Places."""
        formatted = (geo.get("direction") or geo.get("formatted_address") or "").strip()
        place_name = (geo.get("place_name") or geo.get("name") or "").strip()
        place_summary = (geo.get("place_summary") or "").strip()
        candidate_parts = [part for part in [place_name, formatted, place_summary] if part]
        places_address = " | ".join(candidate_parts) if candidate_parts else ""
        place_types = geo.get("place_types")
        if isinstance(place_types, list):
            place_types_payload = place_types
        elif isinstance(place_types, (tuple, set)):
            place_types_payload = list(place_types)
        elif place_types:
            place_types_payload = [str(place_types)]
        else:
            place_types_payload = []

        result = {
            "coincide": None,
            "explicacion": "",
            "places_address": places_address,
            "places_name": place_name,
            "places_summary": place_summary,
            "places_types": place_types_payload,
        }
        if not (input_address and places_address):
            result["explicacion"] = "missing_address_data"
            return result

        text_cfg = (self.ai_config.get('text') or {})
        provider = (text_cfg.get('provider') or 'ollama').lower()
        model = text_cfg.get('model')
        timeout = text_cfg.get('timeout') or 45
        analyzer = self.openrouter_analyzer if provider == 'openrouter' else self.ollama_analyzer

        prompt = (
            "Eres un verificador de direcciones. "
            "Solo responde en JSON con las claves: coincide (boolean) y explicacion (string breve). "
            "Recibirás un JSON con 'input_address' (texto original escrito por el usuario) y múltiples campos "
            "sobre el lugar candidato devuelto por Google Places (dirección formateada, nombre, tipos, ciudad, provincia, país, resumen y enlaces). "
            "Indica coincide=true únicamente si describen el mismo lugar físico considerando referencias, "
            "barrios, avenidas y edificios. Si hay dudas relevantes, responde coincide=false."
        )

        comparison_payload = json.dumps(
            {
                "input_address": input_address,
                "places_candidate": places_address,
                "places_name": place_name,
                "places_summary": place_summary,
                "places_types": place_types_payload,
                "places_business_status": geo.get("place_business_status") or "",
                "places_city": geo.get("city") or "",
                "places_province": geo.get("province") or "",
                "places_country": geo.get("country") or "",
                "places_uri": geo.get("place_google_uri") or "",
                "places_id": geo.get("place_id") or "",
            },
            ensure_ascii=False,
            indent=2
        )

        try:
            ai_raw = analyzer.analyze_text(
                text=comparison_payload,
                prompt=prompt,
                model=model,
                timeout=timeout
            )
            content = ai_raw.get("response", "{}")
            parsed = analyzer.parse_json_response(content)
            coincide_value = parsed.get("coincide")
            coincide_bool = None
            if isinstance(coincide_value, bool):
                coincide_bool = coincide_value
            elif isinstance(coincide_value, str):
                coincide_bool = coincide_value.strip().lower() in {"true", "1", "si", "sí", "yes"}
            elif isinstance(coincide_value, (int, float)):
                coincide_bool = bool(coincide_value)
            result["coincide"] = coincide_bool
            result["explicacion"] = (
                parsed.get("explicacion")
                or parsed.get("justificacion")
                or parsed.get("razon")
                or ""
            )
            result["modelo"] = provider
            result["raw"] = parsed
        except Exception as exc:
            result["error"] = str(exc)

        return result

    def _validate_geo_match(self, search_address: str, geo: Dict[str, Any]) -> Dict[str, Any]:
        """Combina heurística + IA para decidir si se deben usar las coordenadas devueltas."""
        formatted = geo.get("direction") or geo.get("formatted_address") or ""
        heuristic_ok = self._addresses_look_related(search_address, formatted)
        ai_decision = self._ai_compare_addresses(search_address, geo)
        ai_coincide = ai_decision.get("coincide")

        if isinstance(ai_coincide, bool):
            approved = ai_coincide
            reason = "ai_confirmed" if ai_coincide else "ai_rejected"
        else:
            approved = heuristic_ok
            if ai_decision.get("error"):
                reason = "ai_error"
            else:
                reason = "heuristic_match" if heuristic_ok else "insufficient_match"

        print("[Geo] Validación detallada:")
        print(f"       - Dirección buscada  : {search_address}")
        print(f"       - Resultado Places   : {formatted}")
        print(f"       - Heurística coincide: {heuristic_ok}")
        print(f"       - Decisión IA        : {ai_decision}")
        print(f"       - Aprobado           : {approved} (razón: {reason})")

        return {
            "approved": bool(approved),
            "reason": reason,
            "heuristic_match": heuristic_ok,
            "ai_decision": ai_decision,
            "input_address": search_address,
            "places_address": formatted,
        }

    def _filter_existing_jobs_by_city_and_company(
        self,
        existing_jobs: List[Dict[str, Any]],
        new_job: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Filtro previo (Python) antes de IA:
        - Por ciudad: conservar los que coincidan (sin acentos) o no tengan ciudad.
        - Por empresa: conservar los que coincidan (sin acentos) o no tengan empresa.
        Si el nuevo job no tiene ciudad/empresa, se omite ese filtro.
        """
        new_city = self._normalize_text(new_job.get('city', ''))
        new_company = self._normalize_text(new_job.get('company', ''))

        # Filtrar por ciudad
        if new_city:
            after_city = []
            for j in existing_jobs:
                j_city = self._normalize_text(j.get('city', ''))
                if not j_city or j_city == new_city:
                    after_city.append(j)
        else:
            after_city = list(existing_jobs)

        # Filtrar por empresa
        if new_company:
            after_company = []
            for j in after_city:
                j_company = self._normalize_text(j.get('company', ''))
                if not j_company or j_company == new_company:
                    after_company.append(j)
            filtered = after_company
        else:
            filtered = after_city

        return filtered

    def _add_geolocation(self, datos: Dict[str, Any]):
        """
        Intercepta el JSON generado por Ollama antes de subirlo a Firebase.
        Usa Google Maps para obtener lat, lng, direcciÃ³n normalizada y ciudad real.
        Ahora tambiÃ©n incluye 'company' si existe para mejorar la precisiÃ³n.
        """

        city = datos.get("city", "").strip()
        direction = datos.get("direction", "").strip()
        company = datos.get("company", "").strip()  # âœ… NUEVO

        # âœ… ValidaciÃ³n bÃ¡sica
        if not city and not direction and not company:
            print("ðŸŒ No se puede geolocalizar: faltan 'city', 'direction' y 'company'")
            return datos

        # âœ… ConstrucciÃ³n inteligente de direcciÃ³n final
        # Ej: "McDonalds, zona Shopping la Galeria, Asuncion"
        search_address = ""
        if company:
            search_address += company + ", "
        if direction:
            search_address += direction + ", "
        if city:
            search_address += city

        print(f"\nðŸŒ Buscando geolocalizaciÃ³n con Google Maps para: {search_address}")

        try:
            geo = get_location_details(
                city=city or "",
                address=search_address,
                country="Paraguay"  # Puedes cambiar a dinÃ¡mico si quieres
            )

            if not geo:
                print("[Geo] No se pudo obtener ubicacion desde Google Maps")
                return datos

            validation = self._validate_geo_match(search_address, geo)
            datos['geo_validation'] = validation
            if not validation.get("approved"):
                print("   [Geo] Validacion IA/heuristica rechazo el resultado. No se guardan coordenadas.")
                datos['geo_skipped'] = True
                datos['geo_reason'] = validation.get('reason', 'ai_rejected')
                datos.pop("ubication", None)
                return datos

            # ? Reemplazar campos con datos reales
            datos["city"] = geo.get("city", city)
            datos["direction"] = geo.get("direction", search_address)
            datos["ubication"] = {     # ? nombre correcto para Firebase
                "lat": geo.get("lat"),
                "lng": geo.get("lng")
            }
            datos['geo_skipped'] = False
            datos['geo_reason'] = validation.get('reason', 'ok')

            # âœ… Nuevo: asignar departamento (17 dptos de Paraguay) a partir de la ciudad
            try:
                dep = get_departamento_by_city(datos.get("city"))
                if not dep:
                    # Fallback: intentar con la ciudad original o con 'province' del geocoder
                    dep = get_departamento_by_city(city) or (geo.get("province") or "")
                datos["departamento"] = dep or ""
            except Exception:
                datos["departamento"] = ""

            print(f"   âœ… DirecciÃ³n verificada: {datos['direction']}")
            print(f"   ðŸŒŽ Coordenadas: {datos['ubication']['lat']}, {datos['ubication']['lng']}")

        except Exception as e:
            print(f"   âŒ Error en geolocalizaciÃ³n: {e}")

        return datos

    def _add_geolocation_safe(self, datos: Dict[str, Any]):
        """
        Geolocalización con reglas de seguridad para evitar ubicar en otra ciudad:
        - Requiere al menos ciudad esperada (del campo o detectada en dirección) o dirección.
        - Si se conoce la ciudad esperada, SOLO acepta resultados cuya ciudad coincida
          (o cuya dirección formateada contenga la ciudad esperada).
        - Si falla la coincidencia, reintenta con "dirección + ciudad" y luego solo ciudad.
        - Si aún falla: omite geolocalización (marca geo_skipped) para evitar errores.
        """

        input_city = (datos.get("city") or "").strip()
        direction = (datos.get("direction") or "").strip()
        company = (datos.get("company") or "").strip()

        expected_city = self._determine_expected_city(datos)
        expected_city_norm = self._normalize_text(expected_city)

        if (not expected_city_norm and not direction) or (company and not input_city and not direction):
            print("¿YO? Geolocalización omitida: datos insuficientes (se requiere ciudad o dirección)")
            datos['geo_skipped'] = True
            datos['geo_reason'] = 'insufficient_data'
            # Intentar asignar 'departamento' con lo disponible
            try:
                dep = get_departamento_by_city(input_city or expected_city)
                datos["departamento"] = dep or ""
            except Exception:
                datos["departamento"] = ""
            return datos

        parts: List[str] = []
        if company:
            parts.append(company)
        if direction:
            parts.append(direction)
        if expected_city:
            parts.append(expected_city)
        search_address = ", ".join([p for p in parts if p])

        print(f"\n¿YO? Buscando geolocalización con Google Maps para: {search_address}")

        def geocode_and_validate(address_str: str) -> Dict[str, Any]:
            geo = get_location_details(
                city=expected_city or "",
                address=address_str,
                country="Paraguay",
            )
            if not geo:
                return {}
            if expected_city_norm:
                geo_city = geo.get("city") or ""
                if self._cities_match(expected_city, geo_city):
                    return geo
                fa = self._normalize_text(geo.get("formatted_address") or geo.get("direction") or "")
                if expected_city_norm in fa:
                    return geo
                return {}
            return geo

        try:
            geo = geocode_and_validate(search_address)

            if not geo and direction and expected_city:
                alt1 = f"{direction}, {expected_city}"
                print(f"[Geo] Reintento forzado con dirección+ciudad: {alt1}")
                geo = geocode_and_validate(alt1)

            if not geo and expected_city:
                print(f"[Geo] Reintento solo ciudad: {expected_city}")
                geo = geocode_and_validate(expected_city)

            if not geo:
                print("¡sññ? No se pudo obtener ubicación válida que respete la ciudad indicada")
                datos['geo_skipped'] = True
                datos['geo_reason'] = 'city_mismatch_or_not_found'
                if expected_city:
                    datos['geo_expected_city'] = expected_city
                # Asignar departamento por ciudad esperada o entrada si existe
                try:
                    dep = get_departamento_by_city(expected_city or input_city)
                    datos["departamento"] = dep or ""
                except Exception:
                    datos["departamento"] = ""
                return datos

            validation = self._validate_geo_match(search_address, geo)
            datos['geo_validation'] = validation
            if not validation.get("approved"):
                print("   [Geo] Validación IA/heurística no aprobó las coordenadas. Se omiten lat/lng.")
                datos['geo_skipped'] = True
                datos['geo_reason'] = validation.get('reason', 'ai_rejected')
                if expected_city:
                    datos['geo_expected_city'] = expected_city
                try:
                    dep = get_departamento_by_city(expected_city or input_city)
                    datos["departamento"] = dep or ""
                except Exception:
                    datos["departamento"] = ""
                datos.pop("ubication", None)
                return datos

            datos["city"] = geo.get("city", input_city or expected_city)
            datos["direction"] = geo.get("direction", search_address)
            datos["ubication"] = {
                "lat": geo.get("lat"),
                "lng": geo.get("lng"),
            }
            datos['geo_skipped'] = False
            datos['geo_reason'] = validation.get('reason', 'ok')
            print(f"   [Geo] Validación superada: {validation.get('reason')} | IA={validation.get('ai_decision', {}).get('coincide')}")

            # âœ… Nuevo: asignar departamento coherente con 17 dptos
            try:
                dep = get_departamento_by_city(datos.get("city"))
                if not dep:
                    dep = get_departamento_by_city(expected_city) or (geo.get("province") or "")
                datos["departamento"] = dep or ""
            except Exception:
                datos["departamento"] = ""

            print(f"   ño. Dirección verificada: {datos['direction']}")
            print(f"   ¡YOZ Coordenadas: {datos['ubication']['lat']}, {datos['ubication']['lng']}")

        except Exception as e:
            print(f"   ¿?O Error en geolocalización: {e}")

        return datos

    def process_job_image(self, image_path: str, additional_text: str = None,
                          manual_description: str = None, quality: int = 95,
                          upload_to_storage: bool = True,
                          upload_to_firestore: bool = True, timeout_ia: int = 60):

        print("\n=== âœ… PROCESANDO IMAGEN DE ANUNCIO DE EMPLEO ===")

        webp_buffer = self.image_converter.convert_to_webp(
            image_path, quality=quality, verbose=True
        )

        img_provider = (self.ai_config.get('image', {}) or {}).get('provider', 'ollama').lower()
        img_model = (self.ai_config.get('image', {}) or {}).get('model')
        print(f"ðŸ¤– Analizando imagen con {img_provider}...")
        if img_provider == 'openrouter':
            datos = self.openrouter_analyzer.analyze_job_image(
                webp_buffer, additional_text=additional_text, model=img_model, timeout=timeout_ia
            )
        else:
            datos = self.ollama_analyzer.analyze_job_image(
                webp_buffer, additional_text=additional_text, model=img_model, timeout=timeout_ia
            )

        print("\nðŸ” DEBUG - JSON devuelto por el modelo:")
        print(json.dumps(datos, indent=2, ensure_ascii=False))

        # Normalizar categorÃ­as: asegurar array de hasta 3 y 'categoria' principal
        datos = self._ensure_categorias(datos)

        if not datos.get("es_anuncio_empleo", False):
            print("âš ï¸ No es un anuncio de empleo. Deteniendo proceso.")
            return datos

        print("âœ… Es un anuncio de empleo vÃ¡lido")

        if datos.get("es_publicacion_personal") is True:
            motivo_personal = datos.get("razon_publicacion_personal") or "Detectada captura de pantalla de una publicacion personal."
            print("[WARN] Captura personal/red social detectada. Se omite este flyer.")
            datos["skippedUpload"] = True
            datos["skipReason"] = motivo_personal
            return datos

        datos = self._apply_manual_description(
            datos,
            manual_description,
            require_match_with_flyer=True,
            timeout_ia=timeout_ia,
        )

        # âœ… Agregamos geolocalizaciÃ³n ANTES de Firebase
        datos = self._add_geolocation_safe(datos)


        if upload_to_storage:
            thumbnail_buffer = None
            if image_path:
                try:
                    thumbnail_buffer = self.image_converter.create_thumbnail(
                        image_path,
                        max_size=(512, 512),
                        quality=80,
                        verbose=False
                    )
                except Exception as e:
                    print(f"   [WARN] No se pudo generar miniatura: {e}")

            print("\n== Subiendo imagen a Firebase Storage...")
            url = self.firebase_manager.upload_image_to_storage(
                webp_buffer, filename_prefix="job", folder="jobs", make_public=True
            )
            datos["url"] = url

            thumbnail_url = url
            if thumbnail_buffer:
                try:
                    thumbnail_url = self.firebase_manager.upload_image_to_storage(
                        thumbnail_buffer,
                        filename_prefix="job_thumb",
                        folder="jobs/thumbnails",
                        make_public=True
                    )
                except Exception as e:
                    print(f"   [WARN] No se pudo subir la miniatura: {e}")
                    thumbnail_url = url
            datos["thumbnailUrl"] = thumbnail_url

        # Subir a Firestore inmediatamente después de preparar la data
        if upload_to_firestore:
            datos["uid"] = datos.get("uid") or "1"
            print("\nðŸ§  Subiendo datos a Firestore...")
            # Estimar dÃ­as activos y fecha de desactivaciÃ³n
            datos = self._add_active_days(datos, timeout_ia=timeout_ia)
            # AÃ±adir bandera de estado activa antes de subir
            datos["isActive"] = True
            datos["source"] = "ai_bot"
            doc_id = self.firebase_manager.upload_to_firestore(
                datos, collection="jobs", auto_timestamps=True
            )
            datos["firestoreDocId"] = doc_id
            # Registrar en JSON local (compatibilidad sin operador |)
            registro = self._simplify_for_compare(datos)
            registro["firestoreDocId"] = doc_id
            self._append_local_job(registro)

        print("\nâœ… Proceso completado correctamente")
        return datos

    def _add_active_days(self, datos: Dict[str, Any], timeout_ia: int = 60) -> Dict[str, Any]:
        """
        Estima con IA cuÃ¡ntos dÃ­as debe permanecer activa la publicaciÃ³n.
        - Usa proveedor de TEXTO configurado (openrouter/ollama).
        - Si no hay suficiente informaciÃ³n, aplica 30 dÃ­as por defecto.
        - Nunca excede 30 dÃ­as.
        AÃ±ade los campos:
          - activeDays: int (1..30)
          - deactivateAt: ISO8601 (fecha/hora local + activeDays)
        """
        try:
            # Construir prompt para obtener un nÃºmero de dÃ­as 1..30
            prompt = (
                "Analiza el siguiente JSON de una oferta laboral y decide cuÃ¡ntos dÃ­as "
                "deberÃ­a permanecer activa la publicaciÃ³n desde su fecha de publicaciÃ³n. "
                "Si hay informaciÃ³n que sugiera corta duraciÃ³n (eventos puntuales, reemplazo temporal, "
                "promociÃ³n por pocos dÃ­as, fecha lÃ­mite cercana), elige menos dÃ­as. "
                "Si no hay suficiente informaciÃ³n, usa el estÃ¡ndar de 30 dÃ­as. "
                "Responde SOLO en JSON con las claves exactas: "
                "{\"activeDays\": <entero 1..30>, \"reason\": \"breve justificaciÃ³n\"}. "
                "El valor de 'activeDays' nunca debe ser mayor que 30."
            )

            text_provider = (self.ai_config.get('text', {}) or {}).get('provider', 'ollama').lower()
            text_model = (self.ai_config.get('text', {}) or {}).get('model')

            datos_contexto = {
                k: datos.get(k)
                for k in [
                    'position', 'title', 'description', 'company', 'city', 'direction',
                    'categoria', 'salary_range', 'vacancies', 'requeriments'
                ]
            }

            if text_provider == 'openrouter':
                res = self.openrouter_analyzer.analyze_text(
                    text=json.dumps(datos_contexto, ensure_ascii=False),
                    prompt=prompt,
                    model=text_model,
                    timeout=timeout_ia,
                )
                contenido = res.get('response', '{}')
                parsed = self.openrouter_analyzer.parse_json_response(contenido)
            else:
                res = self.ollama_analyzer.analyze_text(
                    text=json.dumps(datos_contexto, ensure_ascii=False),
                    prompt=prompt,
                    model=text_model,
                    timeout=timeout_ia,
                )
                contenido = res.get('response', '{}')
                parsed = self.ollama_analyzer.parse_json_response(contenido)

            # Obtener dÃ­as estimados, con defaults y lÃ­mites
            dias = parsed.get('activeDays')
            if dias is None:
                # tolerar variantes comunes
                dias = parsed.get('dias_activo') or parsed.get('dias')
            try:
                dias = int(dias)
            except Exception:
                dias = 30

            if dias < 1:
                dias = 1
            if dias > 30:
                dias = 30

            datos['activeDays'] = dias
            datos['deactivateAt'] = (datetime.now() + timedelta(days=dias))
        except Exception as e:
            # En caso de error, aplicar estÃ¡ndar
            datos['activeDays'] = 30
            datos['deactivateAt'] = (datetime.now() + timedelta(days=30))
            print(f"âš ï¸ No se pudo estimar activeDays con IA, usando 30: {e}")

        return datos


    def process_job_text(
        self,
        text: str,
        upload_to_firestore: bool = True,
        timeout_ia: int = 60,
        manual_description: str = None,
    ):
        print("\n=== ✅ PROCESANDO TEXTO DE ANUNCIO DE EMPLEO ===")

        text_provider = (self.ai_config.get('text', {}) or {}).get('provider', 'ollama').lower()
        text_model = (self.ai_config.get('text', {}) or {}).get('model')
        if text_provider == 'openrouter':
            datos = self.openrouter_analyzer.analyze_job_text(text, model=text_model, timeout=timeout_ia)
        else:
            datos = self.ollama_analyzer.analyze_job_text(text, model=text_model, timeout=timeout_ia)

        print("\n🧠 DEBUG - JSON completo del modelo:")
        print(json.dumps(datos, indent=2, ensure_ascii=False))

        datos = self._ensure_categorias(datos)

        if not datos.get("es_anuncio_empleo", False):
            print("⚠️ El texto no corresponde a un anuncio laboral.")
            return datos

        print("✅ Anuncio detectado correctamente")

        datos = self._apply_manual_description(
            datos,
            manual_description or text,
            timeout_ia=timeout_ia,
        )
        datos = self._add_geolocation(datos)

        if upload_to_firestore:
            datos["uid"] = datos.get("uid") or "1"
            datos = self._add_active_days(datos, timeout_ia=timeout_ia)
            datos["isActive"] = True
            datos["source"] = "ai_bot"
            doc_id = self.firebase_manager.upload_to_firestore(
                datos, collection="jobs", auto_timestamps=True
            )
            datos["firestoreDocId"] = doc_id
            self._append_local_job(self._simplify_for_compare(datos) | {"firestoreDocId": doc_id})

        print("\n✅ Finalizado con éxito")
        return datos

    def process_job(self, image_path: str = None, text: str = None,
                    quality: int = 95, upload_to_storage: bool = True,
                    upload_to_firestore: bool = True, timeout_ia: int = 60):

        if not image_path and not text:
            raise ValueError("âŒ Debes proporcionar al menos una imagen o texto")

        if image_path and not text:
            return self.process_job_image(
                image_path=image_path,
                quality=quality,
                upload_to_storage=upload_to_storage,
                upload_to_firestore=upload_to_firestore,
                timeout_ia=timeout_ia
            )

        if text and not image_path:
            return self.process_job_text(
                text=text,
                upload_to_firestore=upload_to_firestore,
                timeout_ia=timeout_ia,
                manual_description=text
            )

        return self.process_job_image(
            image_path=image_path,
            additional_text=text,
            manual_description=text,
            quality=quality,
            upload_to_storage=upload_to_storage,
            upload_to_firestore=upload_to_firestore,
            timeout_ia=timeout_ia
        )
