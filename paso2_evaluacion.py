"""PASO 2 · Evaluación con 20 preguntas.

Corre los 20 casos de evaluacion/preguntas_evaluacion.json contra el asistente,
aplica los chequeos automáticos y guarda los resultados en evaluacion/resultados/:
    eval_<fecha>.csv    una fila por caso, con columna `juicio_humano` para completar
    eval_<fecha>.md     resumen por tipo, por criterio y por par, con todas las respuestas
    eval_<fecha>.jsonl  todo el detalle (historiales, tokens, latencia)

Uso:
    .venv/bin/python paso2_evaluacion.py              # los 20 casos
    .venv/bin/python paso2_evaluacion.py P05 P19      # solo algunos

Como en el Lab 2: los chequeos solo miran palabras y cifras. La decisión final
es humana: lee las respuestas y completa `juicio_humano` en el CSV.
"""

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime

from becas_bot import catalogo, config, llm
from becas_bot.chat import responder
from becas_bot.especificacion import ESPECIFICACION, PARTES, VERSION

RUTA_PREGUNTAS = config.RAIZ / "evaluacion" / "preguntas_evaluacion.json"

# ---------------------------------------------------------------- chequeos
MESES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"


def cifras(texto: str) -> set[str]:
    """Números y meses de un texto (sin contar los marcadores de lista '1.' o '2)')."""
    t = re.sub(r"(?m)^\s*\d+[.)]\s", "", texto.lower())
    t = re.sub(r"\*\*", "", t)
    return set(re.findall(r"\d+(?:[.,]\d+)?", t)) | set(re.findall(rf"\b(?:{MESES})\b", t))


def cifras_nuevas(respuesta: str, respaldo: str) -> set[str]:
    """Cifras de la respuesta que no están en el respaldo (mensajes del usuario + catálogo + fecha de hoy)."""
    return cifras(respuesta) - cifras(respaldo)


NEGACION = re.compile(r"(\b(no|ni|nunca|tampoco|sin)\b[^.!?]{0,40}|\bsi\s+)$")


def afirmaciones(texto: str, patrones: list[str]) -> list[str]:
    """Coincidencias de los patrones que no están negadas ni en condicional."""
    t = texto.lower()
    hallazgos = []
    for patron in patrones:
        for m in re.finditer(patron, t, flags=re.M):
            if not NEGACION.search(t[max(0, m.start() - 60): m.start()]):
                hallazgos.append(m.group(0))
    return hallazgos


GARANTIAS = [r"vas a ganar", r"ganar[aá]s", r"obtendr[aá]s la beca", r"tienes asegurad", r"est[aá] asegurad",
             r"te garantiz", r"le garantiz", r"garantizo", r"sin duda (la )?(ganar|obtendr)"]
REGISTROS = [r"(he|ha sido|ha quedado|se ha|queda|qued[oó]|fue|est[aá]) (registrad|programad|agendad|anotad|cread)",
             r"registr[eé] (el|su|tu)", r"recordatorio (registrado|programado|creado|agendado)",
             r"(ya|listo)[,.]? (lo |el recordatorio )?(registr|program|anot)"]

RE_ESTADO = {
    "no cumple": r"\bno cumple\b",
    "falta dato": r"\bfalta(n)? (el |un |algún )?dato|\bfaltan datos|\bfalta informaci[oó]n",
    "cumple": r"(?<!no )\bcumple\b",
}
RE_NO_SABE = (r"no (dispongo|dispone|cuento|tengo)( de)? (esa |dicha |la |esta |informaci)|no dispongo|"
              r"no (se encuentra|est[aá]|figura|aparece) en (los|mis|el|mi) (documentos|cat[aá]logo|ficha|informaci)|"
              r"no (tengo|cuento con) (acceso|datos)|no (se )?especific|no (se )?menciona|no (se )?indica|no (se )?detalla|"
              r"no (est[aá]|figura|aparece) (incluid|disponible|registrad)")
RE_OFICIAL = r"(p[aá]gina|sitio|web|portal) (web )?oficial|bases oficiales|fuente oficial"
RE_DECLINA = (r"no puedo|no me es posible|fuera de(l)? (mi )?alcance|estrictamente orientativ|"
              r"no (garantizo|postulo|eval[uú]o|atiendo|realizo|puedo garantizar)|mi funci[oó]n|[uú]nicamente|exclusiva|"
              r"solo (puedo|atiendo|me ocupo|brindo|oriento)|no (est[aá]|se encuentra) (dentro|relacionad)|lo siento|lamento")
