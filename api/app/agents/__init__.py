"""Agentes de responsabilidad única (architecture.md §6).

Cada módulo de este paquete define una clase que acepta `AgentRequest` y
devuelve `AgentResult` (contratos en `app.domain.models`). Ningún agente
importa ni instancia a otro agente — el `CallCycleOrchestrator`
(`app.orchestrator.call_cycle`) es el único coordinador (architecture.md
§6.2: "cero llamadas entre agentes")."""

from __future__ import annotations
