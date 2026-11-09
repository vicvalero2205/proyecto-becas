"""Configuración del asistente de becas.

Por defecto usa un modelo LOCAL con Ollama (no requiere Google ni claves).
Ollama expone una API compatible con OpenAI en http://localhost:11434/v1,
así que el mismo código sirve para otro proveedor compatible (p. ej. Groq)
cambiando solo variables de entorno o el archivo `.env` en la raíz del proyecto.

Variables:
    BECAS_BASE_URL   URL del servidor (por defecto Ollama local)
    BECAS_API_KEY    clave (Ollama no la usa; cualquier texto sirve)
    BECAS_MODEL      nombre del modelo (por defecto becas-qwen2.5 = qwen2.5:7b con 16k de contexto)
    BECAS_TEMPERATURE  temperatura de muestreo (por defecto 0.2)
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path) -> None:
    """Lee un .env sencillo (CLAVE=valor) sin dependencias extra."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(RAIZ / ".env")

BASE_URL = os.getenv("BECAS_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.getenv("BECAS_API_KEY", "ollama")
MODELO = os.getenv("BECAS_MODEL", "becas-qwen2.5")  # qwen2.5:7b con contexto de 16k (ver Modelfile)
TEMPERATURA = float(os.getenv("BECAS_TEMPERATURE", "0.2"))

# Topes de la interfaz (igual que en el Lab 2)
MAX_CARACTERES = 1000      # por mensaje del usuario
MAX_TURNOS_HISTORIAL = 10  # turnos anteriores que viajan al modelo

CARPETA_TRAZAS = RAIZ / "trazas"
CARPETA_RESULTADOS = RAIZ / "evaluacion" / "resultados"
