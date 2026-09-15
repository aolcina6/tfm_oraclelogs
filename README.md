
# 📊 Procesamiento Automático de Logs en Entornos Oracle JD Edwards

**Trabajo de Fin de Máster — Andrea Olcina**

Solución para el procesamiento, parsing y minado de patrones (*log parsing*) de logs generados en entornos Oracle JD Edwards (E1), incluyendo un pipeline de ingesta, clustering con Drain/Drain3 y generación automática de plantillas y expresiones regulares para nuevos orígenes de log.

---

## 📑 Contenido

- [Descripción general](#-descripción-general)
- [Arquitectura del pipeline](#-arquitectura-del-pipeline)
- [Instalación](#-instalación)
- [Orígenes soportados](#-orígenes-soportados)
- [Uso rápido](#-uso-rápido)
- [Notebooks de referencia](#-notebooks-de-referencia)
- [Estructura del repositorio](#-estructura-del-repositorio)
- [Onboarding de nuevos orígenes de log](#-onboarding-de-nuevos-orígenes-de-log)

---

## 📖 Descripción general

Este proyecto automatiza el procesamiento de logs heterogéneos de un entorno JD Edwards (AIS, BSSV, E1Root, JDE, JAS, Listener, alertas, etc.), normalizando timestamps, clasificando registros contra plantillas conocidas y permitiendo el descubrimiento de nuevos patrones mediante algoritmos de *log parsing* (Drain / Drain3) y agrupación semántica basada en embeddings.

## 🏗️ Arquitectura del pipeline

1. **Parsing** — Detección del tipo de log, extracción de registros, normalización de timestamps y clasificación contra plantillas conocidas.
2. **Drain / Drain3** — Minado de patrones sobre logs crudos o ya parseados, para descubrir clusters de mensajes similares.
3. **Template Generator** — A partir de los clusters de Drain3:
   - Extracción de templates.
   - Agrupación semántica (clustering aglomerativo jerárquico sobre embeddings).
   - Generación de expresiones regulares que codifican las partes variables de cada plantilla.
4. **Onboarding** — Flujo guiado para dar de alta nuevos tipos de log no soportados todavía.

## ⚙️ Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
Aquí tienes el contenido completo del README que había generado, listo para pegar/completar en tu [`README.md`](README.md ):

```markdown

# 📊 Procesamiento Automático de Logs en Entornos Oracle JD Edwards

**Trabajo de Fin de Máster — Andrea Olcina**

Solución para el procesamiento, parsing y minado de patrones (*log parsing*) de logs generados en entornos Oracle JD Edwards (E1), incluyendo un pipeline de ingesta, clustering con Drain/Drain3 y generación automática de plantillas y expresiones regulares para nuevos orígenes de log.

---

## 📑 Contenido

- [Descripción general](#-descripción-general)
- [Arquitectura del pipeline](#-arquitectura-del-pipeline)
- [Instalación](#-instalación)
- [Orígenes soportados](#-orígenes-soportados)
- [Uso rápido](#-uso-rápido)
- [Notebooks de referencia](#-notebooks-de-referencia)
- [Estructura del repositorio](#-estructura-del-repositorio)
- [Onboarding de nuevos orígenes de log](#-onboarding-de-nuevos-orígenes-de-log)

---

## 📖 Descripción general

Este proyecto automatiza el procesamiento de logs heterogéneos de un entorno JD Edwards (AIS, BSSV, E1Root, JDE, JAS, Listener, alertas, etc.), normalizando timestamps, clasificando registros contra plantillas conocidas y permitiendo el descubrimiento de nuevos patrones mediante algoritmos de *log parsing* (Drain / Drain3) y agrupación semántica basada en embeddings.

## 🏗️ Arquitectura del pipeline

1. **Parsing** — Detección del tipo de log, extracción de registros, normalización de timestamps y clasificación contra plantillas conocidas.
2. **Drain / Drain3** — Minado de patrones sobre logs crudos o ya parseados, para descubrir clusters de mensajes similares.
3. **Template Generator** — A partir de los clusters de Drain3:
   - Extracción de templates.
   - Agrupación semántica (clustering aglomerativo jerárquico sobre embeddings).
   - Generación de expresiones regulares que codifican las partes variables de cada plantilla.
4. **Onboarding** — Flujo guiado para dar de alta nuevos tipos de log no soportados todavía.

## ⚙️ Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Requiere Python 3.13. Ver requirements.txt para las versiones exactas de dependencias (boto3, drain3, Flask, pandas, scikit-learn, sentence-transformers, opensearch-py, etc.).

## 🗂️ Orígenes soportados

| Origen |
|---|
| `ais` |
| `alert_jde` |
| `bssv` |
| `e1root` |
| `jas` |
| `jde` |
| `listener` |

## 🚀 Uso rápido

### 1. Parsing

```bash
> ⚠️ Antes de ejecutar el parsing, descarga y descomprime la carpeta `templates/` (disponible en la misma fuente de descarga del proyecto). Es necesaria para la clasificación de registros contra plantillas conocidas.
>
> Puedes probar el pipeline con dos conjuntos de logs distintos (también descargados de la misma fuente): `example_logs/` (conjunto reducido) o `logs/` (conjunto completo).

python parsing/init.py --log-folder example_logs/ --output-folder example_parsed_logs/ --results-output-format json
```

### 2. Drain3 sobre logs parseados

```bash
python drain/drain_unified.py parsed3 \
    --origin ais \
    --parsed-folder example_parsed_logs \
    --parsed-format json \
    --output drain3_parsed_example \
    --no-auto-update
```

### 3. Generación de templates, agrupación semántica y regex

```bash
python template_generator/orchestrator.py ais
```

Para más detalle sobre argumentos y opciones de cada módulo, consulta los notebooks incluidos en el repositorio.

## 📓 Notebooks de referencia

| Notebook | Contenido |
|---|---|
| demo_completa.ipynb | Guía completa de los módulos (parsing, Drain, Drain3, template generator) con ejemplos ejecutables sobre un conjunto reducido de logs (example_logs). |
| `onboarding.ipynb` | Guía paso a paso para incorporar un nuevo tipo de log al sistema (bootstrapping de configuración, procesamiento y generación de templates/regex). |
| demo_flujo_template_generator.ipynb | Demo detallada del flujo interno de generación de templates (Drain3 → extracción → agrupación semántica → regex) sobre un origen concreto. |
| demo_flujo_parsing.ipynb | Demo de las utilidades del flujo de parseo. |
| demo_completa.ipynb | Demo completa de ambos flujos. |
## 📁 Estructura del repositorio

```
TFM/
├── config/                  # Configuraciones por origen (<origin>_config.py) y bootstrapper
├── storage/                 # Módulo de gestión del almacenamiento
├── parsing/                 # Pipeline de parsing e ingesta
├── drain/                   # Implementaciones de Drain / Drain3 y benchmarking
│   └── benchmarking/
├── template_generator/      # Extracción de templates, agrupación semántica y generación de regex
├── templates/               # Plantillas procesamiento de logs
├── utils/                   # Funcionalidades varias
├── example_logs/            # Conjunto reducido de logs de ejemplo
├── sample_logs/             # Logs de ejemplo para onboarding de nuevos orígenes
├── requirements.txt
├── demo_completa.ipynb
├── demo_flujo_onboarding_logs.ipynb
├── demo_flujo_template_generator.ipynb
├── demo_flujo_parsing.ipynb
└── README.md
```

---

## 🖥️ Visualización de resultados

Si quieres visualizar de forma interactiva los resultados parseados (ficheros `.parquet` / `.json` generados por el pipeline), puedes levantar un pequeño visor web local:

```bash
pip install flask
python viewer/app.py
```

Esto arrancará un servidor Flask accesible en tu `localhost` (por defecto en el puerto que indique la consola, normalmente `http://127.0.0.1:5002`, según la configuración en config.yaml). Desde ahí podrás explorar los logs procesados por fecha y origen sin necesidad de abrir manualmente los ficheros `.parquet`.

---

## 🧪 Benchmark contra logpai/logparser

Como parte del análisis del estado del arte, se incluye un módulo de *benchmarking* (`logparser_coverage.py`) que ejecuta varios algoritmos clásicos de *log parsing* del proyecto [logpai/logparser](https://github.com/logpai/logparser) (Drain, Spell, AEL, IPLoM, LenMa, LogCluster, LogSig, SLCT, entre otros) sobre los logs de example_logs, y calcula métricas de cobertura para compararlos con el pipeline propio.

### Instalación

```bash
pip install "logparser3 @ git+https://github.com/logpai/logparser.git" --no-deps
pip install regex pandas numpy
```

> ⚠️ Si aparece un conflicto de versiones con `regex` (por ejemplo, por incompatibilidad con `transformers`), instala la versión más reciente explícitamente: `pip install --upgrade "regex>=2025.10.22"`.

### Ejecución

```bash
python logparser_coverage.py \
    --origin ais \
    --log-file example_logs/COV_AIS_LOG.log \
    --log-format "<Date> <Time> <Level> <Content>" \
    --algorithms drain spell ael iplom \
    --output benchmarks_logparser
```

**Parámetros principales:**

| Argumento | Descripción |
|---|---|
| `--origin` | Nombre del origen a analizar (solo para etiquetar la salida). |
| `--log-file` | Ruta al fichero de log a procesar. |
| `--log-format` | Formato de log estilo logparser, ej. `"<Date> <Time> <Level> <Content>"`. |
| `--algorithms` | Uno o varios algoritmos a ejecutar (drain, `spell`, `ael`, `iplom`, `lenma`, `logcluster`, `logsig`, `slct`, entre otros). |
| `--output` | Carpeta donde se guardan los resultados y el resumen (default: `benchmarks_logparser`). |

### Resultados

Se genera una carpeta por algoritmo con los `_structured.csv` y `_templates.csv` originales de logparser, junto a un resumen comparativo:

```
benchmarks_logparser/
├── drain/
├── spell/
├── ael/
├── iplom/
└── ais_logparser_coverage.json
```

El JSON de resumen incluye, por algoritmo, el número de plantillas generadas, el porcentaje de líneas cubiertas y el tiempo de ejecución, lo que permite comparar de forma objetiva la cobertura obtenida frente al pipeline propio (Drain3 + template_generator).

---

## 🤖 Nota de honestidad académica

Este proyecto ha sido desarrollado con el apoyo de herramientas de inteligencia artificial (GitHub Copilot, modelos LLM tipo Claude/GPT) como asistentes de programación durante distintas fases del desarrollo: generación de código repetitivo o boilerplate, depuración, redacción y formateo de documentación (incluido este README), y sugerencias de refactorización.

Todo el diseño de la arquitectura, las decisiones metodológicas, la definición de los algoritmos de parsing/clustering, la validación de resultados y el análisis crítico presentado en la memoria del TFM son responsabilidad exclusiva de la autora. El uso de estas herramientas se ha limitado a la aceleración de tareas mecánicas de implementación, siempre bajo supervisión y revisión manual del código y contenido generado.

---
**Autora:** Andrea Olcina — Trabajo de Fin de Máster
```
