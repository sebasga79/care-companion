"""Detector determinista de señales de alarma sobre el TEXTO CRUDO del
paciente (SAFE-001 ampliado — defensa en profundidad).

## Por qué existe

Hasta ahora, toda la seguridad clínica del sistema dependía de que el
`InterviewAgent` (un LLM) extrajera correctamente las observaciones: el
motor de reglas determinista (`app/services/rule_engine.py`) sólo ve
`Observation` ya normalizadas por el modelo. Si el modelo no extraía
"fiebre confirmada", las reglas nunca se enteraban y el sistema respondía
"todo dentro de lo esperado".

Eso se observó en vivo, y es la falla más grave posible según la rúbrica
del reto: un paciente dijo *"tengo 40 grados de fiebre"*, *"me está
doliendo mucho el estómago"*, *"creo que tengo que volver a ser
hospitalizado"* y el agente respondió que todo estaba normal. La rúbrica lo
nombra textualmente como **alucinación clínica peligrosa** ("tranquilizar
al paciente ante un síntoma de alarma") y **falso negativo catastrófico**.

Este módulo es la red que no depende del modelo: lógica pura sobre el texto
literal del paciente, sin LLM, sin red, determinista y auditable. Si el
modelo falla, esto sigue disparando. Las observaciones que produce se
combinan con las del `InterviewAgent` con **precedencia de seguridad**:
una señal detectada aquí nunca puede ser rebajada por el modelo
(spec.md §11, "el LLM nunca rebaja una alerta determinista").

## Alcance y límites (declarados, no implícitos)

Es un detector léxico, no un modelo de comprensión: reconoce las formas más
frecuentes en español colombiano de reportar un puñado de señales críticas.
**No pretende cobertura completa** — su propósito es que las señales más
claras y peligrosas nunca dependan del LLM, no reemplazar la extracción
matizada del agente. Un caso que este detector no reconoce sigue pasando
por el camino normal (`InterviewAgent` + reglas).

Sesgo deliberado hacia el falso positivo: ante duda, dispara. La rúbrica
del reto es explícita en que el falso negativo (no alertar cuando había que
alertar) es la falla catastrófica, y pesa más que el falso positivo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.clinical_values import normalize_spanish, parse_pain_nrs
from app.domain.observation import Observation
from app.ports.challenge_case import HistoricalFollowup

DETECTOR_VERSION = "safety-signal-detector-v1"

# Umbral respaldado por el corpus oficial: guías de apendicectomía,
# colecistectomía, cirugía intestinal y reemplazo articular indican
# temperatura *mayor/superior* a 38 °C como signo de alarma. El comparador
# es estricto (`>`), no `>=`, para conservar literalmente ese alcance.
FEVER_CELSIUS_THRESHOLD = 38.0

# Marcadores de negación. Se buscan en una ventana ANTES del término
# detectado — sin esto, "no tengo fiebre" dispararía FEVER, que sería peor
# que no tener detector (spec.md §11: un dato negado explícitamente no es
# una alarma).
_NEGATION_MARKERS: tuple[str, ...] = (
    "no",
    "nunca",
    "ninguna",
    "ningun",
    "sin",
    "tampoco",
    "nada de",
    "ya no",
    "cero",
)
# Ventana (en palabras) hacia atrás donde una negación sigue aplicando.
_NEGATION_WINDOW_WORDS = 4
# Conectores que CORTAN el alcance de una negación: en "no he comido pero
# tengo fiebre", el "no" no niega la fiebre.
_NEGATION_BREAKERS: frozenset[str] = frozenset({"pero", "aunque", "sino", "mas", "y"})

# Formas frecuentes de aclarar que un síntoma ya terminó. Se inspeccionan
# después de la mención porque "tuve fiebre, pero ya no" no tiene una
# negación delante de "fiebre" y, sin esta defensa, quedaría confirmada.
_RESOLUTION_AFTER_RE = re.compile(
    r"^(?:\W|\w+\W){0,4}(?:pero\s+)?(?:ya\s+no|se\s+me\s+quito|ya\s+se\s+fue|me\s+paso)\b"
)

# El paciente PREGUNTA o declara no saber, no reporta un síntoma.
#
# Falso positivo real visto en `/call`: ante "no sé, usted dígame porque no
# me acuerdo cómo estaba… quiero que me diga si sigue igual o mejorado o
# EMPEORADO", el detector confirmó `PAIN_WORSENING` y la llamada escaló a
# urgencia. El paciente no había reportado empeoramiento: estaba pidiendo
# que le recordaran su propia línea base, y la palabra aparecía dentro de
# una enumeración de alternativas.
#
# La rúbrica pesa más el falso negativo, y por eso este módulo sesga hacia
# confirmar; pero escalar porque alguien PRONUNCIÓ la palabra dentro de una
# pregunta no es sesgo prudente, es no distinguir quién afirma qué. Esas
# ocurrencias no se toman como reporte — si además hay una señal real en la
# misma frase ("no sé qué hacer, estoy sangrando"), esa se detecta por su
# propio patrón y sigue disparando.
_QUERY_MARKER_WINDOW_WORDS = 12
_QUERY_MARKERS: tuple[str, ...] = (
    "digame",
    "dime",
    "digamelo",
    "me dice",
    "me diga",
    "me digas",
    "me puede decir",
    "usted sabe",
    "usted dice",
    "no me acuerdo",
    "no recuerdo",
    "que me diga",
    "que me digas",
    "que me cuente",
)
# NO se incluye "quiero que me" a secas: suprimía "quiero que me
# HOSPITALICEN ya", que es una petición de auxilio, no una pregunta. Los
# marcadores deben nombrar el acto de *pedir información* (decir, contar),
# nunca el de pedir atención.
# "no sé" NO entra: es demasiado ambiguo. Suprimía la señal real en
# "no sé qué hacer, estoy sangrando mucho" — un falso negativo, que es
# justo lo que la rúbrica marca como falla catastrófica. Sólo se suprime
# ante una petición explícita de información ("dígame", "no me acuerdo").
# Enumeración de alternativas: "…si sigue igual o mejorado o empeorado".
# Si junto al término aparece su contrario, es un menú de opciones, no un
# reporte.
_ALTERNATIVE_CONTRAST = ("mejor", "igual", "peor")


@dataclass(frozen=True)
class SafetySignal:
    """Una señal de alarma reconocible en el habla del paciente."""

    code: str
    label: str
    patterns: tuple[str, ...]


SAFETY_SIGNALS: tuple[SafetySignal, ...] = (
    SafetySignal(
        code="FEVER",
        label="fiebre o sensación de calor corporal",
        patterns=(
            r"\bfiebre\b",
            r"\bcalentura\b",
            r"\bfebril\b",
            r"\btemperatura alta\b",
            r"\bdestemplad[oa]\b",
            r"\bescalofrios?\b",
        ),
    ),
    SafetySignal(
        code="PAIN_SEVERE",
        label="dolor fuerte que requiere caracterización",
        patterns=(
            r"\bdolor (?:muy )?(?:fuerte|intenso|severo)\b",
            r"\bme duele (?:mucho|muchisimo|demasiado|horrible)\b",
            r"\bduele (?:mucho|muchisimo|demasiado)\b",
            r"\bdolor persistente\b",
            r"\bsiento (?:mucho|muchisimo|demasiado) dolor\b",
            r"\btodavia siento (?:mucho |demasiado )?dolor\b",
        ),
    ),
    SafetySignal(
        code="PAIN_WORSENING",
        label="dolor que empeora, no cede o es insoportable",
        patterns=(
            r"\bdolor (?:muy )?insoportable\b",
            r"\bdolor (?:no cede|no se quita|no para)\b",
            r"\bcada vez (?:mas|peor)\b",
            r"\bno (?:aguanto|soporto) el dolor\b",
            r"\bempeor\w*\b",
            r"\bpeor que (?:ayer|antes)\b",
        ),
    ),
    SafetySignal(
        code="WOUND_DISCHARGE",
        label="secreción o mal aspecto de la herida",
        patterns=(
            r"\bpus\b",
            r"\bsupura\w*\b",
            r"\bsecrecion\w*\b",
            r"\bmal olor\b",
            r"\bhuele (?:mal|feo)\b",
            r"\bherida (?:abierta|roja|inflamada|hinchada)\b",
            r"\bse (?:abrio|abrio) la herida\b",
        ),
    ),
    SafetySignal(
        code="WOUND_INFLAMMATION",
        label="enrojecimiento o inflamación de la herida",
        patterns=(
            r"\bherida\b.{0,35}\b(?:roja|rojo|enrojecida|inflamada|hinchada)\b",
            r"\b(?:esta|se ve)\s+(?:muy\s+|un poco\s+)?"
            r"(?:roja|rojo|enrojecida|inflamada|hinchada)\b",
            r"\b(?:roja|rojo|enrojecida)\b.{0,25}\b(?:inflamada|hinchada)\b",
        ),
    ),
    SafetySignal(
        code="BLEEDING",
        label="sangrado",
        patterns=(
            r"\bsangr\w+\b",
            r"\bhemorragia\b",
            r"\bboto sangre\b",
            r"\bmucha sangre\b",
        ),
    ),
    SafetySignal(
        code="BREATHING_DIFFICULTY",
        label="dificultad para respirar",
        patterns=(
            r"\bno puedo respirar\b",
            r"\bme (?:ahogo|falta el aire)\b",
            r"\bdificultad para respirar\b",
            r"\bahogad[oa]\b",
            r"\bagitad[oa]\b",
        ),
    ),
    SafetySignal(
        code="ALTERED_CONSCIOUSNESS",
        label="desmayo, pérdida de conciencia o confusión",
        patterns=(
            r"\bme (?:desmaye|desmayo|voy a desmayar)\b",
            r"\bperdi (?:el )?conocimiento\b",
            r"\b(?:estoy|me siento) confundid[oa]\b",
            r"\bno puedo mantenerme despiert[oa]\b",
            r"\b(?:esta|estoy) inconsciente\b",
        ),
    ),
    SafetySignal(
        code="EMERGENCY_CONCERN",
        label="el paciente pide atención urgente o teme por su vida",
        patterns=(
            # hospitalizar -> hospitalice/hospitalicen cambia z por c.
            r"\bhospital(?:iz|ic)\w*\b",
            r"\b(?:ir|llevenme|lleveme|volver)\s+(?:al|a el)\s+hospital\b",
            r"\burgencias?\b",
            r"\bemergencia\b",
            r"\bme voy a morir\b",
            r"\bme estoy muriendo\b",
            r"\bes grave\b",
            r"\bambulancia\b",
        ),
    ),
    SafetySignal(
        code="VOMITING",
        label="vómito persistente",
        patterns=(
            r"\bvomit\w+\b",
            r"\bdevuelvo todo\b",
            r"\btodo lo (?:vomito|devuelvo)\b",
        ),
    ),
    SafetySignal(
        code="ORAL_INTAKE_INTOLERANCE",
        label="intolerancia a alimentos o líquidos",
        patterns=(
            r"\bno (?:puedo|logro|tolero) (?:comer|tomar|tragar)\b",
            r"\bno me pasa (?:la comida|el alimento|el agua)\b",
            r"\bno tolero (?:los )?(?:alimentos|liquidos)\b",
        ),
    ),
)

_TEMPERATURE_RE = re.compile(
    r"(?P<value>\d{2}(?:[.,]\d)?)\s*(?:°|º)?\s*(?:c\b|grados?\b|celsius\b)", re.IGNORECASE
)
_FEVER_VALUE_RE = re.compile(
    r"\b(?:fiebre|temperatura)(?:\s+(?:de|en))?\s+(?P<value>\d{2}(?:[.,]\d)?)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Minúsculas y sin tildes — el habla transcrita llega con y sin ellas
    de forma inconsistente ("fiebre"/"fiebré", "dolía"/"dolia")."""
    return normalize_spanish(text)


