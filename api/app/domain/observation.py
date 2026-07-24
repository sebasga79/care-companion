"""`Observation` — contrato de observación clínica normalizada (CON-001,
spec.md §8.1, BR-006).

Cada afirmación del cuidador/paciente conserva texto original, forma
normalizada, certeza y procedencia (turno fuente) — nunca se descarta el
texto verbatim ni se colapsa a un booleano sin trazabilidad (BR-006).

`certainty` tiene cuatro valores, no tres, precisamente para separar
"el cuidador dijo explícitamente que no" (`denied`) de "nunca se preguntó,
no respondió, o el STT no capturó nada" (`not_assessed`). BR-005/FR-023 y
spec.md §11.2 son explícitos: silencio, ausencia de respuesta o error de
captura NUNCA se interpreta como negación. Un `InterviewAgent` (CON-002)
que no logre obtener una respuesta clara para un objetivo del checklist
debe producir `not_assessed`, jamás `denied`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Certainty = Literal["confirmed", "uncertain", "denied", "not_assessed"]

CERTAINTY_VALUES: frozenset[str] = frozenset({"confirmed", "uncertain", "denied", "not_assessed"})


class Observation(BaseModel):
    """spec.md §8.1 (código, etiqueta, valor, certeza, turno fuente, texto
    original, quién normalizó). `value` es opcional: para hallazgos
    binarios la propia `certainty` ya expresa confirmado/negado/incierto;
    `value` solo se usa cuando hay un dato adicional relevante (p. ej. un
    valor de temperatura reportado)."""

    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: bool | str | None = None
    certainty: Certainty
    source_turn_id: str | None = None
    original_text: str = ""
    normalized_text: str | None = None
    normalized_by: str = "interview-agent-v1"

    @model_validator(mode="after")
    def _not_assessed_never_needs_a_turn_or_text(self) -> Observation:
        """`not_assessed` es el único estado que puede carecer de texto
        original/turno fuente (p. ej. un objetivo del checklist que nunca
        se llegó a preguntar en la llamada). Cualquier otro `certainty`
        (confirmed/uncertain/denied) es una afirmación real del cuidador y
        DEBE traer el texto verbatim y el turno que la originó — de lo
        contrario no hay procedencia auditable (BR-006)."""
        if self.certainty != "not_assessed":
            if not self.original_text.strip():
                raise ValueError(
                    f"certainty={self.certainty!r} requiere original_text no vacío "
                    "(BR-006: toda afirmación conserva texto verbatim)"
                )
            if not self.source_turn_id:
                raise ValueError(
                    f"certainty={self.certainty!r} requiere source_turn_id "
                    "(procedencia auditable, BR-006)"
                )
        return self

    @staticmethod
    def not_assessed(
        *, code: str, label: str, normalized_by: str = "interview-agent-v1"
    ) -> Observation:
        """Construye la observación por defecto para un objetivo del
        checklist que la llamada nunca llegó a cubrir (silencio, corte de
        llamada, objetivo no alcanzado) — nunca se sintetiza como `denied`."""
        return Observation(
            code=code,
            label=label,
            certainty="not_assessed",
            original_text="",
            source_turn_id=None,
            normalized_by=normalized_by,
        )


__all__ = ["CERTAINTY_VALUES", "Certainty", "Observation"]
