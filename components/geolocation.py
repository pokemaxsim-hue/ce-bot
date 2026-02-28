import os
import json
import requests
import urllib.parse
from dotenv import load_dotenv

# Cargar API Key desde .env
load_dotenv()
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


def extract_from_components(components, desired_type):
    """Extrae un campo (ciudad, país, postal, provincia) desde address_components."""
    for comp in components:
        if desired_type in comp.get("types", []):
            return comp.get("long_name") or comp.get("longText") or comp.get("name")
    return None


def get_location_details_new(country: str, city: str, address: str):
    """Consulta Places API (New) con searchText. Devuelve None si no hay resultados."""
    if not API_KEY:
        raise ValueError("[Geo] Falta GOOGLE_MAPS_API_KEY en .env")

    query = f"{address}, {city}, {country}".strip().strip(",")
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.name,places.displayName,places.formattedAddress,"
            "places.shortFormattedAddress,places.location,places.addressComponents,"
            "places.types,places.googleMapsUri,places.businessStatus,places.editorialSummary"
        ),
    }
    body = {
        "textQuery": query,
        "languageCode": "es",
        "regionCode": "PY",
    }
    try:
        print(f"[GeoNew] POST {url} q='{query}'")
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=12)
        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            print(f"[GeoNew] JSON parse error (status={status_code}). Body(head): {resp.text[:500]}")
            return None
        places = data.get("places") or []
        if not places:
            print(f"[GeoNew] Sin resultados (status={status_code}) msg={(data.get('error') or {}).get('message')}")
            return None

        p0 = places[0]
        place_id = p0.get("id") or (p0.get("name") or "").split("/")[-1]
        formatted_address = p0.get("formattedAddress")
        short_address = p0.get("shortFormattedAddress")
        loc = (p0.get("location") or {}).get("latLng") or p0.get("location") or {}
        lat = loc.get("latitude") or loc.get("lat")
        lng = loc.get("longitude") or loc.get("lng")
        components = p0.get("addressComponents") or []
        display_name = p0.get("displayName") or {}
        place_name = ""
        if isinstance(display_name, dict):
            place_name = display_name.get("text") or ""
        elif isinstance(display_name, str):
            place_name = display_name
        place_name = place_name or p0.get("name") or ""
        editorial = p0.get("editorialSummary") or {}
        place_summary = ""
        if isinstance(editorial, dict):
            place_summary = editorial.get("text") or editorial.get("overview") or ""
        elif isinstance(editorial, str):
            place_summary = editorial
        place_types = p0.get("types") or []
        google_maps_uri = p0.get("googleMapsUri") or ""
        business_status = p0.get("businessStatus") or ""

        city_name = (
            extract_from_components(components, "locality")
            or extract_from_components(components, "administrative_area_level_2")
            or extract_from_components(components, "sublocality")
        )
        province = extract_from_components(components, "administrative_area_level_1")
        country_name = extract_from_components(components, "country")
        postal_code = extract_from_components(components, "postal_code")

        out = {
            "status": "OK",
            "formatted_address": formatted_address,
            "direction": short_address or formatted_address,
            "lat": lat,
            "lng": lng,
            "city": city_name,
            "province": province,
            "country": country_name,
            "postal_code": postal_code,
            "place_id": place_id,
            "place_name": place_name,
            "place_summary": place_summary,
            "place_types": place_types,
            "place_google_uri": google_maps_uri,
            "place_business_status": business_status,
            "place_address_components": components,
        }
        print(f"[GeoNew] OK id='{place_id}' addr='{formatted_address}' lat={lat} lng={lng}")
        return out
    except Exception as e:
        print(f"[GeoNew] Error en searchText: {e}")
        return None