_UNSPECIFIED_DISTRESS_RE = re.compile(
    r"^(?:(?:me siento|estoy|sigo)\s+)?"
    r"(?:(?:muy|bastante|realmente)\s+)?"
    r"(?:mal|pesimo|terrible|maluco)"
    r"(?:\s+de verdad)?[\s.!¡¿?]*$"
)


def is_unspecified_severe_distress(patient_text: str) -> bool:
    """Detecta malestar intenso declarado sin un síntoma concreto.

    "Muy mal" merece un tamizaje urgente, pero no equivale por sí solo a
    pedir una ambulancia, reportar un signo de alarma ni temer por la vida.
    El `fullmatch` es deliberado: si la misma frase incluye una señal
    concreta (p. ej. "muy mal, no puedo respirar"), esa señal sigue por el
    detector y las reglas no degradables normales.
    """
    return bool(_UNSPECIFIED_DISTRESS_RE.fullmatch(_normalize(patient_text).strip()))


def _is_negated(normalized_text: str, match_start: int) -> bool:
    """Busca un marcador de negación en las palabras inmediatamente
    anteriores al término detectado, cortando en conectores adversativos
    ("no me duele la herida PERO tengo fiebre" no niega la fiebre)."""
    preceding = [word.strip(".,;:¡!¿?()") for word in normalized_text[:match_start].split()]
    window = preceding[-_NEGATION_WINDOW_WORDS:]
    for index in range(len(window) - 1, -1, -1):
        word = window[index]
        if word in _NEGATION_BREAKERS:
            return False
        suffix = " ".join(window[index:])
        if any(suffix.startswith(marker) for marker in _NEGATION_MARKERS):
            return True
    return False