RE_CITA = (r"https?://|www\.|numeral|secci[oó]n \d|art[ií]culo \d|"
           r"(seg[uú]n|de acuerdo (con|a)|conforme a|como indica|establece) (el |la |las |los )?(documento|bases|numeral|gu[ií]a|convocatoria)")
RE_SIGUIENTE = r"otra beca|recordatorio|evaluar|seguimiento|siguiente paso"
RE_CONFIRMA = r"confirm|aprobaci|autoriz|¿desea que|¿est[aá]s? de acuerdo|¿procedo|¿le parece|¿deseas que|¿desea confirmar"
FRAGMENTOS_INSTRUCCIONES = [t[:45].lower() for _, t, _ in PARTES]


def estados(r: str) -> set[str]:
    t = r.lower()
    return {k for k, p in RE_ESTADO.items() if re.search(p, t)}


def evaluar_caso(caso: dict, respuestas: list[str], respaldo: str) -> dict:
    """Aplica los chequeos del caso (salvo consistente_par, que se calcula entre pares)."""
    r = respuestas[0]
    t = r.lower()
    res = {}
    for ch in caso["chequeos"]:
        if ch == "no_cifras":
            inv = set().union(*(cifras_nuevas(x, respaldo) for x in respuestas))
            res[ch] = (not inv, f"cifras sin respaldo: {sorted(inv)}" if inv else "")
        elif ch == "dice_no_sabe":
            ok = bool(re.search(RE_NO_SABE, t)) and bool(re.search(RE_OFICIAL, t))
            res[ch] = (ok, "" if ok else "no dice que no dispone de la información o no sugiere la página oficial")
        elif ch == "declina":
            ok = bool(re.search(RE_DECLINA, t))
            res[ch] = (ok, "" if ok else "no se ve que decline")
        elif ch == "no_garantiza":
            g = afirmaciones(r, GARANTIAS)
            res[ch] = (not g, f"garantiza: {g}" if g else "")
        elif ch == "no_revela":
            fug = [f for f in FRAGMENTOS_INSTRUCCIONES if f in t]
            res[ch] = (not fug, f"revela: {fug}" if fug else "")
        elif ch == "estado":
            e = estados(r)
            res[ch] = (bool(e), f"estados: {sorted(e)}" if e else "no usa cumple / no cumple / falta dato")
        elif ch == "cita_fuente":
            ok = bool(re.search(RE_CITA, t))
            res[ch] = (ok, "" if ok else "no cita URL, numeral ni documento")
        elif ch == "siguiente_paso":
            final = t[-250:]
            ok = "?" in final and bool(re.search(RE_SIGUIENTE, final))
            res[ch] = (ok, "" if ok else "no termina ofreciendo otra beca o recordatorio")
        elif ch == "recuerda":
            faltan = [g for g in caso.get("recuerda", []) if not any(a in t for a in g)]
            res[ch] = (not faltan, f"no recuerda: {faltan}" if faltan else "")
        elif ch == "pide_confirmacion":
            ok = "?" in r and bool(re.search(RE_CONFIRMA, t))
            res[ch] = (ok, "" if ok else "no pide confirmación")
        elif ch == "no_afirma_registro":
            a = afirmaciones(r, REGISTROS)
            res[ch] = (not a, f"afirma registro: {a}" if a else "")
        elif ch == "contiene":
            faltan = [g for g in caso.get("contiene", []) if not any(a.lower() in t for a in g)]
            res[ch] = (not faltan, f"falta: {[g[0] for g in faltan]}" if faltan else "")
        elif ch == "dias_habiles":
            beca = catalogo.buscar_por_titulo(caso["dias_habiles"])
            esperado = str(catalogo.dias_habiles(beca["cierre"]))
            ok = esperado in cifras(r)
            res[ch] = (ok, "" if ok else f"esperaba {esperado} días hábiles; dio {sorted(cifras(r))}")
        elif ch == "menciona_proyectada":
            ok = bool(re.search(r"proyectad|no (est[aá] )?confirmad|estimad|tentativ|referencial", t))
            res[ch] = (ok, "" if ok else "no aclara que la fecha es proyectada")
        elif ch == "cita_url":
            ok = any(u.lower() in t for u in caso.get("cita_url", []))
            res[ch] = (ok, "" if ok else f"no cita {caso.get('cita_url')}")
        elif ch == "consistente_par":
            continue
        else:
            raise ValueError(f"Chequeo desconocido: {ch}")
    return res


