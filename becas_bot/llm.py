"""Llamada al modelo (local con Ollama o cualquier API compatible con OpenAI)."""

import time

from openai import OpenAI

from . import config


class ErrorModelo(Exception):
    pass


_cliente = OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY)


def llamar(mensajes: list[dict], temperatura: float | None = None) -> dict:
    """Envía la lista de mensajes (system + historial + nuevo) y devuelve la respuesta.

    Devuelve un dict con la misma forma que usa el curso:
    respuesta, modelo, input_tokens, output_tokens, latencia_ms.
    """
    t0 = time.perf_counter()
    try:
        r = _cliente.chat.completions.create(
            model=config.MODELO,
            messages=mensajes,
            temperature=config.TEMPERATURA if temperatura is None else temperatura,
        )
    except Exception as e:  # conexión caída, modelo no descargado, cuota, etc.
        raise ErrorModelo(
            f"No se pudo llamar al modelo '{config.MODELO}' en {config.BASE_URL}: {e}\n"
            "¿Está corriendo Ollama (`brew services start ollama`) y descargaste el modelo "
            f"(`ollama pull {config.MODELO}`)?"
        ) from e
    uso = r.usage
    return {
        "respuesta": (r.choices[0].message.content or "").strip(),
        "modelo": r.model or config.MODELO,
        "input_tokens": getattr(uso, "prompt_tokens", None),
        "output_tokens": getattr(uso, "completion_tokens", None),
        "latencia_ms": round((time.perf_counter() - t0) * 1000),
    }
