"""PASO 1 · Chat con historial implementado en Gradio.

Uso (desde la carpeta del proyecto):
    .venv/bin/python paso1_chat_gradio.py            # solo en tu compu: http://127.0.0.1:7860
    .venv/bin/python paso1_chat_gradio.py --share    # enlace público temporal con usuario y código

Cada turno queda registrado en trazas/trazas_chat.jsonl.
"""

import argparse
import random

import gradio as gr

from becas_bot import config, llm
from becas_bot.chat import Trazas, limpiar_historial, responder
from becas_bot.especificacion import VERSION

AVISO = (
    "Asistente de prueba de un curso (UNI · Tópicos de IA Generativa). Responde con un catálogo de 40 becas "
    "de KipuBecas; muchas fechas son proyectadas: confírmalas siempre en la página oficial de cada beca. "
    "No escribas datos personales reales: lo que escribas queda registrado."
)
EJEMPLOS = [
    "Tengo 27 años, soy economista, quinto superior y tengo francés B2. ¿Puedo postular a la France Excellence Eiffel?",
    "¿Cuántos días hábiles faltan para el cierre de la Gates Cambridge Scholarship?",
    "¿Qué becas de maestría en Francia hay en el catálogo?",
]

LOG = Trazas()


def chat(mensaje, historial, request: gr.Request):
    sesion = getattr(request, "session_hash", None) or "sin_sesion"
    if not isinstance(mensaje, str) or not mensaje.strip():
        return "Escribe tu consulta sobre becas de maestría."
    if len(mensaje) > config.MAX_CARACTERES:
        return f"Escribe un mensaje de hasta {config.MAX_CARACTERES} caracteres."
    hist = limpiar_historial(historial)
    try:
        r = responder(mensaje, hist)
    except llm.ErrorModelo as e:
        print("🔴", e)
        return "El asistente no pudo responder ahora. Revisa que Ollama esté encendido y vuelve a intentar."
    LOG.registrar(
        "turno", session_id=sesion, turno=len(hist) // 2 + 1, mensaje=mensaje,
        respuesta=r["respuesta"], historial_turnos=len(hist) // 2, modelo=r["modelo"],
        input_tokens=r["input_tokens"], output_tokens=r["output_tokens"], latencia_ms=r["latencia_ms"],
    )
    return r["respuesta"]


demo = gr.ChatInterface(
    chat,
    title=f"Asistente de elegibilidad y calendario de becas de maestría ({VERSION})",
    description=AVISO,
    examples=EJEMPLOS,
    cache_examples=False,
)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--share", action="store_true", help="crea un enlace público temporal con código")
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args()

    print(f"Modelo: {config.MODELO} · servidor: {config.BASE_URL}")
    print(f"Trazas: {LOG.ruta}")
    opciones = {}
    if args.share:
        codigo = f"{random.SystemRandom().randint(0, 999999):06d}"
        opciones = dict(share=True, auth=("becas", codigo),
                        auth_message="Asistente de prueba de un curso. Pide el código al dueño.")
        print(f"Usuario: becas · Código: {codigo}  (compártelo solo con tu grupo)")
    demo.queue(default_concurrency_limit=2).launch(server_port=args.port, **opciones)
