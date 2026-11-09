"""Catálogo de becas (dataset de KipuBecas) y búsqueda de las fichas relevantes.

Lee los archivos .json de `documentos/` (por ejemplo becas_maestria_v4.json), arma
una ficha de texto por beca y, para cada consulta, devuelve:
  - un ÍNDICE con una línea por beca (para saber qué becas existen y cuáles no), y
  - las FICHAS DETALLADAS de las becas más relacionadas (búsqueda BM25).

Los días hábiles al cierre se calculan aquí, en código (lunes a viernes sin
feriados nacionales del Perú), para que el modelo no tenga que calcularlos.
"""

import json
import math
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from functools import lru_cache

from . import config

CARPETA_DOCUMENTOS = config.RAIZ / "documentos"
FUENTE = "KipuBecas (kipubecas.com) y sitio oficial de cada beca"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Feriados nacionales del Perú (fijos) y Semana Santa por año.
FERIADOS_FIJOS = [(1, 1), (5, 1), (6, 7), (6, 29), (7, 23), (7, 28), (7, 29), (8, 6),
                  (8, 30), (10, 8), (11, 1), (12, 8), (12, 9), (12, 25)]
SEMANA_SANTA = {2026: [(4, 2), (4, 3)], 2027: [(3, 25), (3, 26)], 2028: [(4, 13), (4, 14)]}


def es_feriado(d: date) -> bool:
    return (d.month, d.day) in FERIADOS_FIJOS or (d.month, d.day) in SEMANA_SANTA.get(d.year, [])


def dias_habiles(hasta: date, desde: date | None = None) -> int:
    """Días hábiles desde mañana hasta la fecha de cierre (incluida). 0 si ya pasó."""
    desde = desde or date.today()
    n, d = 0, desde + timedelta(days=1)
    while d <= hasta:
        if d.weekday() < 5 and not es_feriado(d):
            n += 1
        d += timedelta(days=1)
    return n


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


# ------------------------------------------------------------------ carga
def _lista(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v).strip()


def _corta(texto: str, n: int) -> str:
    texto = re.sub(r"\s*\n\s*", " · ", (texto or "").strip())
    return texto if len(texto) <= n else texto[:n].rsplit(" ", 1)[0] + "…"


@lru_cache(maxsize=1)
def cargar() -> tuple[list[dict], str]:
    """Devuelve (becas, fecha_de_consulta). Cada beca trae su ficha y su línea de índice."""
    becas, fechas = [], []
    for ruta in sorted(CARPETA_DOCUMENTOS.glob("*.json")):
        fechas.append(datetime.fromtimestamp(ruta.stat().st_mtime).date())
        for i, b in enumerate(json.loads(ruta.read_text(encoding="utf-8")), 1):
            becas.append(_preparar(b))
    for n, b in enumerate(becas, 1):
        b["n"] = n
    consulta = max(fechas).isoformat() if fechas else "sin fecha"
    return becas, consulta


def _preparar(b: dict) -> dict:
    iso = b.get("fecha_limite_iso")
    cierre = date.fromisoformat(iso) if iso else None
    return {"raw": b, "titulo": b.get("titulo", "").strip(), "organizacion": b.get("organizacion", "").strip(),
            "cierre": cierre, "proyectada": bool(b.get("fecha_proyectada")),
            "url_oficial": b.get("url_oficial") or "", "url_kipu": b.get("url_detalle") or "",
            "completa": "detalle_texto" in b}


def _nacionalidades(b: dict) -> str:
    nac = b.get("nacionalidades_elegibles")
    if not nac:
        return "no especificadas en la ficha"
    items = nac if isinstance(nac, list) else [x.strip() for x in str(nac).split(",")]
    if len(items) > 15:
        incluye = any(x.strip().lower() in ("perú", "peru") for x in items)
        return f"lista de {len(items)} países; {'incluye' if incluye else 'NO incluye'} Perú"
    return ", ".join(items)


