"""
Módulo para análisis de imágenes y texto usando Ollama LOCAL.
Versión modificada para funcionar con Ollama en localhost.
"""

# ============================================================================
# FIX CRÍTICO PARA WINDOWS: Configurar UTF-8 ANTES de cualquier print
# ============================================================================
import sys
import os

if sys.platform == 'win32':
    try:
        # Python 3.7+
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 3.6 o anterior
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    # Configurar variable de entorno
    os.environ['PYTHONIOENCODING'] = 'utf-8'
# ============================================================================

import json
import base64
import re
from typing import Dict, Any, Union
from io import BytesIO
import time
import requests
from dotenv import load_dotenv
from components.municipios_utils import get_allowed_cities_prompt

# Cargar variables de entorno
load_dotenv()


class OllamaLocalAnalyzer:
    """Analizador de imágenes y texto usando Ollama LOCAL."""
    
    # Prompt por defecto para análisis de anuncios de empleo
    DEFAULT_JOB_PROMPT = """Analiza la imagen adjunta y determina si es un anuncio de empleo.

Si NO es un anuncio de empleo, responde ÚNICAMENTE:
{
  "es_anuncio_empleo": false,
  "razon": "La imagen no corresponde a una oferta de empleo válida."
}

Si SÍ es un anuncio de empleo, responde en JSON (deja campos vacíos si no están presentes):
{
  "es_anuncio_empleo": true,
  "es_publicacion_personal": true o false (true si la imagen es una captura de pantalla de WhatsApp, Facebook, Instagram o cualquier red social/mensajería donde se vea claramente el nombre o foto del publicador original; false en caso contrario),
  "razon_publicacion_personal": "explica en una frase si marcaste true",
  "categoria": "selecciona el que más se adecue de entre las opciones:
    Tecnología e Informática,
    Ventas y Comercial,
    Recursos Humanos,
    Marketing y Publicidad,
    Finanzas y Contabilidad,
    Administración,
    Educación,
    Salud y Medicina,
    Ingeniería,
    Construcción,
    Logística y Transporte,
    Servicio al Cliente,
    Diseño Gráfico,
    Desarrollo Web,
    Análisis de Datos,
    Seguridad,
    Legal y Asesoría,
    Manufactura,
    Hogar y Limpieza,
    Gastronomía y Cocina,
    Hostelería y Turismo,
    Agricultura,
    Mecánica y Reparación,
    Fotografía y Video,
    Redacción y Copywriting,
    Community Manager,
    Recursos Audiovisuales,
    Calidad y Control,
    Proyectos,
    Consultoría,
    Investigación Científica,
    Arte y Diseño,
    Deportes,
    Entretenimiento,
    Comunicación,
    Relaciones Públicas,
    Energías Renovables,
    Medio Ambiente,
    Sostenibilidad,
    Otros (en caso de que no se ajuste a ninguno)",

  "position": "nombre del puesto",
  "title": "título CORTO y conciso que resuma la oferta (máximo 5-6 palabras)",
  "description": "redacta una descripción sintética como si fuera la publicación directa de quien busca contratar. Debe sonar natural, como un anuncio real de empleo publicado por la empresa o reclutador. EVITA frases como 'Empresa busca...', 'Se solicita...'. Usa un tono directo de oferta laboral",
  "city": "ciudad",
  "direction": "dirección COMPLETA con todas las referencias mencionadas (ej: 'Shopping la Galería', 'zona Centro', 'Av. España c/ Brasil', nombres de edificios, barrios, etc.)",
  "company": "empresa",
  "vacancies": "número de vacantes",
  "requeriments": ["requisito 1", "requisito 2", "requisito 3", "etc."] (IMPORTANTE: devolver como ARRAY de strings, cada requisito en un elemento separado. Si no hay requisitos específicos, devolver array vacío []),
  "salary_range": "salario",
  "phoneNumber": "Número de teléfono en formato +595XXXXXXXXX. Si el número viene con 0 inicial (ej: '0981 123456'), eliminar el 0 y agregar +595. Si ya tiene +595 o 595, mantenerlo. Si no tiene prefijo ni 0 inicial, agregar +595. Remover espacios y caracteres especiales.",
  "email": "correo",
  "website": "sitio web"
}

IMPORTANTE:
- "es_publicacion_personal": Debe ser true solo cuando la imagen parezca una captura de conversación/red social donde se vea el nombre, foto o perfil personal del publicador original (WhatsApp, Facebook, Instagram, etc.). Si es un flyer genérico sin datos personales visibles, deja este campo en false.
- Si marcas "es_publicacion_personal": true, llena también "razon_publicacion_personal" explicando brevemente lo observado (ej: "Captura de WhatsApp mostrando el nombre Juan Pérez").
- "title": Breve y directo (máximo 5-6 palabras)
- "description": Redactar como una publicación real de empleo, sin descripciones externas o narrativas en tercera persona
- "direction": Extraer la dirección COMPLETA con todos los detalles y referencias
- "requeriments": DEBE ser un array de strings. Cada requisito separado. Ejemplo: ["Experiencia mínima de 2 años", "Conocimientos en Excel", "Disponibilidad inmediata"]
- "phoneNumber": Sin el 0 inicial, si deccides incluir el numero de teléfono en descripcion SÍ coloca el numero de telefono con el 0 incial e la descicpion pero aqui en este compo phoneNumber SIEMPRE mantenlo sin el 0 inicial
- Si algún dato no está explícito, déjalo vacío

Responde SOLO con el JSON.;"""

    # Prompt para análisis solo de texto
    DEFAULT_TEXT_JOB_PROMPT = """Analiza el texto adjunto y determina si es un anuncio de empleo.

Si NO es un anuncio de empleo, responde ÚNICAMENTE:
{
  "es_anuncio_empleo": false,
  "razon": "Explicación breve de por qué no es un anuncio de empleo"
}

Si SÍ es un anuncio de empleo, responde en el siguiente formato JSON (si algún dato no está presente, deja el campo vacío ""):
Responde en JSON (deja campos vacíos si no están presentes, pero intenta inferir información del contexto):
{
  "es_anuncio_empleo": true,
  "position": "nombre del puesto",
  "title": "título CORTO y conciso que resuma la oferta (máximo 5-6 palabras). Mejóralo si es necesario",
  "description": "redacta una descripción sintética como si fuera la publicación directa de quien busca contratar. Debe sonar natural, como un anuncio real de empleo. EVITA frases como 'Empresa busca...', 'Se solicita...'. Mejora y estructura la información del texto original manteniendo un tono directo de oferta laboral",
  "city": "ciudad (intenta extraerla del texto)",
  "categoria": "selecciona el que más se adecue de entre las opciones:
    Tecnología e Informática,
    Ventas y Comercial,
    Recursos Humanos,
    Marketing y Publicidad,
    Finanzas y Contabilidad,
    Administración,
    Educación,
    Salud y Medicina,
    Ingeniería,
    Construcción,
    Logística y Transporte,
    Servicio al Cliente,
    Diseño Gráfico,
    Desarrollo Web,
    Análisis de Datos,
    Seguridad,
    Legal y Asesoría,
    Manufactura,
    Hogar y Limpieza,
    Gastronomía y Cocina,
    Hostelería y Turismo,
    Agricultura,
    Mecánica y Reparación,
    Fotografía y Video,
    Redacción y Copywriting,
    Community Manager,
    Recursos Audiovisuales,
    Calidad y Control,
    Proyectos,
    Consultoría,
    Investigación Científica,
    Arte y Diseño,
    Deportes,
    Entretenimiento,
    Comunicación,
    Relaciones Públicas,
    Energías Renovables,
    Medio Ambiente,
    Sostenibilidad,
    Otros (en caso de que no se ajuste a ninguno)",
  "direction": "dirección COMPLETA con todas las referencias mencionadas en el texto (ej: 'Shopping la Galería', 'zona Centro', 'Av. España c/ Brasil', edificios, barrios específicos, referencias). No simplificar ni omitir información",
  "company": "empresa (intenta identificarla del texto)",
  "vacancies": "número de vacantes",
  "requeriments": ["requisito 1", "requisito 2", "requisito 3", "etc."] (IMPORTANTE: devolver como ARRAY de strings, cada requisito en un elemento separado. Extrae del texto o genera basados en el puesto. Si no hay requisitos, devolver array vacío []),
  "salary_range": "salario (si está mencionado)",
  "phoneNumber": "Número de teléfono en formato +595XXXXXXXXX. Si el número viene con 0 inicial (ej: '0981 123456'), eliminar el 0 y agregar +595. Si ya tiene +595 o 595, mantenerlo. Si no tiene prefijo ni 0 inicial, agregar +595. Remover espacios y caracteres especiales.", 
  IMPORTANTE: Si decides mencionar el número de teléfono dentro del campo "description", 
  en ese caso SÍ incluye el 0 inicial para que sea más legible para los usuarios 
  (ej: "Contactar al 0981-234-567"). Esta es la única excepción - el campo phoneNumber 
  debe mantener el formato sin el 0 inicial en todos los casos."email": "correo electrónico",
  "website": "sitio web"
}

IMPORTANTE:
- "title": Breve y directo (máximo 5-6 palabras), mejóralo si el original es confuso
- "description": Redactar como una publicación real de empleo, sin narrativas externas en tercera persona
- "direction": Extraer COMPLETA con todos los detalles (shoppings, zonas, barrios, calles, referencias, edificios)
- "requeriments": DEBE ser un array de strings. Cada requisito separado y conciso. Ejemplo: ["Mayor de edad", "Experiencia en ventas", "Manejo de redes sociales"]
- "phoneNumber": Almacenar SIEMPRE sin el 0 inicial (ej: "981234567" en lugar de "0981234567"). 
  IMPORTANTE: Si decides mencionar el número de teléfono dentro del campo "description", 
  en ese caso SÍ incluye el 0 inicial para que sea más legible para los usuarios 
  (ej: "Contactar al 0981-234-567"). Esta es la única excepción - el campo phoneNumber 
  debe mantener el formato sin el 0 inicial en todos los casos.
- Si algún dato no está explícito pero puede inferirse del contexto, inclúyelo
- Si algún dato no está explícito, déjalo vacío

Responde SOLO con el JSON."""
    
    def __init__(self, 
                 api_url: str = "http://localhost:11434/api/generate",
                 model: str = "qwen3-vl:235b-cloud",
                 timeout: int = 60):
        """
        Inicializa el analizador de Ollama LOCAL.
        
        Args:
            api_url: URL de tu Ollama local (por defecto: http://localhost:11434/api/generate)
            model: Modelo a usar en Ollama (por defecto: qwen3-vl:235b-cloud)
            timeout: Timeout en segundos (aumentado para procesamiento local)
        """
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        
        print(f"✅ Ollama Local configurado")
        print(f"   URL: {self.api_url}")
        print(f"   Modelo: {self.model}")
        print(f"   Timeout: {timeout}s")
        
        # Verificar conexión
        self._check_connection()
    
    def _check_connection(self):
        """Verifica si Ollama está disponible."""
        try:
            # Intentar conectar a Ollama
            response = requests.get(
                self.api_url.replace("/api/generate", "/api/tags"),
                timeout=5
            )
            if response.status_code == 200:
                print(f"✅ Conexión exitosa con Ollama")
                models = response.json().get("models", [])
                if models:
                    print(f"   Modelos disponibles: {len(models)}")
            else:
                print(f"⚠️  Ollama respondió con status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"❌ No se pudo conectar a Ollama en {self.api_url}")
            print(f"   Asegúrate de que Ollama está corriendo: ollama serve")
        except Exception as e:
            print(f"⚠️  Error al verificar conexión: {str(e)}")
    
    def _convert_to_base64(self, image_data: Union[str, bytes, BytesIO]) -> str:
        """
        Convierte una imagen a base64.
        
        Args:
            image_data: Ruta del archivo, bytes o BytesIO
        
        Returns:
            String en base64
        """
        if isinstance(image_data, str):
            with open(image_data, "rb") as f:
                return base64.b64encode(f.read()).decode()
        elif isinstance(image_data, bytes):
            return base64.b64encode(image_data).decode()
        else:  # BytesIO
            image_data.seek(0)
            return base64.b64encode(image_data.read()).decode()
    
    def analyze_image(
        self,
        image_data: Union[str, bytes, BytesIO],
        prompt: str = None,
        additional_text: str = None,
        model: str = None,
        timeout: int = None,
        max_retries: int = 10,
        retry_delay: int = 2
    ) -> Dict[str, Any]:
        """
        Analiza una imagen usando Ollama LOCAL.
        
        Args:
            image_data: Ruta, bytes o BytesIO de la imagen
            prompt: Prompt personalizado (usa DEFAULT_JOB_PROMPT si no se proporciona)
            additional_text: Texto adicional para enviar junto con la imagen
            model: Modelo a usar (usa self.model si no se proporciona)
            timeout: Timeout en segundos (usa self.timeout si no se proporciona)
            max_retries: Número máximo de reintentos
            retry_delay: Segundos de espera entre reintentos
        
        Returns:
            Respuesta del modelo con el análisis
        """
        model = model or self.model
        timeout = timeout or self.timeout
        prompt = prompt or self.DEFAULT_JOB_PROMPT

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

        # Añadir restricción de ciudades permitidas desde components/municipios.json
        try:
            ciudades_txt = get_allowed_cities_prompt(
                'RESTRICCIÓN PARA EL CAMPO "city": '
                'elige SOLO una ciudad EXACTA de la lista. '
                'Si no corresponde ninguna, deja "city" vacío.'
            )
            if ciudades_txt:
                prompt = f"{prompt}\n\n{ciudades_txt}"
        except Exception:
            # Si falla la carga, continuamos sin la restricción
            pass
        
        # Si hay texto adicional, agregarlo al prompt
        if additional_text:
            prompt = f"{prompt}\n\nTexto adicional proporcionado:\n{additional_text}"
        
        # Convertir imagen a base64
        img_base64 = self._convert_to_base64(image_data)
        
        # Payload para Ollama (usa API /generate con soporte de imágenes)
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [img_base64],
            "stream": False,
            "temperature": 0.7
        }
        
        # Sistema de reintentos
        intento = 0
        while intento < max_retries:
            intento += 1
            try:
                print(f"🔄 Intento {intento}/{max_retries} - Analizando imagen con {model}...")
                
                tiempo_inicio = time.time()
                
                response = requests.post(
                    self.api_url,
                    json=payload,
                    timeout=timeout
                )
                
                tiempo_transcurrido = time.time() - tiempo_inicio
                
                print(f"   Status Code: {response.status_code} (Tiempo: {tiempo_transcurrido:.2f}s)")
                
                if response.status_code != 200:
                    print(f"   Error: {response.text[:200]}")
                    raise requests.exceptions.RequestException(f"Status {response.status_code}")
                
                print(f"✅ Análisis completado en {tiempo_transcurrido:.2f}s")
                
                return {
                    "response": response.json().get("response", response.json()),
                    "status": "success",
                    "tiempo_procesamiento": tiempo_transcurrido
                }
                
            except (requests.exceptions.Timeout, requests.exceptions.RequestException, Exception) as e:
                tiempo_transcurrido = time.time() - tiempo_inicio
                print(f"❌ Error en intento {intento}: {str(e)} ({tiempo_transcurrido:.2f}s)")
                
                if intento >= max_retries:
                    raise Exception(f"Máximo de {max_retries} reintentos alcanzado")
                
                print(f"⚡ Reintentando en {retry_delay}s...")
                time.sleep(retry_delay)
    
    def analyze_text(
        self,
        text: str,
        prompt: str = None,
        model: str = None,
        timeout: int = None,
        max_retries: int = 10,
        retry_delay: int = 2
    ) -> Dict[str, Any]:
        """
        Analiza solo texto usando Ollama LOCAL (sin imagen).
        
        Args:
            text: Texto a analizar
            prompt: Prompt personalizado
            model: Modelo a usar
            timeout: Timeout en segundos
            max_retries: Número máximo de reintentos
            retry_delay: Segundos de espera entre reintentos
        
        Returns:
            Respuesta del modelo con el análisis
        """
        model = model or self.model
        timeout = timeout or self.timeout
        prompt = prompt or self.DEFAULT_TEXT_JOB_PROMPT

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

        # Añadir restricción de ciudades permitidas desde components/municipios.json
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
        
        # Combinar prompt con el texto
        full_prompt = f"{prompt}\n\nTexto a analizar:\n{text}"
        
        # Payload para Ollama (sin imágenes)
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "temperature": 0.7
        }
        
        # Sistema de reintentos
        intento = 0
        while intento < max_retries:
            intento += 1
            try:
                print(f"🔄 Intento {intento}/{max_retries} - Analizando texto con {model}...")
                
                tiempo_inicio = time.time()
                
                response = requests.post(
                    self.api_url,
                    json=payload,
                    timeout=timeout
                )
                
                tiempo_transcurrido = time.time() - tiempo_inicio
                
                print(f"   Status Code: {response.status_code} (Tiempo: {tiempo_transcurrido:.2f}s)")
                
                if response.status_code != 200:
                    print(f"   Error: {response.text[:200]}")
                    raise requests.exceptions.RequestException(f"Status {response.status_code}")
                
                print(f"✅ Análisis completado en {tiempo_transcurrido:.2f}s")
                
                return {
                    "response": response.json().get("response", response.json()),
                    "status": "success",
                    "tiempo_procesamiento": tiempo_transcurrido
                }
                
            except (requests.exceptions.Timeout, requests.exceptions.RequestException, Exception) as e:
                tiempo_transcurrido = time.time() - tiempo_inicio
                print(f"❌ Error en intento {intento}: {str(e)} ({tiempo_transcurrido:.2f}s)")
                
                if intento >= max_retries:
                    raise Exception(f"Máximo de {max_retries} reintentos alcanzado")
                
                print(f"⚡ Reintentando en {retry_delay}s...")
                time.sleep(retry_delay)
    
    def parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Extrae y parsea el JSON de la respuesta del modelo.
        
        Args:
            content: Contenido de texto de la respuesta
        
        Returns:
            Diccionario con los datos parseados
        """
        # Intentar parsear directamente
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Buscar JSON en el texto usando regex
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, content, re.DOTALL)
        
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        # Si no se pudo parsear
        return {
            "error": "No se pudo parsear la respuesta como JSON",
            "contenido_original": content[:500]
        }
    
    def analyze_job_image(
        self,
        image_data: Union[str, bytes, BytesIO],
        additional_text: str = None,
        model: str = None,
        timeout: int = None
    ) -> Dict[str, Any]:
        """
        Método simplificado para analizar anuncios de empleo desde imagen.
        
        Args:
            image_data: Ruta, bytes o BytesIO de la imagen
            additional_text: Texto adicional para complementar el análisis
            model: Modelo a usar
            timeout: Timeout en segundos
        
        Returns:
            Diccionario con los datos del anuncio parseados
        """
        # Analizar imagen
        resultado = self.analyze_image(
            image_data=image_data,
            additional_text=additional_text,
            model=model,
            timeout=timeout
        )
        
        # Extraer contenido
        contenido = resultado.get("response", "No hay respuesta")
        
        # Parsear JSON
        return self.parse_json_response(contenido)
    
    def analyze_job_text(
        self,
        text: str,
        model: str = None,
        timeout: int = None
    ) -> Dict[str, Any]:
        """
        Método simplificado para analizar anuncios de empleo desde texto puro.
        
        Args:
            text: Texto del anuncio a analizar
            model: Modelo a usar
            timeout: Timeout en segundos
        
        Returns:
            Diccionario con los datos del anuncio parseados
        """
        # Analizar texto
        resultado = self.analyze_text(
            text=text,
            model=model,
            timeout=timeout
        )
        
        # Extraer contenido
        contenido = resultado.get("response", "No hay respuesta")
        
        # Parsear JSON
        return self.parse_json_response(contenido)


    def is_duplicate_job(
        self,
        new_job: Dict[str, Any],
        existing_jobs: list,
        model: str = None,
        timeout: int = None
    ) -> Dict[str, Any]:
        """
        Evalúa con el modelo si un nuevo job es duplicado (o demasiado similar)
        a alguno de los existentes. Devuelve un dict parseado del JSON del modelo:
        {
          "duplicado": true|false,
          "indice": number|-1,
          "similitud": 0-100,
          "explicacion": "..."
        }
        """
        instrucciones = (
            "Eres un evaluador de duplicados de ofertas laborales. "
            "Te daré un NUEVO_JOB y una lista JOBS_EXISTENTES. "
            "Compara por company, position, title, description, city, direction, phoneNumber, email, website. "
            "Tolera pequeñas variaciones (tildes, mayúsculas/minúsculas, sinónimos). "
            "Si encuentras uno esencialmente igual/demasiado similar (misma oferta), marca duplicado. "
            "Evita falsos positivos: si hay dudas relevantes, responde que NO es duplicado. "
            "Responde SOLO con JSON con las claves: duplicado (boolean), indice (entero 0-based o -1), similitud (0-100), explicacion (string)."
        )
        instrucciones += " Usa únicamente los datos suministrados en esos JSON. No inventes ni uses fuentes externas. Responde solo con JSON."

        texto_datos = (
            "NUEVO_JOB:\n" + json.dumps(new_job, ensure_ascii=False) +
            "\n\nJOBS_EXISTENTES:\n" + json.dumps(existing_jobs, ensure_ascii=False)
        )

        modelo_comparacion = model or "minimax-m2:cloud"

        resultado = self.analyze_text(
            text=texto_datos,
            prompt=instrucciones,
            model=modelo_comparacion,
            timeout=timeout
        )

        contenido = resultado.get("response", "{}")
        return self.parse_json_response(contenido)

# Ejemplo de uso
if __name__ == "__main__":
    # IMPORTANTE: Asegúrate de que Ollama está corriendo
    # En la terminal ejecuta: ollama serve
    # Y luego descarga el modelo: ollama pull llava:latest
    
    print("\n" + "="*80)
    print("INICIANDO OLLAMA LOCAL ANALYZER")
    print("="*80 + "\n")
    
    # Inicializar analizador con Ollama local
    analyzer = OllamaLocalAnalyzer(
        api_url="http://localhost:11434/api/generate",
        model="llava:latest",  # Modelo que soporta visión
        timeout=120  # Timeout más largo para procesamiento local
    )
    
    print("\n" + "="*80)
    print("EJEMPLO 1: Analizar imagen")
    print("="*80)
    
    try:
        # Analizar una imagen
        resultado = analyzer.analyze_job_image("ee.webp")
        
        # Mostrar resultado
        print("\n📊 RESULTADO DEL ANÁLISIS:")
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        
        if resultado.get("es_anuncio_empleo"):
            print(f"\n✅ Anuncio de empleo detectado:")
            print(f"   Puesto: {resultado.get('position', 'N/A')}")
            print(f"   Ciudad: {resultado.get('city', 'N/A')}")
            print(f"   Empresa: {resultado.get('company', 'N/A')}")
        else:
            print(f"\n⚠️  No es un anuncio de empleo")
            if "error" not in resultado:
                print(f"   Razón: {resultado.get('razon', 'N/A')}")
    
    except FileNotFoundError:
        print("⚠️  Archivo 'ee.webp' no encontrado. Saltando ejemplo de imagen.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    print("\n" + "="*80)
    print("EJEMPLO 2: Analizar solo texto (sin imagen)")
    print("="*80)
    
    # Analizar solo texto
    texto_anuncio = """
    SE BUSCA DESARROLLADOR PYTHON
    
    Empresa: Tech Solutions SA
    Ubicación: Asunción, Paraguay
    Salario: 3.000.000 - 4.500.000 Gs
    
    Requisitos:
    - 2 años de experiencia en Python
    - Conocimientos en Django y Flask
    - Trabajo en equipo
    
    Contacto: rrhh@techsolutions.com.py
    Tel: 021-456789
    """
    
    try:
        resultado2 = analyzer.analyze_job_text(texto_anuncio)
        
        print("\n📊 RESULTADO DEL ANÁLISIS DE TEXTO:")
        print(json.dumps(resultado2, indent=2, ensure_ascii=False))
        
        if resultado2.get("es_anuncio_empleo"):
            print(f"\n✅ Anuncio de empleo detectado:")
            print(f"   Puesto: {resultado2.get('position', 'N/A')}")
            print(f"   Ciudad: {resultado2.get('city', 'N/A')}")
            print(f"   Empresa: {resultado2.get('company', 'N/A')}")
            print(f"   Salario: {resultado2.get('salary_range', 'N/A')}")
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