def _is_resolved_after(normalized_text: str, match_end: int) -> bool:
    """Reconoce aclaraciones cercanas que hacen histórico el síntoma."""
    return _RESOLUTION_AFTER_RE.search(normalized_text[match_end:]) is not None


def _is_query_not_report(normalized_text: str, match_start: int, match_end: int) -> bool:
    """`True` si el término aparece porque el paciente PREGUNTA o enumera
    opciones, no porque reporte el síntoma. Ver `_QUERY_MARKERS`."""
    preceding = normalized_text[:match_start]
    window = " ".join(preceding.split()[-_QUERY_MARKER_WINDOW_WORDS:])
    if any(marker in window for marker in _QUERY_MARKERS):
        return True

    # Enumeración de alternativas: el contrario aparece muy cerca, unido por
    # "o" ("sigue igual o mejorado o empeorado").
    tail = " ".join(preceding.split()[-6:])
    if " o " in f" {tail} " and any(word in tail for word in _ALTERNATIVE_CONTRAST):
        return True
    following = " ".join(normalized_text[match_end:].split()[:6])
    return " o " in f" {following} " and any(w in following for w in _ALTERNATIVE_CONTRAST)


def _detect_reported_temperature(normalized_text: str) -> float | None:
    """Devuelve la temperatura más alta reportada de forma plausible.

    Filtra números fuera del rango fisiológico (un "40" suelto puede ser una
    edad o una dosis; sólo se acepta como temperatura si el patrón incluye
    grados/°C explícitos y cae en un rango humano posible)."""
    best: float | None = None
    matches = [
        *_TEMPERATURE_RE.finditer(normalized_text),
        *_FEVER_VALUE_RE.finditer(normalized_text),
    ]
    for match in matches:
        if _is_negated(normalized_text, match.start()) or _is_resolved_after(
            normalized_text, match.end()
        ):
            continue
        raw = match.group("value").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            continue
        if not (34.0 <= value <= 43.0):
            continue
        if best is None or value > best:
            best = value
    return best