def ficha(beca: dict, hoy: date | None = None) -> str:
    """Texto de la ficha detallada que se envía al modelo."""
    b, hoy = beca["raw"], hoy or date.today()
    lineas = [f"[Beca {beca['n']}] {beca['titulo']} — {beca['organizacion']}"]
    if beca["url_oficial"]:
        lineas.append(f"URL oficial: {beca['url_oficial']}")
    if beca["url_kipu"]:
        lineas.append(f"Ficha KipuBecas: {beca['url_kipu']}")
    lineas.append(f"Estado en KipuBecas: {b.get('estado', 'sin dato')}")
    if beca["cierre"]:
        c = beca["cierre"]
        nota = " — FECHA PROYECTADA, aún no confirmada" if beca["proyectada"] else ""
        lineas.append(f"Fecha límite: {fecha_larga(c)} ({c.isoformat()}, {DIAS[c.weekday()]}){nota}")
        dh = dias_habiles(c, hoy)
        lineas.append(f"Días hábiles hasta el cierre (calculado desde hoy, feriados de Perú): "
                      f"{dh}" if c > hoy else "Días hábiles hasta el cierre: 0 (la fecha ya pasó)")
    else:
        lineas.append(f"Fecha límite: {b.get('fecha_limite_tarjeta', 'sin dato')} (sin detalle verificado)")
    if not beca["completa"]:
        lineas.append(f"Descripción: {b.get('descripcion_corta', '')}")
        lineas.append("AVISO: ficha incompleta; no hay requisitos detallados de esta beca.")
        return "\n".join(lineas)
    campos = [
        ("Nivel de estudio", _lista(b.get("nivel_de_estudio"))),
        ("Tipo de beca", _lista(b.get("tipo_de_beca"))),
        ("País de destino", _lista(b.get("pais_de_destino"))),
        ("Área de estudio", _lista(b.get("area_de_estudio"))),
        ("Financiamiento", _corta(_lista(b.get("financiamiento")), 400)),
        ("Cobertura", _lista(b.get("cobertura_beneficios"))),
        ("Idioma requerido", _lista(b.get("idioma_requerido"))),
        ("Experiencia laboral", _lista(b.get("experiencia_laboral"))),
        ("Rango de edad", _lista(b.get("rango_de_edad"))),
        ("Nacionalidades elegibles", _nacionalidades(b)),
        ("Duración", _corta(_lista(b.get("duracion")), 200)),
        ("Requisitos", _corta(_lista(b.get("requisitos_principales") or b.get("requisitos")), 1100)),
        ("Beneficios", _corta(_lista(b.get("beneficios")), 500)),
        ("Documentos requeridos", _corta(_lista(b.get("documentos_requeridos")), 450)),
        ("Importante", _corta(_lista(b.get("importante")), 450)),
    ]
    lineas += [f"{k}: {v}" for k, v in campos if v]
    return "\n".join(lineas)


def linea_indice(beca: dict) -> str:
    b = beca["raw"]
    cierre = (beca["cierre"].isoformat() + (" (proyectada)" if beca["proyectada"] else "")) if beca["cierre"] \
        else b.get("fecha_limite_tarjeta", "sin dato")
    nivel = _lista(b.get("nivel_de_estudio")) or "sin dato"
    pais = _lista(b.get("pais_de_destino")) or "sin dato"
    return f"[Beca {beca['n']}] {beca['titulo']} · {beca['organizacion']} · Nivel: {nivel} · País: {pais} · Cierre: {cierre}"


# ------------------------------------------------------------------ búsqueda BM25
VACIAS = set("""de la el los las un una unos unas y o a en por para con sin que se su sus mi mis me te le lo al del es
son soy tengo tiene quiero puedo como cual cuales cuando cuanto cuantos donde hay esta este esto esa ese
beca becas maestria maestrias programa programas postular sobre si no mas muy ya tu yo""".split())


def _tokens(texto: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 1 and w not in VACIAS]


@lru_cache(maxsize=1)
def _indice_bm25():
    becas, _ = cargar()
    docs = []
    for b in becas:
        nombre = f"{b['titulo']} {b['organizacion']} "
        docs.append(_tokens(nombre * 3 + ficha(b)))
    df = Counter(w for d in docs for w in set(d))
    prom = sum(len(d) for d in docs) / max(len(docs), 1)
    return docs, df, prom


def buscar(consulta: str, k: int = 3) -> list[dict]:
    """Las k becas más relacionadas con la consulta (solo las que tienen coincidencias)."""
    becas, _ = cargar()
    docs, df, prom = _indice_bm25()
    q = _tokens(consulta)
    if not q:
        return []
    n, k1, b_ = len(docs), 1.5, 0.75
    puntajes = []
    for beca, d in zip(becas, docs):
        tf = Counter(d)
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b_ + b_ * len(d) / prom))
        puntajes.append((s, beca))
    puntajes.sort(key=lambda x: -x[0])
    return [b for s, b in puntajes[:k] if s > 0]


# ------------------------------------------------------------------ contexto para el modelo
def bloque_contexto(consulta: str, hoy: date | None = None, k: int = 3) -> str:
    """Texto que se agrega al system: fecha de hoy, índice del catálogo y fichas relevantes."""
    hoy = hoy or date.today()
    becas, consultado = cargar()
    partes = [f"Fecha de hoy: {DIAS[hoy.weekday()]} {fecha_larga(hoy)} ({hoy.isoformat()})."]
    if not becas:
        partes.append("Documentos públicos oficiales proporcionados: ninguno por ahora. "
                      "Por lo tanto, no dispones de requisitos ni fechas de ninguna beca.")
        return "\n\n".join(partes)
    partes.append(
        f"Documentos públicos oficiales proporcionados: catálogo de {len(becas)} becas. Fuente: {FUENTE}; "
        f"fecha de consulta: {consultado}. Si una beca no aparece en este índice, no está en tus documentos."
    )
    partes.append("ÍNDICE DEL CATÁLOGO:\n" + "\n".join(linea_indice(b) for b in becas))
    relevantes = buscar(consulta, k)
    if relevantes:
        partes.append("FICHAS DETALLADAS DE LAS BECAS RELACIONADAS CON LA CONSULTA:\n\n"
                      + "\n\n".join(ficha(b, hoy) for b in relevantes))
    return "\n\n".join(partes)


def buscar_por_titulo(fragmento: str) -> dict | None:
    becas, _ = cargar()
    f = fragmento.lower()
    return next((b for b in becas if f in b["titulo"].lower()), None)
