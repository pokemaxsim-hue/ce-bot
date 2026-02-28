"""
Procesamiento histórico de mensajes WhatsApp.
Permite elegir un grupo/canal y una fecha (hoy, ayer o específica) para
procesar todos los mensajes de esa jornada en cola, mostrando progreso.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Tuple

from batch_image_processor import BatchMultiFormatProcessor


class HistoricalMessageProcessor:
    """Procesa mensajes históricos reutilizando el mismo pipeline del watcher."""

    def __init__(
        self,
        messages_folder: str = "anuncios_empleo/mensajes",
        images_folder: str = "anuncios_empleo/imagenes",
    ):
        self.messages_folder = Path(messages_folder)
        self.images_folder = Path(images_folder)
        self.processor = BatchMultiFormatProcessor()

    # ------------------------------------------------------------------ #
    # Selección de fuente y fecha
    # ------------------------------------------------------------------ #
    def _extract_chat_id(self, raw_id: str | None) -> str:
        if not raw_id:
            return "unknown"
        parts = raw_id.split("_", 2)
        if len(parts) >= 2:
            return parts[1]
        return raw_id

    def _classify_chat(self, chat_id: str) -> str:
        if "@g.us" in chat_id:
            return "Grupo"
        if "@newsletter" in chat_id:
            return "Canal"
        if "@s.whatsapp.net" in chat_id:
            return "Contacto"
        return "Desconocido"

    def list_sources(self) -> Dict[str, Dict[str, Any]]:
        """Agrupa los JSON por chat/canal usando su ID real."""
        sources: Dict[str, Dict[str, Any]] = {}
        for json_path in sorted(self.messages_folder.glob("*.json")):
            try:
                with json_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            chat_id = self._extract_chat_id(data.get("id"))
            meta = sources.setdefault(
                chat_id,
                {
                    "messages": [],
                    "contacts": set(),
                    "type": self._classify_chat(chat_id),
                },
            )
            meta["messages"].append({"path": json_path, "payload": data})
            contact = (data.get("contacto") or "").strip()
            if contact:
                meta["contacts"].add(contact)
        return sources

    def _parse_message_date(self, payload: Dict) -> date | None:
        """Convierte los campos fecha/fechaLegible a date."""
        raw_iso = payload.get("fecha")
        if isinstance(raw_iso, str) and raw_iso.strip():
            try:
                normalized = raw_iso.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).date()
            except Exception:
                pass
        raw_human = payload.get("fechaLegible")
        if isinstance(raw_human, str):
            for fmt in ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    return datetime.strptime(raw_human, fmt).date()
                except Exception:
                    continue
        return None

    def filter_messages(
        self, messages: List[Dict[str, Any]], target_date: date
    ) -> List[Tuple[Path, Dict]]:
        """Devuelve pares (path, data) cuyo día coincide con target_date."""
        filtered: List[Tuple[Path, Dict]] = []
        for entry in messages:
            json_path = entry["path"]
            data = entry["payload"]
            msg_date = self._parse_message_date(data)
            if msg_date == target_date:
                filtered.append((json_path, data))
        return filtered

    # ------------------------------------------------------------------ #
    # Procesamiento individual reutilizando la lógica del watcher
    # ------------------------------------------------------------------ #
    def _process_text(self, texto: str, metadata: Dict) -> Dict:
        file_info = {
            "path": metadata.get("id", "texto"),
            "name": f"{metadata.get('contacto', 'Desconocido')}_texto",
            "type": "text",
            "metadata": {
                "contacto": metadata.get("contacto"),
                "numero": metadata.get("numero"),
                "fecha": metadata.get("fechaLegible"),
                "es_propio": metadata.get("esPropio", False),
            },
        }
        return self.processor._process_text_content(texto, file_info)

    def _process_image(
        self, image_path: Path, metadata: Dict, additional_text: str | None = None
    ) -> Dict:
        file_info = {
            "path": str(image_path),
            "name": image_path.name,
            "type": "image",
            "metadata": {
                "contacto": metadata.get("contacto"),
                "numero": metadata.get("numero"),
                "fecha": metadata.get("fechaLegible"),
                "es_propio": metadata.get("esPropio", False),
            },
            "texto_adicional": additional_text,
        }
        return self.processor._process_single_file(file_info)

    def _process_single_message(self, json_path: Path, payload: Dict) -> bool:
        """Procesa un mensaje; devuelve True si no falló."""
        success = True
        texto = payload.get("texto", "") or ""
        imagenes = payload.get("imagenes") or []

        print(f"    Texto presente: {'sí' if texto else 'no'} | Imágenes: {len(imagenes)}")

        try:
            if not imagenes and texto.strip():
                print("    -> Procesando texto del mensaje…")
                result = self._process_text(texto, payload)
                self.processor.results.append(result)
        except Exception as err:
            success = False
            print(f"    [ERROR] Falló el texto: {err}")

        if imagenes:
            for img_info in imagenes:
                nombre = img_info.get("nombreArchivo")
                if not nombre:
                    continue
                img_path = self.images_folder / nombre
                if not img_path.exists():
                    print(f"    [WARN] Imagen no encontrada: {img_path}")
                    success = False
                    continue
                print(f"    -> Procesando imagen {nombre}…")
                try:
                    result = self._process_image(img_path, payload, additional_text=texto)
                    self.processor.results.append(result)
                except Exception as err:
                    success = False
                    print(f"       [ERROR] Imagen fallida: {err}")
        return success

    # ------------------------------------------------------------------ #
    # Ejecución principal
    # ------------------------------------------------------------------ #
    def run(self):
        if not self.messages_folder.exists():
            print(f"❌ Carpeta no encontrada: {self.messages_folder}")
            return

        sources = self.list_sources()
        if not sources:
            print("⚠️ No se encontraron mensajes para procesar.")
            return

        selected_chat = self._prompt_source(sources)
        if not selected_chat:
            print("⚠️ Operación cancelada.")
            return

        target_date = self._prompt_date()
        if not target_date:
            print("⚠️ Fecha inválida. Cancelado.")
            return

        candidates = self.filter_messages(sources[selected_chat]["messages"], target_date)
        if not candidates:
            print(
                f"⚠️ No hay mensajes del chat {selected_chat} para {target_date.isoformat()}."
            )
            return

        total = len(candidates)
        print(
            f"\n[INFO] Preparando procesamiento para '{selected_chat}' en {target_date:%d/%m/%Y}"
        )
        print(f"   Total a analizar: {total}")

        processed = 0
        successes = 0
        for idx, (json_path, payload) in enumerate(sorted(candidates), start=1):
            print(f"\n[{idx}/{total}] Procesando {json_path.name}")
            if self._process_single_message(json_path, payload):
                successes += 1
            processed += 1
            print(f"   Restantes: {total - processed}")

        print(
            f"\n[RESUMEN] Se procesaron correctamente {successes} de {total} mensajes seleccionados."
        )

    # ------------------------------------------------------------------ #
    # Helpers de UI
    # ------------------------------------------------------------------ #
    def _format_source_label(self, chat_id: str, meta: Dict[str, Any]) -> str:
        contacts_list = sorted(meta["contacts"])
        if len(contacts_list) > 3:
            contacts = ", ".join(contacts_list[:3]) + ", ..."
        elif contacts_list:
            contacts = ", ".join(contacts_list)
        else:
            contacts = "sin remitentes registrados"
        return (
            f"{meta['type']} | {chat_id} "
            f"(mensajes: {len(meta['messages'])}, últimos remitentes: {contacts})"
        )

    def _prompt_source(self, sources: Dict[str, Dict[str, Any]]) -> str | None:
        entries = sorted(
            [(chat_id, self._format_source_label(chat_id, meta)) for chat_id, meta in sources.items()],
            key=lambda item: item[1].lower(),
        )

        print("\n[MENU] Selecciona el grupo/canal a analizar:")
        for idx, (_, label) in enumerate(entries, start=1):
            print(f"  {idx}. {label}")

        total = len(entries)

        def find_matches(token: str) -> List[int]:
            token_lower = token.lower()
            return [
                idx
                for idx, (chat_id, label) in enumerate(entries)
                if token_lower in chat_id.lower() or token_lower in label.lower()
            ]

        while True:
            choice = input("Ingresa número o texto (enter para cancelar): ").strip()
            if not choice:
                return None
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= total:
                    return entries[idx - 1][0]
            matches = find_matches(choice)
            if len(matches) == 1:
                return entries[matches[0]][0]
            if len(matches) > 1:
                print("Coincidencias encontradas:")
                for mi in matches[:5]:
                    print(f"  - {entries[mi][1]}")
                if len(matches) > 5:
                    print("  (más coincidencias... refina tu búsqueda)")
            else:
                print("❌ No se encontró coincidencia. Intenta de nuevo.")

    def _prompt_date(self) -> date | None:
        print("\n[MENU] Selecciona la fecha a analizar:")
        print("  1) Hoy")
        print("  2) Ayer")
        print("  3) Ingresar fecha (dd--mm--yy)")

        choice = input("Opción: ").strip()
        today = datetime.now().date()
        if choice == "1":
            return today
        if choice == "2":
            return today - timedelta(days=1)
        if choice == "3":
            raw = input("Fecha (dd--mm--yy): ").strip()
            normalized = raw.replace("--", "-")
            try:
                return datetime.strptime(normalized, "%d-%m-%y").date()
            except ValueError:
                print("❌ Formato inválido. Usa dd--mm--yy (ej: 10--11--25).")
                return None
        print("❌ Opción inválida.")
        return None


if __name__ == "__main__":
    HistoricalMessageProcessor().run()
