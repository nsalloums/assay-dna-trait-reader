#!/usr/bin/env python3
"""Traduce el contenido curado del seed al español (in situ).

Reescribe data/seed/associations.json y data/seed/_curated_base.json sustituyendo
los textos legibles (nombre del rasgo, efecto por genotipo, resumen, avisos,
categorías, haplotipo APOE) por español claro y breve. Conserva rsIDs,
coordenadas, alelos y banderas — solo cambia el texto que ve la persona.

Cada efecto está redactado como una explicación breve y fácil de leer de lo que
significa ese genotipo. Ejecuta después:  python -m app.db_update seed
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSOC = ROOT / "data" / "seed" / "associations.json"
BASE = ROOT / "data" / "seed" / "_curated_base.json"

# --- Traducciones por rsID: nombre del rasgo, resumen, y efecto por genotipo ---
ES: dict[str, dict] = {
    "rs12913832": {"trait": "Color de ojos (azul vs. marrón)",
        "summary": "El interruptor genético más fuerte del color de ojos. La variante G reduce la melanina (ojos claros) y la A la aumenta (marrón).",
        "gt": {"GG": "Lo más probable es que tengas los ojos azules.",
               "AG": "Ojos intermedios: verde, avellana o marrón; normalmente no azules.",
               "AA": "Lo más probable es que tengas los ojos marrones."}},
    "rs1800407": {"trait": "Modificador del color de ojos (OCA2)",
        "summary": "Un ajuste secundario del color de ojos; solo tiene sentido junto con rs12913832.",
        "gt": {"GG": "Este punto no aclara tus ojos.",
               "AG": "Ligero empujón hacia el verde/avellana si tienes fondo de ojos claros.",
               "AA": "Empujón más marcado hacia tonos no marrones."}},
    "rs1426654": {"trait": "Pigmentación de la piel",
        "summary": "Una de las variantes de mayor efecto en el color de piel humano.",
        "gt": {"AA": "Piel más clara (variante europea muy común).",
               "AG": "Pigmentación intermedia.",
               "GG": "Piel más oscura (variante ancestral)."}},
    "rs16891982": {"trait": "Pigmentación de piel y cabello (SLC45A2)",
        "summary": "Locus importante de pigmentación. Es un SNP palindrómico (C/G): confiamos en la orientación del proveedor.",
        "gt": {"GG": "Pigmentación más clara (típica europea).",
               "CG": "Pigmentación intermedia.",
               "CC": "Pigmentación más oscura."}},
    "rs1805007": {"trait": "Pelo rojo / piel clara (MC1R R151C)",
        "summary": "Variante clásica del pelo rojo en MC1R. El pelo rojo suele necesitar dos copias de este tipo de variantes.",
        "gt": {"TT": "Pelo rojo muy probable, piel clara, pecas y sensibilidad al sol.",
               "CT": "Portador/a: posible tono cobrizo, pecas y más sensibilidad al sol.",
               "CC": "Sin efecto de pelo rojo por esta variante."}},
    "rs1805008": {"trait": "Pelo rojo / piel clara (MC1R R160W)",
        "summary": "Segunda variante común de pelo rojo en MC1R; se interpreta junto con rs1805007.",
        "gt": {"TT": "Pelo rojo probable; piel clara, pecosa y sensible al sol.",
               "CT": "Portador/a de una variante MC1R; combinada con otras sube la probabilidad de pelo rojo.",
               "CC": "Sin efecto de pelo rojo por esta variante."}},
    "rs12203592": {"trait": "Color de cabello, pecas y bronceado (IRF4)",
        "summary": "Modificador fuerte de pecas y aclaramiento del cabello.",
        "gt": {"TT": "Cabello más claro de niño/a, más pecas y peor bronceado.",
               "CT": "Pecas y bronceado intermedios.",
               "CC": "Cabello más oscuro; te bronceas con más facilidad."}},
    "rs713598": {"trait": "Percepción del sabor amargo (PTC)",
        "summary": "Determina si percibes fuerte el amargor del PTC/PROP. Es un SNP palindrómico (C/G): confiamos en la orientación del proveedor.",
        "gt": {"GG": "Catador/a: percibes con fuerza el amargor.",
               "CG": "Catador/a intermedio/a.",
               "CC": "No catador/a: percibes poco o nada ese amargor."}},
    "rs1726866": {"trait": "Sabor amargo (marcador de apoyo TAS2R38)",
        "summary": "Segundo punto del gen TAS2R38; ayuda a confirmar si eres catador/a.",
        "gt": {"GG": "Asociado a percibir el amargor.",
               "AG": "Intermedio.",
               "AA": "Asociado a no percibir el amargor."}},
    "rs17822931": {"trait": "Tipo de cerumen y olor corporal (ABCC11)",
        "summary": "Rasgo mendeliano: define cerumen húmedo/seco y la cantidad de olor axilar.",
        "gt": {"TT": "Cerumen seco y menos olor corporal (variante común en Asia Oriental).",
               "CT": "Cerumen húmedo (dominante) y olor corporal típico.",
               "CC": "Cerumen húmedo y olor corporal típico."}},
    "rs72921001": {"trait": "Cilantro con sabor a jabón",
        "summary": "Cerca de un grupo de receptores del olfato; la variante C se asocia a percibir el cilantro como jabonoso.",
        "gt": {"CC": "Más probable que el cilantro te sepa a jabón.",
               "AC": "Algo más probable que notes un toque jabonoso.",
               "AA": "Menos probable que el cilantro te sepa a jabón."}},
    "rs4481887": {"trait": "Oler el espárrago en la orina",
        "summary": "Variante de receptores del olfato que decide si notas el olor del espárrago en la orina.",
        "gt": {"AA": "Detectas mejor el olor del espárrago en la orina.",
               "AG": "Capacidad de detección intermedia.",
               "GG": "Más probable que no lo huelas (‘anosmia al espárrago’)."}},
    "rs4988235": {"trait": "Tolerancia a la lactosa en la edad adulta",
        "summary": "La conocida ‘-13910C>T’: la variante A (persistencia) suele permitir digerir lácteos de adulto/a.",
        "gt": {"AA": "Sueles tolerar los lácteos en la edad adulta.",
               "AG": "Sueles tolerar los lácteos (la persistencia es dominante).",
               "GG": "Más probable intolerancia a la lactosa de adulto/a (contexto europeo)."}},
    "rs762551": {"trait": "Velocidad para metabolizar la cafeína",
        "summary": "La variante A metaboliza rápido la cafeína; con C tiende a ser más lenta. Es una tendencia, no una regla.",
        "gt": {"AA": "Metabolizador/a rápido/a: eliminas la cafeína deprisa.",
               "AC": "Metabolizador/a lento/a-intermedio/a.",
               "CC": "Metabolizador/a lento/a: la cafeína dura más (más nervios/insomnio)."}},
    "rs671": {"trait": "Rubor facial con el alcohol",
        "summary": "La variante A (ALDH2*2, común en Asia Oriental) hace que se acumule acetaldehído y aparezca el rubor. Rasgo educativo, no una evaluación de salud.",
        "gt": {"AA": "Rubor intenso; casi no puedes metabolizar el acetaldehído.",
               "AG": "Rubor, náuseas y taquicardia con el alcohol (déficit parcial).",
               "GG": "Metabolismo del alcohol típico; sin rubor por esta variante."}},
    "rs1229984": {"trait": "Velocidad para metabolizar el alcohol (ADH1B)",
        "summary": "La variante A (ADH1B*2) oxida el alcohol rápido; se asocia a menor dependencia. Se interpreta junto con rs671.",
        "gt": {"AA": "Metabolismo muy rápido; a menudo el alcohol resulta desagradable.",
               "AG": "Una copia rápida: conviertes el alcohol más deprisa de lo típico.",
               "GG": "Metabolismo típico."}},
    "rs1815739": {"trait": "Tipo de fibra muscular (ACTN3, ‘gen del sprint’)",
        "summary": "La variante C favorece potencia/velocidad; la T, resistencia. Efecto pequeño y recreativo, no predice talento.",
        "gt": {"CC": "Fibra rápida: perfil orientado a potencia/velocidad.",
               "CT": "Mixto: una copia funcional.",
               "TT": "Sin alfa-actinina-3: perfil más de resistencia (muy común)."}},
    "rs10427255": {"trait": "Estornudo con la luz (reflejo ACHOO)",
        "summary": "El reflejo de estornudar al pasar de la sombra a la luz brillante.",
        "gt": {"CC": "Más probable que estornudes con la luz brillante.",
               "CT": "Algo más probable que tengas el reflejo.",
               "TT": "Menos probable que estornudes con la luz."}},
    "rs4680": {"trait": "Metabolismo de la dopamina (COMT, ‘guerrero/preocupado’)",
        "summary": "Curiosidad de muy bajo valor predictivo. Solo a modo informativo, no es psicología.",
        "gt": {"GG": "Val/Val ‘guerrero’: aclaras la dopamina más rápido; a menudo más estable bajo estrés.",
               "AG": "Intermedio.",
               "AA": "Met/Met ‘preocupado’: aclaras más lento; asociado a sensibilidad al estrés."}},
    "rs6265": {"trait": "BDNF Val66Met (memoria/plasticidad, débil)",
        "summary": "Asociaciones de conducta débiles e inconsistentes; estrictamente educativo.",
        "gt": {"CC": "Val/Val: secreción de BDNF típica.",
               "CT": "Una copia Met.",
               "TT": "Met/Met: secreción de BDNF algo distinta en algunos estudios."}},
    "rs1801133": {"trait": "MTHFR C677T (enzima del folato)",
        "summary": "Popular pero muy sobrevalorado: las sociedades de genética NO recomiendan analizarlo de rutina. Solo contexto de bienestar.",
        "gt": {"GG": "Actividad normal de MTHFR (677CC).",
               "AG": "~65% de actividad (677CT): una copia de función reducida.",
               "AA": "~30% de actividad (677TT): enzima termolábil; puede subir algo la homocisteína."}},
    "rs1801131": {"trait": "MTHFR A1298C",
        "summary": "Efecto menor; mismo aviso de no sobreinterpretar que el C677T.",
        "gt": {"TT": "Normal (1298AA).",
               "GT": "Una copia 1298C; ligera reducción de actividad.",
               "GG": "1298CC; reducción de actividad modesta."}},
    "rs1800562": {"trait": "Hemocromatosis hereditaria (HFE C282Y)",
        "summary": "La variante mejor caracterizada de sobrecarga de hierro, pero de penetrancia INCOMPLETA: muchas personas AA nunca desarrollan sobrecarga.",
        "gt": {"GG": "Sin la variante C282Y.",
               "AG": "Portador/a de C282Y: normalmente sin síntomas.",
               "AA": "C282Y en homocigosis: principal genotipo de riesgo (penetrancia variable). Requiere estudio clínico de hierro."}},
    "rs1799945": {"trait": "HFE H63D (modificador del hierro)",
        "summary": "SNP palindrómico (C/G): confiamos en la orientación del proveedor. Baja penetrancia; solo relevante junto con C282Y.",
        "gt": {"CC": "Sin la variante H63D.",
               "CG": "Portador/a de H63D: normalmente benigno por sí solo.",
               "GG": "H63D en homocigosis: efecto leve; junto con C282Y sube el riesgo."}},
    "rs429358": {"trait": "APOE — sitio 1 (Alzheimer y lípidos)",
        "summary": "Se debe combinar con rs7412 para leer el genotipo APOE (ver el resultado de haplotipo). Locus de riesgo de Alzheimer más importante.",
        "gt": {"TT": "Sin ε4 desde este punto (fondo ε2 o ε3).",
               "CT": "Un alelo que define ε4 presente.",
               "CC": "Dos alelos que definen ε4 (con rs7412 C = ε4/ε4)."}},
    "rs7412": {"trait": "APOE — sitio 2 (Alzheimer y lípidos)",
        "summary": "Combínalo con rs429358 para leer ε2/ε3/ε4. El ε2 baja el LDL y el riesgo de Alzheimer.",
        "gt": {"CC": "Sin ε2 desde este punto (fondo ε3 o ε4).",
               "CT": "Un alelo que define ε2.",
               "TT": "Dos alelos que definen ε2 (ε2/ε2, con rs429358 T)."}},
    "rs9939609": {"trait": "Índice de masa corporal (FTO)",
        "summary": "SNP palindrómico (A/T): confiamos en la orientación del proveedor. Efecto por alelo pequeño y muy modificable por el estilo de vida; no es determinante.",
        "gt": {"AA": "Tendencia a un IMC algo mayor (~+3 kg vs. TT a nivel poblacional).",
               "AT": "Intermedio.",
               "TT": "Tendencia a un IMC algo menor desde este punto."}},
    "rs7903146": {"trait": "Predisposición a diabetes tipo 2 (TCF7L2)",
        "summary": "La variante común más asociada a diabetes tipo 2, pero solo es un modificador: pesan más el estilo de vida y los antecedentes familiares.",
        "gt": {"CC": "Menor riesgo desde este punto.",
               "CT": "Riesgo ~1,4× por alelo de diabetes tipo 2.",
               "TT": "El mayor riesgo de una sola variante común (~2×)."}},
    "rs16969968": {"trait": "Dependencia de la nicotina (CHRNA5)",
        "summary": "Solo relevante en personas fumadoras; asociado a cigarrillos por día y a dificultad para dejarlo.",
        "gt": {"GG": "Menor tendencia a la dependencia desde este punto.",
               "AG": "Intermedio.",
               "AA": "Mayor dependencia, consumo más intenso y más difícil de dejar."}},
    "rs9923231": {"trait": "Sensibilidad a la warfarina (dosis)",
        "summary": "La ‘-1639G>A’: la variante T indica sensibilidad y dosis más baja. Evidencia sólida, pero NUNCA ajustes dosis con datos de consumo directo.",
        "gt": {"CC": "Expresión normal de VKORC1: dosis estándar de warfarina.",
               "CT": "Mayor sensibilidad: suele necesitarse una dosis menor.",
               "TT": "Alta sensibilidad: dosis de warfarina bastante más baja."}},
    "rs1799853": {"trait": "CYP2C9*2 — metabolismo reducido de fármacos",
        "summary": "Se combina con rs1057910 (*3) y VKORC1 para la warfarina. Solo informativo.",
        "gt": {"CC": "Normal (*1) en este punto.",
               "CT": "Un alelo *2: metabolismo reducido (warfarina, AINE, fenitoína).",
               "TT": "*2/*2: metabolismo muy reducido."}},
    "rs1057910": {"trait": "CYP2C9*3 — metabolismo reducido de fármacos",
        "summary": "Forma un diplotipo de estrella con rs1799853; efecto mayor que el *2.",
        "gt": {"AA": "Normal (*1) en este punto.",
               "AC": "Un alelo *3: metabolismo bastante reducido.",
               "CC": "*3/*3: metabolizador/a pobre."}},
    "rs4244285": {"trait": "CYP2C19*2 — pérdida de función (clopidogrel)",
        "summary": "El alelo de pérdida de función más común de CYP2C19. Informativo; confírmalo clínicamente.",
        "gt": {"GG": "Función normal (*1) en este punto.",
               "AG": "Un alelo nulo *2: metabolizador/a intermedio/a.",
               "AA": "*2/*2: metabolizador/a pobre; menos activación del clopidogrel."}},
    "rs12248560": {"trait": "CYP2C19*17 — función aumentada",
        "summary": "Se interpreta junto con *2 para asignar el fenotipo de CYP2C19.",
        "gt": {"CC": "Sin *17 en este punto.",
               "CT": "Un alelo *17: metabolizador/a rápido/a.",
               "TT": "*17/*17: metabolizador/a ultrarrápido/a."}},
    "rs4149056": {"trait": "Riesgo de miopatía por estatinas (SLCO1B1 *5)",
        "summary": "Existe guía clínica (sobre todo con simvastatina), pero el resultado es orientativo: coméntalo con quien te receta.",
        "gt": {"TT": "Función normal del transportador: riesgo típico de miopatía.",
               "CT": "Función reducida: mayor riesgo de miopatía con simvastatina.",
               "CC": "Función baja: máximo riesgo de miopatía con simvastatina a dosis alta."}},
}

CATEGORIES_ES = {
    "appearance": "Rasgos físicos visibles y de gran señal: color de ojos, cabello y piel. Educativo, no clínico.",
    "taste_and_smell": "Percepción del gusto y el olfato: amargor, cilantro jabonoso, espárrago. Divertido y de bajo riesgo.",
    "diet_and_metabolism": "Respuesta a la dieta no clínica: lactosa, cafeína, rubor y metabolismo del alcohol. Tendencias, no diagnósticos.",
    "physical_performance": "Composición de fibra muscular y respuesta al ejercicio (ACTN3). Recreativo; efectos pequeños.",
    "sensory_and_reflex": "Reflejos y percepciones curiosas, como el estornudo con la luz. Nivel curiosidad.",
    "behavioral_neuro_soft": "Asociaciones de conducta muy débiles (COMT, BDNF). Solo informativo, nunca accionable.",
    "carrier_and_metabolic_health": "Variantes de portador/metabólicas (HFE, MTHFR). Con aviso de salud; solo contexto de bienestar.",
    "complex_disease_risk": "Modificadores de riesgo de enfermedades comunes (APOE, FTO, TCF7L2, CHRNA5). Una sola variante explica poco.",
    "pharmacogenomics": "Respuesta a fármacos (VKORC1, CYP2C9, CYP2C19, SLCO1B1). Real, pero nunca ajustes dosis con estos datos.",
}

DISCLAIMERS_ES = {
    "global_banner": "Solo para uso educativo y recreativo — esto NO es un dispositivo médico ni consejo médico, "
        "diagnóstico o de tratamiento. Todo se ejecuta localmente en tu equipo; tu archivo de ADN y tus resultados "
        "nunca salen de esta máquina ni se suben o guardan en ningún servidor. La genética es solo una de muchas "
        "influencias en cualquier rasgo. No tomes decisiones de salud, dieta o medicación basándote en esta app. "
        "Consulta a un profesional de salud o a genética clínica para cualquier tema médico.",
    "health_result": "RESULTADO RELACIONADO CON LA SALUD — LEE PRIMERO. Esta variante se muestra solo con fines "
        "educativos y NO es un diagnóstico. Los chips de genotipado de consumo no son de grado clínico: para variantes "
        "raras o clínicamente relevantes, cerca del 40% de los resultados de ‘riesgo’ en datos crudos son FALSOS "
        "POSITIVOS (artefactos del chip) y no se confirmarían con secuenciación clínica. La mayoría de las condiciones "
        "dependen de muchos genes y del entorno, así que una sola variante rara vez determina el resultado, y la "
        "penetrancia suele ser incompleta. NUNCA cambies medicación, dosis, suplementos ni dieta por esta pantalla. "
        "Si un resultado te preocupa, habla con un médico o con genética clínica y confírmalo en un laboratorio "
        "clínico acreditado antes de actuar.",
    "false_positive_note": "Por qué avisamos dos veces en salud: los archivos de ADN de consumo están optimizados para "
        "ancestría, no para precisión clínica. Un genotipo puede estar mal por hibridación cruzada de sondas, líos de "
        "hebra/orientación, no-llamadas leídas como llamadas o errores en variantes raras — por eso análisis "
        "independientes encuentran que ~40% de las variantes patogénicas aparentes no se confirman clínicamente. Solo "
        "mostramos variantes bien replicadas, marcamos los SNP ambiguos de hebra y aun así te lo decimos: trata "
        "cualquier resultado de salud o farmacogenómico como una HIPÓTESIS a confirmar con pruebas clínicas, nunca "
        "como un hecho.",
}

APOE_ES = {
    "trait": "Genotipo APOE ε (riesgo de Alzheimer y lípidos)",
    "summary": "El estado ε2/ε3/ε4 se lee combinando dos SNP (rs429358 + rs7412). El ε4 sube, y el ε2 baja, el "
        "riesgo medio de Alzheimer tardío y el LDL — pero es un modificador probabilístico, NO un diagnóstico: "
        "muchas personas con ε4 nunca desarrollan Alzheimer.",
    "dip": {
        "ε2/ε2": "ε2/ε2 — el menor riesgo de Alzheimer ligado a APOE (raro); puede asociarse a hiperlipoproteinemia tipo III.",
        "ε2/ε3": "ε2/ε3 — riesgo de Alzheimer por APOE por debajo del promedio.",
        "ε3/ε3": "ε3/ε3 — el genotipo más común; riesgo APOE promedio/de referencia.",
        "ε2/ε4": "ε2/ε4 — un alelo protector y uno de riesgo; en conjunto cerca del promedio.",
        "ε3/ε4": "ε3/ε4 — un alelo ε4; unas 2–3× más riesgo medio de Alzheimer tardío que ε3/ε3.",
        "ε4/ε4": "ε4/ε4 — dos alelos ε4; riesgo medio de Alzheimer tardío bastante mayor. Sigue siendo probabilístico, no determinante.",
        "ε1/ε2": "ε1/ε2 — combinación muy rara; interpretación incierta. Confírmalo clínicamente.",
        "ε1/ε4": "ε1/ε4 — combinación muy rara; interpretación incierta. Confírmalo clínicamente.",
        "ε1/ε1": "ε1/ε1 — extremadamente raro; interpretación incierta. Confírmalo clínicamente.",
    },
}

STRAND_SUMMARY_ES = (
    "Los genotipos se normalizan a la hebra directa (+) de la referencia humana y se ordenan alfabéticamente "
    "(‘AG’ y no ‘GA’) antes de comparar. Los archivos modernos (23andMe, AncestryDNA, FTDNA) ya reportan en hebra +. "
    "En SNP NO palindrómicos, una lectura antigua en hebra − se detecta y se complementa (A↔T, C↔G). Los SNP "
    "palindrómicos (A/T o C/G) no se pueden resolver por complemento: confiamos en la hebra + del proveedor y los "
    "marcamos, sin adivinar. Las no-llamadas (‘--’, ‘00’, ‘NN’, …) se descartan."
)


def apply_to_associations(data: dict) -> tuple[dict, list]:
    warn = []
    data["disclaimers"] = DISCLAIMERS_ES
    data["strand_rules_summary"] = STRAND_SUMMARY_ES
    for c in data.get("trait_categories", []):
        if c["name"] in CATEGORIES_ES:
            c["description"] = CATEGORIES_ES[c["name"]]
    for a in data["associations"]:
        es = ES.get(a["rsid"])
        if not es:
            warn.append(f"sin traducción: {a['rsid']}")
            continue
        a["trait"] = es["trait"]
        a["plain_summary"] = es["summary"]
        for gt, meta in a["genotypes"].items():
            key = "".join(sorted(gt.upper()))
            if key in es["gt"]:
                meta["effect"] = es["gt"][key]
            else:
                warn.append(f"{a['rsid']} genotipo {gt} sin traducción")
    for hap in data.get("haplotypes", []):
        if hap["id"] == "apoe_isoform":
            hap["trait"] = APOE_ES["trait"]
            hap["plain_summary"] = APOE_ES["summary"]
            for key, dip in hap["diplotypes"].items():
                name = dip.get("name")
                if name in APOE_ES["dip"]:
                    dip["effect"] = APOE_ES["dip"][name]
    return data, warn


def main() -> int:
    total_warn = []
    for path in (ASSOC, BASE):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        # _curated_base.json uses genotypes list-of-dicts? No: it uses same nested dict.
        data, warn = apply_to_associations(_normalize_base(data))
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        total_warn += [f"{path.name}: {w}" for w in warn]
        print(f"Traducido {path.name}")
    if total_warn:
        print("AVISOS:")
        for w in total_warn:
            print(" -", w)
    return 0


def _normalize_base(data: dict) -> dict:
    """_curated_base.json stores 'associations' with the same nested genotypes dict
    and 'disclaimers'/'trait_categories'/'haplotypes' — compatible as-is."""
    return data


if __name__ == "__main__":
    raise SystemExit(main())