def derive_longitudinal_safety_signals(
    observations: list[Observation],
    historical_followups: list[HistoricalFollowup],
    *,
    source_turn_id: str,
) -> list[Observation]:
    """Deriva señales auditables a partir del valor actual y el último hito.

    Solo opera sobre observaciones ya confirmadas. No convierte una frase
    ambigua en síntoma; su función es normalizar un dolor 0..10 y hacer
    explícita la diferencia frente al último seguimiento conocido.
    """
    latest_by_code: dict[str, Observation] = {}
    for observation in observations:
        latest_by_code[observation.code] = observation

    severity = latest_by_code.get("PAIN_SEVERITY")
    if severity is None or severity.certainty != "confirmed":
        return []
    pain_nrs = parse_pain_nrs(severity.value, severity.original_text)
    if pain_nrs is None:
        return []

    derived: list[Observation] = []
    if pain_nrs >= 7:
        derived.append(
            Observation(
                code="PAIN_SEVERE",
                label="dolor actual de intensidad alta",
                value=pain_nrs,
                certainty="confirmed",
                source_turn_id=severity.source_turn_id or source_turn_id,
                original_text=severity.original_text,
                normalized_text=f"dolor_nrs={pain_nrs}",
                normalized_by="longitudinal-safety-v1",
            )
        )

    if historical_followups:
        previous = max(historical_followups, key=lambda item: item.day)
        if pain_nrs - previous.pain_nrs >= 3:
            derived.append(
                Observation(
                    code="PAIN_HISTORY_DETERIORATION",
                    label="aumento del dolor respecto al último seguimiento",
                    value=f"{previous.pain_nrs}->{pain_nrs}",
                    certainty="confirmed",
                    source_turn_id=severity.source_turn_id or source_turn_id,
                    original_text=severity.original_text,
                    normalized_text=(
                        f"último seguimiento día {previous.day}: dolor_nrs={previous.pain_nrs}; "
                        f"actual={pain_nrs}"
                    ),
                    normalized_by="longitudinal-safety-v1",
                )
            )
    return derived


