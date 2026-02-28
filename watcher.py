"""
Servidor de monitoreo en tiempo real con sistema de cola.
Procesa archivos JSON de WhatsApp conforme se agregan a la carpeta.
Compatible con el formato de WhatsApp downloader.
VERSIÓN CORREGIDA: Pasa el texto del mensaje al analizar imágenes.
"""

import time
import json
import os
import threading
from queue import Queue
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from batch_image_processor import BatchMultiFormatProcessor

DATA_DIR = os.getenv("DATA_DIR", ".")
DEFAULT_MESSAGES_FOLDER = os.getenv(
    "WHATSAPP_MESSAGES_DIR",
    os.path.join(DATA_DIR, "anuncios_empleo", "mensajes")
)
DEFAULT_IMAGES_FOLDER = os.getenv(
    "WHATSAPP_IMAGES_DIR",
    os.path.join(DATA_DIR, "anuncios_empleo", "imagenes")
)


class RealTimeFolderWatcher(FileSystemEventHandler):
    """
    Escucha la carpeta de mensajes JSON y los agrega a la cola de procesamiento.
    """
    def __init__(self, processor: BatchMultiFormatProcessor, file_queue: Queue):
        self.processor = processor
        self.file_queue = file_queue
        self.processed_files = set()  # Evitar reprocesar

    def on_created(self, event):
        """Cuando se crea un nuevo archivo JSON, lo agrega a la cola."""
        if event.is_directory:
            return

        file_path = event.src_path
        
        # Solo procesar archivos JSON
        if not file_path.endswith('.json'):
            return
            
        # Evitar reprocesar el mismo archivo
        if file_path in self.processed_files:
            return

        print(f"\n👀 Nuevo mensaje detectado: {Path(file_path).name}")

        # Verificar que el archivo esté completamente escrito
        time.sleep(0.5)  # Pequeña espera para asegurar escritura completa

        try:
            # Leer y validar el JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Verificar que tenga la estructura esperada
            if 'contacto' in data and 'texto' in data:
                self.file_queue.put(file_path)
                self.processed_files.add(file_path)
                print(f"🧾 Mensaje encolado para análisis")
                print(f"   📱 Contacto: {data.get('contacto', 'Desconocido')}")
                print(f"   💬 Texto: {data.get('texto', '(sin texto)')[:50]}...")
            else:
                print(f"⚠️ JSON no tiene el formato esperado")
                
        except json.JSONDecodeError:
            print(f"⚠️ Error al leer JSON, puede estar incompleto")
        except Exception as e:
            print(f"⚠️ Error procesando archivo: {e}")


