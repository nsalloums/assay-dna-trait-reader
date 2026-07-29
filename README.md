# 🧬 ASSAY — Lector local de rasgos de ADN, centrado en la privacidad

[![CI](https://github.com/nsalloums/assay-dna-trait-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/nsalloums/assay-dna-trait-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

Suelta tu archivo de ADN de consumo (23andMe, AncestryDNA, FamilyTreeDNA, MyHeritage,
LivingDNA, tellmeGen o CSV/TSV genérico) y lee los rasgos asociados a tus genotipos —
**100% en local, en tu propia máquina.** Sin cuentas, sin subidas, sin nube, sin
telemetría. Tu ADN nunca sale de tu computadora.

> **Solo para uso educativo — no es un dispositivo médico ni consejo médico.** En un
> estudio de 49 casos remitidos a un laboratorio clínico para confirmación, el **40% de
> las variantes raras y de alta penetrancia** (BRCA1/2, TP53, MLH1…) halladas en datos
> crudos de consumo **no se confirmaron** ([Tandy-Connor et al., *Genet Med* 2018](https://doi.org/10.1038/gim.2018.38)).
> Esa cifra viene de una cohorte seleccionada y no se aplica por igual a los SNP comunes
> que muestra esta app, pero marca el punto: confirma cualquier resultado de salud con una
> prueba de grado clínico y un/a profesional. Nada aquí es un diagnóstico.

### ▶ [Pruébalo ahora en tu navegador — sin instalar nada](https://assay-dna-trait-reader.vercel.app)

Suelta tu archivo, o pulsa **«Probar con un archivo de ejemplo»** si no tienes uno a mano.
Todo corre en tu navegador: no hay backend, no se sube nada.

---

## Procedencia y límites (léelo antes que nada)

Lo construí **yo, sin formación clínica ni en genética**, mediante orquestación multi-agente
con IA. Yo especifiqué las restricciones — local-only, no reempaquetar PharmGKB por su
copyleft, marcar los SNP palindrómicos en vez de adivinar — y la IA escribió la mayor parte
del código bajo ellas. El prompt completo está publicado en
[`docs/how-this-was-built.md`](docs/how-this-was-built.md).

Qué significa eso en la práctica, dicho sin adornos:

- **Ningún genetista ha revisado este proyecto.** Las 35 interpretaciones del seed curado son
  resúmenes en lenguaje llano de asociaciones bien replicadas; nombran su base de datos de
  origen (GWAS Catalog / ClinVar / PharmGKB) pero **no llevan cita por asociación** (sin PMID).
  Están pendientes de respaldo bibliográfico individual.
- **Lo que sí está verificado por máquina** es la arquitectura de privacidad, no la biología:
  `tests/test_privacy_g3.py` bloquea todos los sockets y comprueba que análisis→anotación
  sigue funcionando. Esa parte es mecánica, no una promesa.
- **Los tamaños de efecto proceden mayoritariamente de cohortes europeas** y no transfieren
  igual a poblaciones mestizas. Ver [Ancestría](#ancestría-una-limitación-real).

---

## Inicio rápido

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python run.py            # → http://127.0.0.1:8765
```

En el primer arranque la app construye automáticamente una pequeña **base de datos
curada sin conexión**, así que funciona de inmediato sin red. Arrastra un archivo de ADN
a la página y tus rasgos aparecen en tiempo real, agrupados por categoría, cada uno con
su fuente y su fecha, y con una **explicación breve y fácil de leer** de lo que significa.

### Enriquecer con las bases de datos públicas completas (opcional, una vez)

```bash
python -m app.db_update update            # GWAS Catalog + ClinVar + PharmGKB
python -m app.db_update update --sources gwas_catalog,pharmgkb   # elegir fuentes
python -m app.db_update status            # ver actualidad
```

Este es el **único** paso que usa la red. Descarga bases de datos de anotación *públicas*
a tu máquina (no contienen datos de usuario). Después de ejecutarlo una vez, la app
funciona totalmente sin conexión. También puedes lanzarlo desde el panel **Fuentes de
datos** de la app.

---

## Modelo de privacidad (cómo garantizamos que tu ADN es tuyo)

| Garantía | Cómo se aplica |
|---|---|
| Escucha **solo en loopback** | `run.py` rechaza cualquier host que no sea `127.0.0.1` (`app/core/security.assert_loopback`). |
| Los genotipos viven **solo en RAM** | La subida se procesa en memoria; las llamadas quedan en un almacén de sesión en memoria con caducidad (`app/core/sessions.py`). Nunca se escriben en disco ni en una BD. |
| El camino de anotación **no toca la red** | `app/core/*` y `app/api/{parse,annotate}.py` **no importan ningún cliente HTTP**. Toda la red está aislada en `app/db_update/sources.py`, al que solo llega `POST /api/db/update`. Una prueba bloquea todos los sockets y comprueba que el análisis→anotación sigue funcionando. |
| La BD en ejecución es de **solo lectura** | El almacén de anotación se abre `mode=ro`; físicamente no se pueden escribir datos de usuario. El emparejamiento usa una tabla temporal de rsIDs (se descarta al cerrar). |
| **Sin persistencia ni registro** de datos genéticos | Ningún genotipo se escribe en disco, logs o temporales. Un filtro de logs redacta cualquier cosa que parezca un rsID/genotipo. Sin analítica, sin SDK de reportes. |
| **CSP** estricta | `connect-src 'self'` impide que la SPA contacte cualquier host de terceros; sin CDN, sin fuentes web, todo autoalojado (`app/core/security.py`). |
| El paso de actualización lleva **cero datos de usuario** | Solo GET contra una lista blanca de hosts (EBI / NCBI / PharmGKB / Ensembl); cualquier otro host se rechaza, incluso tras redirecciones. |

Todos los datos de prueba son **sintéticos** (generados por `SyntheticSNPGenerator` de
`snps`). Nunca se usa un archivo humano real.

---

## Fuentes de datos y licencias

La app combina bases de datos de anotación **mantenidas activamente** (no SNPedia, cuyos
términos restringen el rastreo). Ver [`NOTICE`](NOTICE) para la atribución completa.

| Fuente | Qué aporta | Licencia | Cómo la usamos |
|---|---|---|---|
| **NHGRI-EBI GWAS Catalog** | Asociaciones SNP ↔ rasgo/fenotipo | Términos EBI — reutilizable con cita | Descargada en el dispositivo por `update_databases` |
| **NCBI ClinVar** | Significado clínico de variantes | Dominio público (Gob. EE. UU.) | Descargada en el dispositivo por `update_databases` |
| **ClinPGx** (antes PharmGKB) | Farmacogenómica (respuesta a fármacos) | **CC BY-SA 4.0 (copyleft)** | **Nunca se reempaqueta** — se descarga en *tu* máquina al actualizar, en su propia partición, con atribución |
| **dbSNP / Ensembl** | Normalización de rsID, coordenadas GRCh37/38 | Dominio público / EMBL-EBI | **Solo en tiempo de construcción** (`scripts/enrich_seed_coords.py`); nunca en ejecución |

**Por qué PharmGKB no viene incluido:** CC BY-SA es copyleft viral. Empaquetar sus datos
obligaría a todo el conjunto distribuido a estar bajo BY-SA. En su lugar distribuimos
*código*, y la persona usuaria descarga ClinPGx localmente — manteniendo el artefacto
distribuido libre de copyleft. El seed redistribuible (`data/seed/associations.json`)
contiene solo interpretaciones propias del proyecto, que **nombran** su base de datos de
origen pero **no llevan cita por asociación** (ver [Procedencia y límites](#procedencia-y-límites-léelo-antes-que-nada)).

El `LICENSE.txt` que viene *dentro* de la descarga de ClinPGx añade dos condiciones por
encima de un CC BY-SA normal, y por eso no basta con "atribuir y ya": quien reciba datos
alterados debe aceptar antes la misma licencia (con prueba de ello disponible para
PharmGKB), y *"under no circumstances can PharmGKB data be sold for other's private or
commercial use"*.

**Por qué no usamos SNPedia:** es la fuente obvia para un lector de rasgos y la usa
prácticamente todo el nicho — incluida la herramienta más popular del sector. Pero SNPedia
es **CC BY-NC-SA 3.0** (no comercial + copyleft) y es **propiedad de MyHeritage desde
2019**. Construir sobre ella significa que tu proyecto hereda una restricción no comercial
y depende del wiki de una empresa que compite con las pruebas que analizas. Preferimos
fuentes de instituciones públicas (EMBL-EBI, NCBI, Stanford/St. Jude) aunque cueste más
trabajo.

Cada resultado muestra su **fuente, versión/lanzamiento y la fecha “datos actualizados a”**,
con un punto de actualidad. Reejecutar `update_databases` avanza esas fechas.

---

## Explicación de cada resultado (fácil de leer)

Cada coincidencia muestra:

- El **genotipo** detectado (p. ej. `GG`), el **rasgo** y el **gen**.
- Una **línea breve en lenguaje sencillo** de lo que significa (p. ej. *“Lo más probable es
  que tengas los ojos azules.”*).
- Al desplegar: un bloque **“¿Qué significa?”** con la explicación completa, contexto extra,
  la procedencia técnica (rsID, cromosoma, alelo, evidencia, fuente + fecha) y, en resultados
  de salud, el aviso de no-diagnóstico.

El seed curado (los rasgos más conocidos) está redactado en **español claro**. Los rasgos de
las fuentes masivas (GWAS/ClinVar/PharmGKB) conservan el nombre en su idioma original (son
datos de la fuente), pero se enmarcan con una explicación honesta en español que nunca se
lee como un diagnóstico.

---

## Cómo tratamos las partes difíciles (correctamente)

- **Hebra / orientación** (el error nº 1). Los genotipos se normalizan a la **hebra directa
  (+)**, ordenados alfabéticamente, antes de comparar (`app/core/strand.py`). Las lecturas
  antiguas en hebra − de SNP *no palindrómicos* se detectan y complementan; los SNP
  **palindrómicos** A/T y C/G (p. ej. `rs713598`, `rs9939609`, `rs16891982`, `rs1799945`) no
  se pueden resolver por complemento, así que confiamos en la hebra + del proveedor y los
  **marcamos**, sin adivinar.
- **Versión del genoma (36/37/38)**. `snps` detecta la versión; el emparejamiento es por
  **rsID** (no por posición), así que genotipos idénticos en GRCh37 vs GRCh38 dan resultados
  idénticos.
- **No-llamadas** (`--`, `00`, `NN`, `DD`, `II`) se descartan, nunca se emparejan.
- **Haplotipos multi-SNP** como **APOE** ε2/ε3/ε4 se resuelven desde `rs429358` + `rs7412`.
- **Puerta de salud**. Las categorías de salud/clínicas/farmacogenómicas se ocultan tras una
  confirmación explícita y llevan los avisos de no-diagnóstico y falsos positivos.

---

## Ancestría: una limitación real

La app está en español, así que buena parte de quien la use tendrá ancestría mestiza
(europea / amerindia / africana). **Los tamaños de efecto que muestra proceden
mayoritariamente de cohortes de ascendencia europea y no transfieren igual.** Esto no es un
detalle legal: cambia el número.

- **APOE.** El seed dice que ε3/ε4 conlleva "unas 2–3× más riesgo medio de Alzheimer tardío".
  Ese número plano esconde una variación grande: un metaanálisis de 2023 halló OR desde 1,88
  (hispanos caribeños) hasta 3,51 (sudamericanos) según la proporción de ancestría europea.
- **`rs4988235` (lactasa).** **No marca persistencia de lactasa en la mayoría de poblaciones
  de ascendencia africana** — allí la señal la llevan otras variantes (`rs182549`,
  `rs41380347`). Un `GG` → "más probable intolerancia" será sencillamente incorrecto para
  parte de la población afrodescendiente latinoamericana.
- **`rs12913832` (color de ojos).** ~85% predictivo en europeos del norte; bastante menos en
  poblaciones del sur de Europa y mestizas.

Trabajo pendiente: un campo `ancestry_basis` por asociación y un aviso persistente en la UI.
Hoy solo está documentado aquí, que es menos de lo que debería.

---

## Arquitectura

```
run.py                      lanzador de un comando (solo loopback)
app/
  main.py                   app FastAPI: SPA estática + API, middleware CSP, ciclo de vida
  config.py  db.py          rutas/constantes; ayudantes SQLite (solo lectura en ejecución)
  api/                      parse · annotate (SSE) · db/status+update · health
  core/                     parsing (snps) · strand · sessions · annotation · security · content
  db_update/                sources (ÚNICO módulo de red) · normalize · update · build_seed
data/
  schema.sql                DDL del almacén de anotación unificado
  seed/associations.json    seed curado redistribuible (35 asociaciones + regla APOE), en español
  annotations.db            construido localmente (ignorado por git)
web/                        SPA en JS puro (diseño ASSAY; sin recursos externos)
demo/                       demo estático: el mismo motor portado a JS, sin backend (Vercel)
tests/                      corpus sintético + G1/G2/G3 golden + pruebas de privacidad
docs/how-this-was-built.md  el prompt de orquestación multi-agente con el que se construyó
.github/workflows/ci.yml    tests en Linux/macOS/Windows × Python 3.12/3.13 + job de privacidad
scripts/enrich_seed_coords.py   enriquecimiento de coordenadas (Ensembl) en construcción
scripts/translate_seed_es.py    traducción del seed curado al español
```

El flujo análisis → anotación: la subida se procesa en memoria con `snps`; los genotipos van
a una sesión en memoria; `POST /api/annotate` transmite las coincidencias por **SSE** a medida
que se resuelven (renderizado progresivo), emparejando contra el almacén local de solo lectura.

---

## Pruebas

```bash
python -m pytest tests/ -q
```

Cubre los criterios de aceptación con un corpus **sintético** (7 archivos de proveedor/versión/
casos límite con genotipos inyectados conocidos y valores esperados):

- **G1 Análisis** — detección de proveedor + versión, normalización de hebra, manejo de no-llamadas.
- **G2 Anotación** — anotaciones exactas, cero falsos positivos, diplotipo APOE, identidad
  GRCh37/38, volteos de hebra −, no-volteo de palíndromos, independencia de formato.
- **G3 Privacidad** — análisis→anotación con **todos los sockets bloqueados**, escaneo centinela de
  no-persistencia, almacén de solo lectura, purga de sesión, lista blanca de hosts, redacción de logs.
- **Normalizador de ClinVar** — validado con un fixture (sin descargar 440 MB).

Regenerar el corpus / reconstruir el seed:

```bash
python -m tests.make_corpus            # escribe fixtures en tests/corpus/
python -m app.db_update seed           # reconstruye la BD del seed
python scripts/translate_seed_es.py    # retraduce el seed curado al español
python scripts/enrich_seed_coords.py   # refresca coordenadas del seed desde Ensembl
```

---

## Licencia

[MIT](LICENSE) para el código y el seed curado de este proyecto. Los datos y dependencias de
terceros conservan sus propias licencias — ver [`NOTICE`](NOTICE). Los datos de PharmGKB no se
redistribuyen aquí; se descargan en tu máquina bajo CC BY-SA 4.0.