def detect_safety_signals(patient_text: str, *, source_turn_id: str) -> list[Observation]:
    """Analiza el texto literal del paciente y devuelve observaciones
    `confirmed`/`denied` para las señales reconocidas.

    No produce `not_assessed`: lo que este detector no reconoce simplemente
    no se reporta (el `InterviewAgent` sigue siendo el responsable de cubrir
    el checklist completo). `denied` sólo se emite cuando el paciente negó
    explícitamente la señal — nunca por ausencia (spec.md §11.2: silencio
    nunca equivale a negación)."""
    if not patient_text or not patient_text.strip():
        return []

    normalized = _normalize(patient_text)
    observations: list[Observation] = []

    reported_temperature = _detect_reported_temperature(normalized)

    for signal in SAFETY_SIGNALS:
        confirmed = False
        denied = False
        for pattern in signal.patterns:
            for match in re.finditer(pattern, normalized):
                # El paciente pregunta o enumera opciones: no es un reporte,
                # ni confirmado ni negado — simplemente no dice nada sobre el
                # síntoma. Marcarlo `denied` sería tan incorrecto como
                # `confirmed` (spec.md §11.2: no inferir negación).
                if _is_query_not_report(normalized, match.start(), match.end()):
                    continue
                # Hay patrones cuya propia frase es una negación: "no puedo
                # respirar", "no puedo comer". Aplicarles el chequeo de
                # negación previa los invertía — "no sé, no puedo respirar"
                # quedaba como `denied`, un falso negativo en una señal de
                # urgencia. La negación ya forma parte del síntoma.
                matched_text = match.group(0)
                intrinsic_negation = matched_text.startswith("no ")
                if not intrinsic_negation and (
                    _is_negated(normalized, match.start())
                    or _is_resolved_after(normalized, match.end())
                ):
                    denied = True
                else:
                    confirmed = True
                    break
            if confirmed:
                break

        # La temperatura numérica manda sobre la mención léxica: "tengo 40
        # grados" confirma fiebre aunque nunca diga la palabra "fiebre";
        # "tengo 36.5" la descarta aunque la mencione. En el límite exacto
        # de 38 °C se conserva una mención explícita de fiebre como FEVER,
        # pero no se crea HIGH_FEVER (el corpus oficial usa > 38 °C).
        if signal.code == "FEVER" and reported_temperature is not None:
            if reported_temperature > FEVER_CELSIUS_THRESHOLD:
                confirmed = True
                denied = False
            elif reported_temperature < FEVER_CELSIUS_THRESHOLD:
                confirmed = False
                denied = True
            elif not confirmed:
                # Un valor aislado de 38 °C no supera el umbral de alarma.
                # Si además dijo explícitamente "fiebre", esa observación
                # léxica sí se conserva como confirmada para no contradecirlo.
                denied = True

        if not confirmed and not denied:
            continue

        value: bool | str | None = None
        if signal.code == "FEVER" and reported_temperature is not None:
            value = f"{reported_temperature:.1f} °C (reportado por el paciente)"

        observations.append(
            Observation(
                code=signal.code,
                label=signal.label,
                value=value,
                certainty="confirmed" if confirmed else "denied",
                source_turn_id=source_turn_id,
                original_text=patient_text.strip(),
                normalized_by=DETECTOR_VERSION,
            )
        )

    # Se conserva FEVER para el checklist y las reglas existentes, pero la
    # temperatura numérica de alarma recibe además un código separado. Así
    # "tengo fiebre" no se convierte automáticamente en HARD_RED_FLAG sin
    # conocer el valor, mientras que "tengo 40 grados" sí queda protegido
    # por una regla inequívoca y no degradable.
    if reported_temperature is not None and reported_temperature > FEVER_CELSIUS_THRESHOLD:
        observations.append(
            Observation(
                code="HIGH_FEVER",
                label="temperatura reportada superior a 38 °C",
                value=f"{reported_temperature:.1f} °C (reportado por el paciente)",
                certainty="confirmed",
                source_turn_id=source_turn_id,
                original_text=patient_text.strip(),
                normalized_by=DETECTOR_VERSION,
            )
        )

    return observations