class RealTimeProcessor:
    """
    Administra la cola y el procesamiento continuo de mensajes en tiempo real.
    """
    def __init__(self, messages_folder: str = DEFAULT_MESSAGES_FOLDER,
                 images_folder: str = DEFAULT_IMAGES_FOLDER):
        self.messages_folder = messages_folder
        self.images_folder = images_folder
        self.processor = BatchMultiFormatProcessor()
        self.file_queue = Queue()
        self._stop_flag = threading.Event()
        
        # Crear carpetas si no existen
        Path(messages_folder).mkdir(parents=True, exist_ok=True)
        Path(images_folder).mkdir(parents=True, exist_ok=True)

    def start(self):
        """Inicia el observador y el hilo de procesamiento."""
        print("\n" + "=" * 80)
        print("🟢 SERVIDOR DE ANÁLISIS EN TIEMPO REAL DE ANUNCIOS DE EMPLEO")
        print("=" * 80)
        print(f"📂 Carpeta de mensajes: {self.messages_folder}")
        print(f"🖼️  Carpeta de imágenes: {self.images_folder}")
        print("📡 Esperando nuevos mensajes de WhatsApp...\n")

        # Iniciar observador
        event_handler = RealTimeFolderWatcher(self.processor, self.file_queue)
        observer = Observer()
        observer.schedule(event_handler, path=self.messages_folder, recursive=False)
        observer.start()

        # Iniciar hilo de procesamiento
        worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        worker_thread.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Servidor detenido por el usuario")
            self._stop_flag.set()
            observer.stop()

        observer.join()
        worker_thread.join()

    def _worker_loop(self):
        """Bucle principal que procesa mensajes de la cola uno por uno."""
        while not self._stop_flag.is_set():
            try:
                json_path = self.file_queue.get(timeout=1)
            except:
                continue  # Esperar nuevos archivos

            print(f"\n🚀 Analizando mensaje: {Path(json_path).name}")

            try:
                # Leer el JSON del mensaje
                with open(json_path, 'r', encoding='utf-8') as f:
                    message_data = json.load(f)

                # Obtener el texto del mensaje para usarlo como contexto adicional
                texto = message_data.get('texto', '')
                imagenes = message_data.get('imagenes', [])
                
                # Decidir qué procesar: si hay imagen, solo procesar imagen (con texto como contexto)
                if imagenes:
                    # Si hay imágenes, el texto se usará como contexto adicional
                    # No procesamos el texto por separado para evitar duplicados
                    pass
                elif texto:
                    # Solo procesar texto si NO hay imágenes
                    print(f"📝 Procesando texto del mensaje...")
                    text_result = self._process_text(texto, message_data)
                    self.processor.results.append(text_result)
                    print(f"✅ Texto analizado")

                # Procesar imágenes asociadas si existen
                if imagenes:
                    print(f"🖼️  Mensaje tiene {len(imagenes)} imagen(es)")
                    for img_info in imagenes:
                        img_path = Path(self.images_folder) / img_info['nombreArchivo']
                        if img_path.exists():
                            print(f"   📸 Procesando: {img_info['nombreArchivo']}")
                            
                            # 🔥 CAMBIO CRÍTICO: Pasar el texto como contexto adicional
                            if texto:
                                print(f"   📝 Incluyendo texto del mensaje como contexto")
                            else:
                                print(f"   ⚠️  No hay texto adicional")
                            
                            img_result = self._process_image(
                                str(img_path), 
                                message_data,
                                additional_text=texto  # ✅ AHORA PASA EL TEXTO
                            )
                            self.processor.results.append(img_result)
                            print(f"   ✅ Imagen analizada")
                        else:
                            print(f"   ⚠️ Imagen no encontrada: {img_path}")

                # Marcar como procesado
                self.file_queue.task_done()
                print(f"✅ Mensaje completamente procesado")
                print(f"📊 Cola restante: {self.file_queue.qsize()} mensajes\n")

            except Exception as e:
                print(f"❌ Error procesando mensaje: {e}")
                self.file_queue.task_done()

        print("🛑 Worker detenido.")

    def _process_text(self, texto: str, metadata: dict):
        """Procesa el texto del mensaje usando BatchMultiFormatProcessor."""
        file_info = {
            'path': metadata.get('id', 'texto'),
            'name': f"{metadata.get('contacto', 'Desconocido')}_texto",
            'type': 'text',
            'metadata': {
                'contacto': metadata.get('contacto'),
                'numero': metadata.get('numero'),
                'fecha': metadata.get('fechaLegible'),
                'es_propio': metadata.get('esPropio', False)
            }
        }
        
        # Usar el método de procesamiento de texto del processor
        return self.processor._process_text_content(texto, file_info)

    def _process_image(self, image_path: str, metadata: dict, additional_text: str = None):
        """
        Procesa una imagen usando BatchMultiFormatProcessor.
        
        Args:
            image_path: Ruta de la imagen a procesar
            metadata: Metadatos del mensaje de WhatsApp
            additional_text: Texto del mensaje para usar como contexto (NUEVO)
        """
        file_info = {
            'path': image_path,
            'name': Path(image_path).name,
            'type': 'image',
            'metadata': {
                'contacto': metadata.get('contacto'),
                'numero': metadata.get('numero'),
                'fecha': metadata.get('fechaLegible'),
                'es_propio': metadata.get('esPropio', False)
            },
            # ✅ AGREGAMOS EL TEXTO ADICIONAL AL file_info
            'texto_adicional': additional_text  # Clave correcta que espera batch_image_processor
        }
        
        # Usar el método de procesamiento de imágenes del processor
        return self.processor._process_single_file(file_info)


def iniciar_servidor(messages_folder: str = DEFAULT_MESSAGES_FOLDER,
                     images_folder: str = DEFAULT_IMAGES_FOLDER):
    """
    Punto de entrada para iniciar el servidor en tiempo real.
    
    Args:
        messages_folder: Carpeta donde se guardan los JSONs de mensajes
        images_folder: Carpeta donde se guardan las imágenes
    """
    processor = RealTimeProcessor(messages_folder, images_folder)
    processor.start()


if __name__ == "__main__":
    iniciar_servidor()
