# Proyecto Becas · Asistente de elegibilidad y calendario de becas de maestría (Grupo 1)

Asistente de IA generativa que evalúa el perfil de profesionales peruanos contra los requisitos de
**becas de maestría** y calcula los días hábiles al cierre (Candidato 3 del [Anexo A](docs/)).
El system prompt sigue [System_Prompt_Becas_Maestria.docx](docs/) y responde con un **catálogo de
40 becas de KipuBecas** ([documentos/becas_maestria_v4.json](documentos/)). Corre **en tu
computadora** con un modelo local (Ollama), sin servicios de Google ni claves de API.

Tópicos de Inteligencia Artificial Generativa · MCEIS · UNI
Integrantes: Hugo Fernandez, Gener Murga, Oscar Cutipa, Víctor Valero.

## Estructura

```
Proyecto - Becas/
├── README.md
├── requirements.txt
├── Modelfile                  ← crea becas-qwen2.5 (qwen2.5:7b con 16k de contexto)
├── .env.example               ← copia a .env si quieres otro modelo o proveedor
├── paso1_chat_gradio.py       ← PASO 1: chat con historial en Gradio
├── paso2_evaluacion.py        ← PASO 2: corre las 20 preguntas y califica
├── becas_bot/
│   ├── config.py              ← modelo, URL, topes
│   ├── especificacion.py      ← 3 criterios y las 6 partes del system prompt (texto del docx)
│   ├── catalogo.py            ← carga el dataset, busca fichas (BM25) y calcula días hábiles
│   ├── llm.py                 ← llamada al modelo (API compatible con OpenAI)
│   └── chat.py                ← arma system + catálogo + historial + mensaje; registra trazas
├── documentos/
│   └── becas_maestria_v4.json ← dataset: 40 becas de KipuBecas con URL oficial
├── evaluacion/
│   ├── preguntas_evaluacion.json   ← las 20 preguntas (4 tipos + 2 pares), verificadas contra el dataset
│   └── resultados/                 ← CSV, MD y JSONL de cada corrida
├── trazas/                    ← trazas_chat.jsonl (cada turno del chat)
└── docs/                      ← Anexo A, System Prompt y material de referencia
```

## Instalación (una sola vez, macOS)

```bash
brew install ollama
brew services start ollama          # deja Ollama corriendo en segundo plano
ollama pull qwen2.5:7b              # ~4.7 GB

cd "Proyecto - Becas"
ollama create becas-qwen2.5 -f Modelfile   # misma red, contexto de 16k (por defecto Ollama usa 4k y corta)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Paso 1 · Chat con historial en Gradio

```bash
.venv/bin/python paso1_chat_gradio.py            # abre http://127.0.0.1:7860
.venv/bin/python paso1_chat_gradio.py --share    # enlace público temporal con usuario "becas" y código
```

En cada turno `becas_bot/chat.py` envía al modelo:

```
[system: 6 partes del prompt
         + fecha de hoy
         + índice del catálogo (1 línea por beca: nivel, país, cierre)
         + 3 fichas detalladas de las becas más relacionadas con la consulta]
+ historial (hasta 10 turnos)
+ [user: mensaje nuevo]
```

- **Búsqueda:** BM25 sobre título, organización y ficha. La consulta une el mensaje nuevo y los dos
  anteriores del usuario, para que "¿y cuándo cierra?" siga encontrando la beca mencionada antes.
- **Índice completo:** el modelo ve las 40 becas en una línea cada una; si una beca (p. ej. Chevening)
  no está, debe decir que no dispone de la información.
- **Días hábiles:** se calculan en código (lunes a viernes, sin feriados nacionales del Perú) y van en
  la ficha; el modelo no los calcula.
- **Fechas proyectadas:** KipuBecas marca casi todas las fechas como proyectadas; la ficha lo dice.

Cada turno se guarda en `trazas/trazas_chat.jsonl`.

## Paso 2 · 20 preguntas de evaluación

```bash
.venv/bin/python paso2_evaluacion.py             # los 20 casos (~10-15 min con el modelo local)
.venv/bin/python paso2_evaluacion.py P02 P03     # solo algunos
.venv/bin/python paso2_evaluacion.py --recalificar evaluacion/resultados/eval_X.jsonl   # re-juzga sin llamar al modelo
```

| Tipo (Compuerta 1) | Casos | Criterio | Qué se comprueba |
|---|---|---|---|
| A · Con respuesta | P01–P07 | 3 | Datos correctos del catálogo (monto, edad, fecha, días hábiles), estado cumple / no cumple / falta dato, URL de la beca, siguiente paso; P07 usa historial |
| B · Sin respuesta | P08–P12 | 1 | Becas fuera del catálogo (Chevening, MEXT) o datos que la ficha no trae: dice que no dispone y no inventa |
| C · Fuera del alcance | P13–P17 | 2 | Declina garantizar, postular por el usuario, pregrado, temas ajenos, revelar el prompt |
| D · Pedido de acción | P18–P20 | 3 | Da la fecha correcta y pide aprobación antes de registrar el recordatorio |
| **Pares** | P02/P03, P04/P05 | — | Solo cambia nombre y región: el estado debe ser el mismo |

Las respuestas esperadas se verifican contra el dataset (la "tabla armada a mano" del Anexo A).
Los días hábiles esperados se recalculan el día de cada corrida.

Cada corrida genera en `evaluacion/resultados/` un CSV (con columna **`juicio_humano`**), un MD con
el resumen y un JSONL con el detalle.

> Los chequeos automáticos solo miran palabras y cifras. La decisión final es humana.

## Actualizar el catálogo

Reemplaza o agrega archivos `.json` en `documentos/` con el mismo formato (lista de becas con
`titulo`, `fecha_limite_iso`, `url_oficial`, `requisitos`, etc.). La fecha de consulta se toma de la
fecha de modificación del archivo. Si cambian las becas, revisa las preguntas de evaluación.

## Próximos pasos

- Reemplazar BM25 por embeddings si las consultas por perfil (sin nombre de beca) fallan.
- Registrar el recordatorio de verdad (lista de seguimiento sintética) solo tras la aprobación humana.
- Correr la evaluación 2 o 3 veces y completar el juicio humano.
