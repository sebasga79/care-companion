# Care Companion — Diagrama de arquitectura (DOC-002)

> v1.0 · 24 de julio de 2026 · Deriva de `architecture.md`. Renderizable en
> GitHub/artefactos (Mermaid). Muestra el sistema y el flujo de decisión.

## 1. Sistema

```mermaid
flowchart TB
    subgraph Browser["Navegador (Next.js / React)"]
        CALL["/call\nllamada en vivo"]
        KNOW["/knowledge\nconocimiento vivo"]
        AUDIT["/audit\ntraza y métricas"]
        VOICE["useVoiceSession\nSTT+TTS navegador · barge-in"]
    end

    subgraph API["Backend FastAPI (monolito modular)"]
        REST["REST /api/v1\ncases · sessions · knowledge · audit · metrics"]
        WS["WebSocket /ws/sessions/{id}\nenvelopes versionados"]
        ORCH["CallOrchestrator\nmáquina de estados tipada"]
        subgraph AGENTS["Agentes (responsabilidad única)"]
            INT["InterviewAgent"]
            TRI["TriageAgent"]
            RES["ResponseAgent"]
        end
        RULES["RuleEngine\ndeterminista · red flags"]
        REDUCE["reduce_decision\nprecedencia no degradable"]
        RAG["RAG híbrido\nFTS5 + coseno + RRF + evidence gate"]
        SUM["SummaryBuilder"]
    end

    subgraph PORTS["Puertos / adaptadores (ADR-001)"]
        LLM["LLMPort → FakeLLM\n(modelo obligatorio en T0)"]
        EMB["EmbeddingsPort → Fake"]
        CASE["ChallengeCasePort → Fixture\n(Delta Share en T0)"]
    end

    DB[("SQLite WAL\nsessions · turns · events\ndocuments · chunks · citations\nobservations · decisions · escalations")]

    CALL <-->|"JWT/HTTP + WS"| REST
    CALL <--> WS
    VOICE --> CALL
    KNOW --> REST
    AUDIT --> REST

    WS --> ORCH
    ORCH --> INT --> ORCH
    ORCH --> RULES
    ORCH --> RAG
    ORCH --> TRI --> ORCH
    ORCH --> REDUCE
    ORCH --> RES --> ORCH
    ORCH --> SUM
    RULES --> REDUCE
    TRI --> REDUCE

    INT -.-> LLM
    TRI -.-> LLM
    RES -.-> LLM
    RAG -.-> EMB
    REST -.-> CASE
    ORCH --> DB
    RAG --> DB
```

Regla estructural: **los agentes nunca se llaman entre sí**; solo el
orquestador coordina. El dominio no importa SDKs — todo proveedor entra por un
puerto.

## 2. Flujo de decisión (no degradable)

```mermaid
flowchart TD
    TURN["Turno del paciente\n(voz o texto)"] --> OBS["InterviewAgent\n→ observaciones estructuradas"]
    OBS --> RE["RuleEngine determinista"]
    OBS --> RET["Retrieval + evidence gate"]
    RE --> RF{"¿Red flag\ndeterminista?"}
    RET --> EV{"¿Evidencia\nsuficiente?"}
    RF -->|"Sí"| HARD["HARD_RED_FLAG"]
    EV -->|"No, con riesgo"| INSUF["EVIDENCE_INSUFFICIENT_WITH_RISK"]
    RF -->|"No"| TRI["TriageAgent\n(evaluación del modelo)"]
    TRI --> ML["MODEL_HIGH / MODERATE / ROUTINE"]

    HARD --> REDUCE["reduce_decision\nprecedencia:\nHARD_RED_FLAG >\nDATA_INTEGRITY_FAILURE >\nEVIDENCE_INSUFFICIENT_WITH_RISK >\nMODEL_HIGH > MODEL_MODERATE >\nROUTINE"]
    INSUF --> REDUCE
    ML --> REDUCE

    REDUCE --> ESC{"¿Escala?"}
    ESC -->|"Sí"| HANDOFF["Escalamiento idempotente\n+ respuesta que abstiene/deriva"]
    ESC -->|"No"| ANSWER["ResponseAgent\nsolo afirma con evidencia citada"]
    HANDOFF --> SUMMARY["CallSummary\nreportado/negado/no evaluado + citas"]
    ANSWER --> SUMMARY

    FAIL["Fallo de modelo/RAG/persistencia\ncon riesgo"] -.->|"fail-safe"| REDUCE
```

Invariante clínica: **la salida del modelo nunca rebaja** un nivel producido
por una regla determinista; silencio/dato ausente no es negación; sin evidencia
activa no hay afirmación clínica.
