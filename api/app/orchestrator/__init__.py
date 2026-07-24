"""`CallCycleOrchestrator` (ORC-002, architecture.md §6.1/§7).

Único módulo del proyecto que coordina agentes entre sí. Ningún agente
(`app.agents.*`) importa a otro agente ni al orquestador — la dependencia
va siempre en un solo sentido: `orchestrator -> agents`. Ver
`app.orchestrator.call_cycle` para la implementación."""

from __future__ import annotations