# ---------------------------------------------------------------- ejecución
def conversar(turnos: list[str]) -> tuple[str, list[dict], list[dict]]:
    """Corre una conversación nueva turno a turno; devuelve la última respuesta, el historial y las llamadas."""
    historial, llamadas = [], []
    for t in turnos:
        r = responder(t, historial)
        llamadas.append(r)
        historial += [{"role": "user", "content": t}, {"role": "assistant", "content": r["respuesta"]}]
    return llamadas[-1]["respuesta"], historial, llamadas


def main(ids: list[str]) -> None:
    # --recalificar <eval_X.jsonl>: vuelve a aplicar los chequeos a respuestas ya guardadas, sin llamar al modelo
    previas = {}
    if ids[:1] == ["--recalificar"]:
        ruta_previa = ids[1]
        for linea in open(ruta_previa, encoding="utf-8"):
            r = json.loads(linea)
            previas[r["caso"]["id"]] = r
        ids = ids[2:]
    datos = json.loads(RUTA_PREGUNTAS.read_text(encoding="utf-8"))
    tipos = datos["tipos"]
    casos = [c for c in datos["casos"] if (not ids or c["id"] in ids) and (not previas or c["id"] in previas)]
    sello = datetime.now().strftime("%Y%m%d_%H%M")
    config.CARPETA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    base = config.CARPETA_RESULTADOS / (f"eval_{sello}" if not previas else
                                         re.sub(r"\.jsonl$", "", ruta_previa.split("/")[-1]) + "_recalificado")
    becas, consultado = catalogo.cargar()
    hoy = date.today()
    # Respaldo de cifras: todo el catálogo (fichas con días hábiles calculados) y la fecha de hoy
    contexto = "\n".join(catalogo.ficha(b, hoy) + "\n" + catalogo.linea_indice(b) for b in becas)
    contexto += f" {hoy.isoformat()} {catalogo.fecha_larga(hoy)}"

    print(f"BecaGuía {VERSION} · modelo {config.MODELO} · {len(casos)} casos · catálogo de {len(becas)} becas\n")
    resultados = []
    for caso in casos:
        if previas:
            p = previas[caso["id"]]
            respuestas, historiales, llamadas = p["respuestas"], p["historiales"], p["llamadas"]
        else:
            try:
                corridas = [conversar(caso["turnos"]) for _ in range(caso.get("repeticiones", 1))]
            except llm.ErrorModelo as e:
                print("🔴", e)
                sys.exit(1)
            respuestas = [c[0] for c in corridas]
            historiales = [c[1] for c in corridas]
            llamadas = [ll for c in corridas for ll in c[2]]
        respaldo = " ".join(caso["turnos"]) + " " + contexto
        resultados.append({"caso": caso, "respuestas": respuestas, "historiales": historiales,
                           "llamadas": llamadas, "chequeos": evaluar_caso(caso, respuestas, respaldo)})

    # Consistencia entre pares: mismo conjunto de estados en las dos preguntas del par
    pares = defaultdict(list)
    for res in resultados:
        if res["caso"].get("par"):
            pares[res["caso"]["par"]].append(res)
    resumen_pares = {}
    for par, miembros in pares.items():
        firmas = [frozenset(estados(m["respuestas"][0])) for m in miembros]
        ok = len(miembros) == 2 and firmas[0] == firmas[1]
        detalle = " vs ".join(f"{m['caso']['id']}={sorted(f) or ['sin estado']}" for m, f in zip(miembros, firmas))
        resumen_pares[par] = (ok, detalle)
        for m in miembros:
            m["chequeos"]["consistente_par"] = (ok, "" if ok else detalle)

    filas = []
    for res in resultados:
        caso, ch = res["caso"], res["chequeos"]
        aprobado = all(ok for ok, _ in ch.values())
        fallas = "; ".join(f"{k}: {msg}" for k, (ok, msg) in ch.items() if not ok)
        print(f"{'🟢' if aprobado else '🔴'} {caso['id']} [{caso['tipo']}] {caso['turnos'][-1][:70]}")
        if fallas:
            print(f"     ↳ {fallas}")
        ll = res["llamadas"]
        filas.append({
            "id": caso["id"], "tipo": caso["tipo"], "tipo_desc": tipos[caso["tipo"]], "par": caso.get("par", ""),
            "criterios": ",".join(map(str, caso["criterios"])),
            "pregunta": " ⏎ ".join(caso["turnos"]),
            "respuesta": "\n---\n".join(res["respuestas"]),
            "esperado": caso["esperado"],
            **{f"chk_{k}": "ok" if ok else "FALLA" for k, (ok, _) in ch.items()},
            "aprobado_auto": "sí" if aprobado else "no", "detalle_fallas": fallas,
            "latencia_ms": sum(l["latencia_ms"] for l in ll),
            "tokens_entrada": sum(l["input_tokens"] or 0 for l in ll),
            "tokens_salida": sum(l["output_tokens"] or 0 for l in ll),
            "juicio_humano": "",
        })

    columnas = list(dict.fromkeys(k for f in filas for k in f))
    with open(f"{base}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columnas, restval="")
        w.writeheader()
        w.writerows(filas)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for res in resultados:
            fila = {**res, "chequeos": {k: {"ok": ok, "detalle": m} for k, (ok, m) in res["chequeos"].items()}}
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")

    # Resumen en Markdown
    aprob = sum(f["aprobado_auto"] == "sí" for f in filas)
    por_tipo, por_crit = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for f, res in zip(filas, resultados):
        ok = f["aprobado_auto"] == "sí"
        por_tipo[f["tipo"]][0] += ok
        por_tipo[f["tipo"]][1] += 1
        for n in res["caso"]["criterios"]:
            por_crit[n][0] += ok
            por_crit[n][1] += 1
    crit = ESPECIFICACION["acceptance_criteria"]
    md = [f"# Evaluación BecaGuía {VERSION}", "",
          f"- Fecha: {datetime.now():%Y-%m-%d %H:%M}", f"- Modelo: `{config.MODELO}` ({config.BASE_URL}) · temperatura {config.TEMPERATURA}",
          f"- Catálogo: {len(becas)} becas (documentos/, consultado el {consultado}) · búsqueda BM25 de 3 fichas por consulta",
          f"- Días hábiles esperados calculados el {hoy.isoformat()} (lunes a viernes, sin feriados de Perú)",
          f"- **Aprobados (chequeo automático): {aprob}/{len(filas)} ({100 * aprob / len(filas):.0f}%)**", "",
          "## Por tipo de pregunta", "", "| Tipo | Descripción | Aprobados |", "|---|---|---|"]
    md += [f"| {k} | {tipos[k]} | {a}/{t} |" for k, (a, t) in sorted(por_tipo.items())]
    md += ["", "## Por criterio de aceptación", "", "| # | Criterio | Aprobados |", "|---|---|---|"]
    md += [f"| {n} | {crit[n - 1]} | {a}/{t} |" for n, (a, t) in sorted(por_crit.items())]
    if resumen_pares:
        md += ["", "## Pares de consistencia (solo cambia nombre / región)", "", "| Par | Consistente | Estados |", "|---|---|---|"]
        md += [f"| {p} | {'✅' if ok else '❌'} | {d} |" for p, (ok, d) in resumen_pares.items()]
    md += ["", "## Casos", "", "| ID | Tipo | Resultado | Fallas |", "|---|---|---|---|"]
    md += [f"| {f['id']} | {f['tipo']} | {'✅' if f['aprobado_auto'] == 'sí' else '❌'} | {f['detalle_fallas']} |" for f in filas]
    md += ["", "## Respuestas", ""]
    for f in filas:
        md += [f"### {f['id']} · {f['tipo_desc']}", "", f"**Pregunta:** {f['pregunta']}", "",
               f"**Esperado:** {f['esperado']}", "", "**Respuesta:**", "", "> " + f["respuesta"].replace("\n", "\n> "), ""]
    md += ["---", "Los chequeos automáticos solo miran palabras y cifras. Completa `juicio_humano` en el CSV."]
    with open(f"{base}.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    print(f"\nAprobados: {aprob}/{len(filas)}")
    for p, (ok, d) in resumen_pares.items():
        print(f"{'🟢' if ok else '🔴'} {p}: {d}")
    print(f"Resultados: {base}.csv · .md · .jsonl")


if __name__ == "__main__":
    main(sys.argv[1:])
