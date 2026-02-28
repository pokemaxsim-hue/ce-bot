import requests
import json

# Configuración
# Si usas Ollama Cloud o un servidor remoto, cambia la URL y añade headers si es necesario.
MODELO = "llama3" 
URL = "http://localhost:11434/api/generate" # Cambia esto por tu URL (ej: https://tu-ollama-cloud.com/api/generate)
HEADERS = {
    # "Authorization": "Bearer TU_API_KEY", # Descomenta y pon tu clave si es necesario
    "Content-Type": "application/json"
}

def probar_ollama():
    payload = {
        "model": MODELO,
        "prompt": "Hola, responde brevemente: ¿Estás funcionando?",
        "stream": True
    }

    print(f"Conectando a Ollama ({URL}) con modelo '{MODELO}'...")
    
    try:
        with requests.post(URL, json=payload, headers=HEADERS, stream=True) as response:
            response.raise_for_status()
            
            print("Respuesta:")
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    data = json.loads(decoded_line)
                    
                    if "response" in data:
                        print(data["response"], end="", flush=True)
                    
                    if data.get("done", False):
                        print("\n\n[Fin de la respuesta]")
                        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: No se pudo conectar a Ollama. Asegúrate de que esté ejecutándose.")
    except Exception as e:
        print(f"\n❌ Ocurrió un error: {e}")

if __name__ == "__main__":
    probar_ollama()
