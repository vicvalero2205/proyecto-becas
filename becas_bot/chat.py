"""Núcleo del chat con historial: arma cada llamada y registra trazas."""

import json
from datetime import datetime

from . import catalogo, config, llm
from .especificacion import INSTRUCCIONES, VERSION


def _texto(contenido) -> str:
    """Gradio 6 puede guardar el contenido como texto o como lista de partes."""
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return " ".join(p.get("text", "") for p in contenido if isinstance(p, dict))
    if isinstance(contenido, dict):
        return contenido.get("text", "")
    return ""


def limpiar_historial(historial) -> list[dict]:
    """Deja solo turnos user/assistant con texto, recortados y limitados."""
    hist = []
    for m in historial or []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            t = _texto(m.get("content"))
            if t:
                hist.append({"role": m["role"], "content": t[: config.MAX_CARACTERES * 2]})
    return hist[-2 * config.MAX_TURNOS_HISTORIAL :]


def consulta_busqueda(mensaje: str, historial: list[dict]) -> str:
    """Texto con el que se buscan las becas: el mensaje nuevo y los dos últimos del usuario.

    Así una pregunta de seguimiento ("¿y cuándo cierra?") sigue encontrando la beca
    que se mencionó en un turno anterior.
    """
    previos = [m["content"] for m in historial if m["role"] == "user"][-2:]
    return " ".join(previos + [mensaje])


def armar_mensajes(mensaje: str, historial: list[dict]) -> list[dict]:
    """La llamada lleva TODO: instrucciones (+ fecha y catálogo), historial y mensaje nuevo."""
    hist = limpiar_historial(historial)
    system = INSTRUCCIONES + "\n\n" + catalogo.bloque_contexto(consulta_busqueda(mensaje, hist))
    return (
        [{"role": "system", "content": system}]
        + hist
        + [{"role": "user", "content": mensaje}]
    )


def responder(mensaje: str, historial: list[dict]) -> dict:
    return llm.llamar(armar_mensajes(mensaje, historial))


class Trazas:
    """Registro JSONL de cada turno (equivalente al LOG del Lab 2, pero local)."""

    def __init__(self, nombre: str = "trazas_chat.jsonl"):
        config.CARPETA_TRAZAS.mkdir(parents=True, exist_ok=True)
        self.ruta = config.CARPETA_TRAZAS / nombre

    def registrar(self, tipo: str, **datos) -> None:
        fila = {"ts": datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
                "prompt_version": VERSION, **datos}
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")

    def leer(self, tipo: str | None = None) -> list[dict]:
        if not self.ruta.exists():
            return []
        filas = [json.loads(l) for l in self.ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [f for f in filas if tipo is None or f.get("tipo") == tipo]
