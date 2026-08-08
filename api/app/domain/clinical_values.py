"""Normalización determinista de valores clínicos expresados en español.

Estas funciones no diagnostican. Solo convierten valores ya atribuidos a un
campo concreto (por ejemplo, ``PAIN_SEVERITY``) al vocabulario numérico o
categórico del dataset longitudinal. Mantener esta capa fuera del LLM evita
guardar ``"siete"`` donde el dataset usa ``7`` o frases no relacionadas en
campos como movilidad y sueño.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

_NUMBER_WORDS: dict[str, int] = {
    "cero": 0,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}


def normalize_spanish(text: str) -> str:
    lowered = text.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _decoded(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def parse_pain_nrs(value: Any, original_text: str = "") -> int | None:
    """Convierte una intensidad ya contextualizada a entero 0..10."""
    candidate = _decoded(value)
    if isinstance(candidate, bool):
        return None
    if isinstance(candidate, (int, float)) and 0 <= candidate <= 10:
        return int(candidate)
    text = normalize_spanish(str(candidate or original_text)).strip()
    numeric = re.search(r"(?<!\d)(10|[0-9])(?!\d)", text)
    if numeric:
        return int(numeric.group(1))
    for word, number in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return number
    return None


def parse_temperature_c(value: Any, original_text: str = "") -> float | None:
    """Extrae una temperatura fisiológicamente plausible (34..43 °C)."""
    candidate = _decoded(value)
    if isinstance(candidate, bool):
        return None
    if isinstance(candidate, (int, float)) and 34 <= candidate <= 43:
        return float(candidate)
    text = normalize_spanish(str(candidate or original_text))
    for match in re.finditer(r"(?<!\d)(\d{2}(?:[.,]\d)?)(?!\d)", text):
        number = float(match.group(1).replace(",", "."))
        if 34 <= number <= 43:
            return number
    return None


def normalize_mobility(text: str) -> str | None:
    normalized = normalize_spanish(text)
    if re.search(r"\b(no puedo|no logra|inmovil|postrad|no camina)\b", normalized):
        return "muy_limitada"
    if re.search(r"\b(limitad|dificultad|con ayuda|poco)\b", normalized):
        return "limitada"
    if re.search(r"\b(normal|bien|camino|camina|activo|activa)\b", normalized):
        return "normal"
    return None


def normalize_wound(text: str) -> str | None:
    normalized = normalize_spanish(text)
    if re.search(r"\b(pus|secrecion|supura|mal olor)\b", normalized):
        return "secrecion_o_mal_olor"
    if re.search(r"\b(roja|rojo|enrojec|inflamad|hinchad)\b", normalized):
        return "enrojecida_inflamada"
    if re.search(r"\b(normal|limpia|seca|bien)\b", normalized):
        return "normal"
    return None


def normalize_appetite(text: str) -> str | None:
    normalized = normalize_spanish(text)
    liquids_ok = bool(
        re.search(
            r"(?:\b(?:puedo|tolero|tomo)\b.*\b(?:liquidos?|bebidas?)\b|"
            r"\b(?:liquidos?|bebidas?)\b.*\b(?:normal|bien|puedo|tolero)\b)",
            normalized,
        )
    )
    cannot_eat = bool(
        re.search(r"\b(no puedo|no logro|no tolero)\s+(?:comer|alimentos?)\b", normalized)
    )
    if liquids_ok and cannot_eat:
        return "tolera_liquidos_no_alimentos"
    if cannot_eat:
        return "no_tolera_alimentos"
    if re.search(r"\b(sin apetito|no tengo apetito|apetito.*disminuid)\b", normalized):
        return "disminuido"
    if re.search(r"\b(normal|bien|como|comiendo|tolero)\b", normalized):
        return "normal"
    return None


def normalize_sleep(text: str) -> str | None:
    normalized = normalize_spanish(text)
    if re.search(r"\b(no duermo|no he dormido|insomnio|mal|interrumpid)\b", normalized):
        return "alterado"
    if re.search(r"\b(normal|bien|dormi|descans)\b", normalized):
        return "normal"
    return None


__all__ = [
    "normalize_appetite",
    "normalize_mobility",
    "normalize_sleep",
    "normalize_spanish",
    "normalize_wound",
    "parse_pain_nrs",
    "parse_temperature_c",
]
