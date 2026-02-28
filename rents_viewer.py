"""
Script para obtener alquileres de Firestore, analizarlos con IA Ollama Qwen,
y actualizar el campo 'approved' si cumplen condiciones.
Mantiene un registro JSON de alquileres analizados.
"""

import sys
import os

# UTF-8 para Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from components.firebase_manager import FirebaseManager
from components.ollama_analyzer import OllamaLocalAnalyzer
import json
from typing import List, Dict, Any
from datetime import datetime
import requests
from io import BytesIO

class RentalsAIAnalyzer:
    """Analizador de alquileres con IA y actualización automática."""
    
    def __init__(self, 
                 registry_file: str = "rentals_analyzed.json",
                 min_approval_score: float = 0.7):
        """
        Inicializa el analizador.
        
        Args:
            registry_file: Archivo JSON donde guardar registros de análisis
            min_approval_score: Puntuación mínima para aprobar (0-1)
        """
        self.fb_manager = FirebaseManager()
        self.analyzer = OllamaLocalAnalyzer(
            api_url="http://localhost:11434/api/generate",
            model="qwen3-vl:235b-cloud",
            timeout=120
        )
        self.registry_file = registry_file
        self.min_approval_score = min_approval_score
        self.analyzed_registry = self._load_registry()
        
        print(f"✅ RentalsAIAnalyzer inicializado")
        print(f"   Registry: {registry_file}")
        print(f"   Puntuación mínima: {min_approval_score}")
    
    def _load_registry(self) -> Dict[str, Any]:
        """Carga el registro de análisis previos."""
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"analyzed": [], "approved": [], "rejected": []}
        return {"analyzed": [], "approved": [], "rejected": []}
    
    def _save_registry(self):
        """Guarda el registro de análisis."""
        with open(self.registry_file, 'w', encoding='utf-8') as f:
            json.dump(self.analyzed_registry, f, indent=2, ensure_ascii=False)
        print(f"💾 Registro guardado: {self.registry_file}")
    
    def _is_already_analyzed(self, rental_id: str) -> bool:
        """Verifica si un alquiler ya fue analizado."""
        analyzed_ids = [r['id'] for r in self.analyzed_registry.get('analyzed', [])]
        return rental_id in analyzed_ids
    
    def _download_image(self, url: str) -> BytesIO:
        """Descarga una imagen desde URL."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return BytesIO(response.content)
        except Exception as e:
            print(f"   ⚠️  Error descargando imagen: {str(e)}")
            return None
    
    def _calculate_approval_score(self, analysis: Dict) -> tuple[float, str]:
        """
        Calcula una puntuación de aprobación basada en el análisis.
        
        Returns:
            (score: float, reason: str)
        """
        score = 1.0
        reasons = []
        
        # Verificar campos obligatorios
        required_fields = ['title', 'description', 'city', 'price']
        for field in required_fields:
            if not analysis.get(field) or analysis.get(field) == "":
                score -= 0.15
                reasons.append(f"Falta: {field}")
        
        # Verificar calidad de descripción
        description = analysis.get('description', '')
        if len(description) < 30:
            score -= 0.2
            reasons.append("Descripción muy corta")
        
        # Verificar ubicación
        if not analysis.get('city'):
            score -= 0.15
            reasons.append("Sin ciudad especificada")
        
        # Verificar contacto
        has_contact = bool(analysis.get('phoneNumber') or analysis.get('email') or analysis.get('website'))
        if not has_contact:
            score -= 0.2
            reasons.append("Sin información de contacto")
        
        # Bonificación por información completa
        if analysis.get('direction'):
            score += 0.1
        if analysis.get('email') and analysis.get('phoneNumber'):
            score += 0.1
        
        # Asegurar rango 0-1
        score = max(0, min(1, score))
        
        return score, " | ".join(reasons) if reasons else "Cumple requisitos"
    
    def analyze_rental(self, rental: Dict) -> Dict[str, Any]:
        """
        Analiza un alquiler usando IA.
        
        Args:
            rental: Diccionario del alquiler de Firestore
        
        Returns:
            Resultado del análisis
        """
        rental_id = rental.get('id', 'unknown')
        
        print(f"\n{'='*80}")
        print(f"Analizando alquiler: {rental_id}")
        print(f"{'='*80}")
        
        # Verificar si ya fue analizado
        if self._is_already_analyzed(rental_id):
            print(f"⚠️  Este alquiler ya fue analizado anteriormente")
            return None
        
        analysis_result = {
            "id": rental_id,
            "timestamp": datetime.now().isoformat(),
            "rental_data": {
                "title": rental.get('title'),
                "city": rental.get('city'),
                "price": rental.get('price'),
                "userId": rental.get('userId')
            },
            "ai_analysis": {},
            "approval_score": 0,
            "approval_reason": "",
            "approved": False,
            "images_analyzed": 0,
            "images_errors": 0
        }
        
        # Analizar imágenes
        images = rental.get('images', [])
        if images:
            print(f"📷 Encontradas {len(images)} imagen(es)")
            
            for img_idx, img_url in enumerate(images, 1):
                try:
                    print(f"   Analizando imagen {img_idx}/{len(images)}...")
                    
                    # Descargar imagen
                    img_data = self._download_image(img_url)
                    if not img_data:
                        analysis_result['images_errors'] += 1
                        continue
                    
                    # Análisis de imagen
                    additional_text = f"""
                    Título: {rental.get('title', '')}
                    Ciudad: {rental.get('city', '')}
                    Descripción: {rental.get('description', '')}
                    """
                    
                    img_analysis = self.analyzer.analyze_job_image(
                        img_data,
                        additional_text=additional_text
                    )
                    
                    analysis_result['ai_analysis'][f'image_{img_idx}'] = img_analysis
                    analysis_result['images_analyzed'] += 1
                    print(f"   ✅ Imagen {img_idx} analizada")
                    
                except Exception as e:
                    print(f"   ❌ Error analizando imagen {img_idx}: {str(e)}")
                    analysis_result['images_errors'] += 1
        
        # Análisis de texto
        try:
            print(f"📝 Analizando datos de texto...")
            text_content = f"""
            Título: {rental.get('title', '')}
            Descripción: {rental.get('description', '')}
            Ciudad: {rental.get('city', '')}
            Precio: {rental.get('price', '')}
            Dirección: {rental.get('direction', '')}
            Teléfono: {rental.get('phoneNumber', '')}
            Email: {rental.get('email', '')}
            """
            
            text_analysis = self.analyzer.analyze_job_text(text_content)
            analysis_result['ai_analysis']['text_analysis'] = text_analysis
            print(f"✅ Análisis de texto completado")
        except Exception as e:
            print(f"❌ Error en análisis de texto: {str(e)}")
        
        # Calcular puntuación
        score, reason = self._calculate_approval_score(
            analysis_result['ai_analysis'].get('text_analysis', {})
        )
        analysis_result['approval_score'] = score
        analysis_result['approval_reason'] = reason
        
        # Determinar aprobación
        if score >= self.min_approval_score:
            analysis_result['approved'] = True
            print(f"\n✅ APROBADO (Score: {score:.2f})")
        else:
            analysis_result['approved'] = False
            print(f"\n❌ RECHAZADO (Score: {score:.2f})")
        
        print(f"Razón: {reason}")
        
        return analysis_result
    
    def update_firestore_approval(self, rental_id: str, approved: bool) -> bool:
        """
        Actualiza el campo 'approved' en Firestore.
        
        Args:
            rental_id: ID del alquiler
            approved: Valor de aprobación
        
        Returns:
            True si se actualizó exitosamente
        """
        try:
            success = self.fb_manager.update_firestore_document(
                doc_id=rental_id,
                data={"approved": approved},
                collection="rents",
                merge=True
            )
            if success:
                print(f"✅ Firestore actualizado: approved = {approved}")
            return success
        except Exception as e:
            print(f"❌ Error actualizando Firestore: {str(e)}")
            return False
    
    def process_all_rentals(self, skip_approved: bool = True):
        """
        Procesa todos los alquileres pendientes.
        
        Args:
            skip_approved: Si True, salta los ya aprobados
        """
        print(f"\n{'='*80}")
        print(f"INICIANDO ANÁLISIS DE ALQUILERES")
        print(f"{'='*80}\n")
        
        # Obtener todos los alquileres
        try:
            all_rentals = self.fb_manager.query_firestore(collection='rents')
        except Exception as e:
            print(f"❌ Error obteniendo alquileres: {str(e)}")
            return
        
        # Filtrar por tipo 'alquiler' (no 'empleo')
        rentals = [r for r in all_rentals if r.get('publicationType') == 'alquiler']
        
        if skip_approved:
            rentals = [r for r in rentals if r.get('approved') != True]
        
        print(f"📊 Total de alquileres a procesar: {len(rentals)}\n")
        
        approved_count = 0
        rejected_count = 0
        
        for idx, rental in enumerate(rentals, 1):
            print(f"\n[{idx}/{len(rentals)}]")
            
            # Analizar
            result = self.analyze_rental(rental)
            if not result:
                continue
            
            # Guardar en registro
            self.analyzed_registry['analyzed'].append(result)
            
            # Actualizar Firestore si fue aprobado
            if result['approved']:
                approved_count += 1
                self.analyzed_registry['approved'].append(result)
                
                # Actualizar en Firestore
                self.update_firestore_approval(rental.get('id'), True)
            else:
                rejected_count += 1
                self.analyzed_registry['rejected'].append(result)
            
            # Guardar registro después de cada análisis
            self._save_registry()
        
        # Resumen final
        print(f"\n{'='*80}")
        print(f"RESUMEN FINAL")
        print(f"{'='*80}")
        print(f"Total procesados:  {len(rentals)}")
        print(f"Aprobados:         {approved_count}")
        print(f"Rechazados:        {rejected_count}")
        print(f"Registro guardado: {self.registry_file}")
        print(f"{'='*80}\n")


# Uso
if __name__ == "__main__":
    # Inicializar analizador
    analyzer = RentalsAIAnalyzer(
        registry_file="rentals_analyzed.json",
        min_approval_score=0.7  # 70% mínimo para aprobar
    )
    
    # Procesar todos los alquileres
    analyzer.process_all_rentals(skip_approved=True)