def get_location_details(country: str, city: str, address: str):
    """
    Obtiene ubicación usando Google Places (Text Search + Place Details).

    Retorna:
    - direction (formatted_address)
    - lat, lng
    - city (locality)
    - province (administrative_area_level_1)
    - country
    - postal_code
    - place_id
    """
    if not API_KEY:
        raise ValueError("❌ No se encontró GOOGLE_MAPS_API_KEY en el archivo .env")

    # Construimos la consulta con el mayor contexto posible
    query = f"{address}, {city}, {country}".strip().strip(",")
    encoded_query = urllib.parse.quote(query)

    # Intentar primero con Places API (New); si devuelve resultado, retornamos
    try:
        res_new = get_location_details_new(country=country, city=city, address=address)
        if res_new:
            return res_new
    except Exception as e:
        print(f"[Geo] Fallback al API clásico por error en New: {e}")
    try:
        print(f"[Geo] Inputs -> country='{country}' city='{city}' address='{address}'")
    except Exception:
        pass

    # 1) Text Search para obtener place_id + geometry rápido
    ts_url = (
        f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={encoded_query}&key={API_KEY}"
    )
    try:
        print(f"[Geo] Query: '{query}' | URL: {ts_url}")
        ts_resp = requests.get(ts_url, timeout=12)
        status_code = ts_resp.status_code
        try:
            ts_data = ts_resp.json()
        except Exception:
            ts_data = {"status": "PARSE_ERROR", "raw": ts_resp.text[:500]}
            print(f"[Geo] TextSearch JSON parse error (status={status_code}). Body(head): {ts_data.get('raw')}")
    except Exception as e:
        print(f"[Geo] TextSearch request error: {e}")
        return None

    if ts_data.get("status") != "OK" or not ts_data.get("results"):
        print(
            f"[Geo] TextSearch no OK. status={ts_data.get('status')} "
            f"error={ts_data.get('error_message')} results={len(ts_data.get('results', []))}"
        )
        return None

    ts_first = ts_data["results"][0]
    place_id = ts_first.get("place_id")
    formatted_address = ts_first.get("formatted_address")
    location = (ts_first.get("geometry") or {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")
    place_name = ts_first.get("name") or ""
    place_types = ts_first.get("types") or []
    business_status = ts_first.get("business_status") or ""
    place_summary = ""
    maps_uri = ""
    print(f"[Geo] TextSearch OK. place_id={place_id} addr='{formatted_address}' lat={lat} lng={lng}")

    # 2) Place Details para address_components (ciudad, provincia, país, etc.)
    components = []
    try:
        if place_id:
            fields = (
                "address_component,geometry,formatted_address,place_id,name,"
                "types,business_status,url,editorial_summary,website"
            )
            det_url = (
                f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields={fields}&key={API_KEY}"
            )
            print(f"[Geo] Place Details URL: {det_url}")
            det_resp = requests.get(det_url, timeout=12)
            det_status = det_resp.status_code
            try:
                det_data = det_resp.json()
            except Exception:
                print(f"[Geo] Details JSON parse error (status={det_status}). Body(head): {det_resp.text[:500]}")
                det_data = {}
            if det_data.get("status") == "OK" and det_data.get("result"):
                result = det_data["result"]
                components = result.get("address_components", [])
                # Si details trae dirección/geometry más precisa, úsala
                formatted_address = result.get("formatted_address", formatted_address)
                loc2 = (result.get("geometry") or {}).get("location")
                if loc2:
                    lat = loc2.get("lat", lat)
                    lng = loc2.get("lng", lng)
                place_name = result.get("name") or place_name
                place_types = result.get("types") or place_types
                business_status = result.get("business_status") or business_status
                editorial = result.get("editorial_summary") or {}
                if isinstance(editorial, dict):
                    place_summary = editorial.get("overview") or editorial.get("text") or place_summary
                elif isinstance(editorial, str):
                    place_summary = editorial
                maps_uri = result.get("url") or result.get("website") or maps_uri
                print("[Geo] Details OK. components_len=", len(components))
            else:
                print(
                    f"[Geo] Details no OK. status={det_data.get('status')} error={det_data.get('error_message')}"
                )
    except Exception as e:
        # En caso de fallo en details, seguimos con los datos de Text Search
        print(f"[Geo] Error en Place Details: {e}")

    # 🔍 Extraer datos clave
    city_name = (
        extract_from_components(components, "locality")
        or extract_from_components(components, "administrative_area_level_2")
        or extract_from_components(components, "sublocality")
    )
    province = extract_from_components(components, "administrative_area_level_1")
    country_name = extract_from_components(components, "country")
    postal_code = extract_from_components(components, "postal_code")

    if not maps_uri and place_id:
        maps_uri = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    out = {
        "status": "OK",
        "formatted_address": formatted_address,
        "direction": formatted_address,  # compatibilidad con main.py
        "lat": lat,
        "lng": lng,
        "city": city_name,
        "province": province,
        "country": country_name,
        "postal_code": postal_code,
        "place_id": place_id,
        "place_name": place_name,
        "place_summary": place_summary,
        "place_types": place_types,
        "place_google_uri": maps_uri,
        "place_business_status": business_status,
        "place_address_components": components,
    }
    try:
        print(
            f"[Geo] Resultado final: city='{out['city']}' prov='{out['province']}' country='{out['country']}' "
            f"lat={out['lat']} lng={out['lng']}"
        )
    except Exception:
        pass
    return out