def merge_with_safety_precedence(
    agent_observations: list[Observation],
    safety_observations: list[Observation],
) -> list[Observation]:
    """Combina las observaciones del `InterviewAgent` con las del detector
    determinista, dando **precedencia al detector cuando éste confirma** una
    señal.

    Regla (spec.md §11, BR-020): el modelo nunca puede rebajar una alerta
    determinista. Si el detector confirmó `FEVER` y el modelo dijo
    `denied`/`not_assessed`/`uncertain` para el mismo código, gana el
    detector. En cambio, si el detector sólo `denied` (el paciente negó
    explícitamente) y el modelo confirmó, gana el **modelo**: el modelo
    entiende contexto que un detector léxico no, y confirmar es el lado
    seguro."""
    merged: dict[str, Observation] = {obs.code: obs for obs in agent_observations}

    for safety_obs in safety_observations:
        existing = merged.get(safety_obs.code)
        if safety_obs.certainty == "confirmed":
            merged[safety_obs.code] = safety_obs
        elif existing is None or existing.certainty == "not_assessed":
            merged[safety_obs.code] = safety_obs

    return list(merged.values())


__all__ = [
    "DETECTOR_VERSION",
    "FEVER_CELSIUS_THRESHOLD",
    "SAFETY_SIGNALS",
    "SafetySignal",
    "detect_safety_signals",
    "derive_longitudinal_safety_signals",
    "is_unspecified_severe_distress",
    "merge_with_safety_precedence",
]
