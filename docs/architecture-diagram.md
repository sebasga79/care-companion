# Care Companion — Diagrama de arquitectura (DOC-002)

> v2.0 · 10 de agosto de 2026 · Deriva de [`architecture.md`](architecture.md).
> Renderizable en GitHub/artefactos (Mermaid). Muestra el sistema **tal como
> corre hoy**, no la propuesta previa al kit.

Reconstruido sobre v1.0 (24 de julio, previo al kit oficial): esa versión
mostraba un LLM simulado y `ChallengeCasePort → Fixture (Delta Share en T0)`.
Ninguno es seleccionable en el runtime actual (los dobles permanecen solo en
tests); nunca hubo Delta Share y el kit real trae `.xlsx` + PDFs. Con la
rúbrica evaluando el diagrama tomando piezas al azar y buscándolas en el
código (criterio "Comprensión del problema y diseño de la conversación"),
un diagrama desalineado con el repositorio es peor que no tenerlo. Esta
versión refleja los adapters reales, agrega la ruta de auditoría/métricas
(inexistente en v1.0) y el detector de seguridad determinista.

## 1. Sistema

```mermaid
flowchart TB
    subgraph Browser["Navegador (Next.js / React)"]
        CALL["/call\n40 pacientes · 160 episodios históricos"]
        KNOW["/knowledge\nconocimiento vivo + llamada de prueba"]
        AUDIT["/audit\ntraza, decisiones y métricas rúbrica §5"]
        MODAL["CallModal\ncompartido por /call y /knowledge"]
        VOICE["useVoiceSession\nSTT+TTS del navegador · half-duplex\nbarge-in ≤250ms · mide latencia voz-a-voz real"]
    end

    subgraph API["Backend FastAPI (monolito modular)"]
        REST["REST /api/v1\ncases · sessions · knowledge · audit · metrics"]
        WS["WebSocket /ws/sessions/{id}\nenvelopes versionados + seq"]
        ORCH["CallCycleOrchestrator\nmáquina de estados tipada"]
        subgraph AGENTS["Agentes de responsabilidad única\n(nunca se llaman entre sí)"]
            INT["InterviewAgent"]
            TRI["TriageAgent"]
            RES["ResponseAgent"]
        end
        RULES["RuleEngine\nred flags deterministas · rules-v2"]
        SAFETY["SafetySignalDetector\nred de seguridad sobre texto crudo\ncon precedencia sobre el LLM"]
        REDUCE["reduce_decision\nprecedencia no degradable"]
        RAGSVC["RAG híbrido\nFTS5 + coseno + RRF + evidence gate"]
        SUM["SummaryBuilder\nCallSummary v1.2"]
        AUDITREPO["AuditRepository\nlatency_percentiles · voice_latency_percentiles\nusage_summary por proveedor · trace"]
    end

    subgraph PORTS["Puertos / adaptadores"]
        LLM["LLMPort\nOpenAICompatLLM → Groq llama-3.3-70b-versatile\nenvuelto en FallbackLLM → Ollama llama3.2:3b"]
        EMB["EmbeddingsPort\nLocalHashEmbeddings (arranque reproducible)\no OpenAICompatEmbeddings → Ollama BGE-M3"]
        CASE["ChallengeCasePort\nCombinedCaseAdapter =\nDatasetCaseAdapter (160 episodios/40 pacientes sintéticos del kit)\n+ FixtureCaseAdapter (4 casos sintéticos de prueba)"]
    end

    DB[("SQLite WAL\nsessions·turns·events·documents·chunks\ncitations·observations·decisions\nescalations·followup_records")]

    CALL --> MODAL
    KNOW --> MODAL
    MODAL <-->|"REST"| REST
    MODAL <-->|"WS"| WS
    VOICE --> MODAL
    VOICE -.->|"POST voice-latency, fire-and-forget"| REST
    AUDIT --> REST

    WS --> ORCH
    ORCH --> INT --> ORCH
    ORCH --> RULES
    ORCH --> SAFETY
    ORCH --> RAGSVC
    ORCH --> TRI --> ORCH
    ORCH --> REDUCE
    ORCH --> RES --> ORCH
    ORCH --> SUM
    RULES --> REDUCE
    SAFETY --> REDUCE
    TRI --> REDUCE

    INT -.-> LLM
    TRI -.-> LLM
    RES -.-> LLM
    RAGSVC -.-> EMB
    REST -.-> CASE
    ORCH --> DB
    RAGSVC --> DB
    REST --> AUDITREPO --> DB
```

Regla estructural: **los agentes nunca se llaman entre sí**; solo el
orquestador coordina. El dominio no importa SDKs — todo proveedor entra por
un puerto, incluido el resguardo (`FallbackLLM` decide sin que el dominio lo
sepa). `AuditRepository` separa tokens por proveedor real de cada llamada
(`by_provider`) para no cobrar precio de Groq por una llamada que en
realidad sirvió gratis el resguardo local.

## 2. Flujo de decisión (no degradable)

```mermaid
flowchart TD
    TURN["Turno del paciente\n(voz o texto)"] --> OBS["InterviewAgent\n→ observaciones estructuradas"]
    OBS --> RE["RuleEngine determinista\n(rules-v2)"]
    OBS --> SAFE["SafetySignalDetector\n(texto crudo, precedencia sobre el LLM)"]
    OBS --> RET["Retrieval + evidence gate"]
    RE --> RF{"¿Red flag\ndeterminista?"}
    SAFE --> RF
    RET --> EV{"¿Evidencia\nsuficiente?"}
    RF -->|"Sí"| HARD["HARD_RED_FLAG"]
    EV -->|"No, con riesgo"| INSUF["EVIDENCE_INSUFFICIENT_WITH_RISK"]
    RF -->|"No"| TRI["TriageAgent\n(evaluación del modelo)"]
    TRI --> ML["MODEL_HIGH / MODERATE / ROUTINE"]

    HARD --> REDUCE["reduce_decision\nprecedencia:\nHARD_RED_FLAG >\nDATA_INTEGRITY_FAILURE >\nEVIDENCE_INSUFFICIENT_WITH_RISK >\nMODEL_HIGH > MODEL_MODERATE >\nROUTINE"]
    INSUF --> REDUCE
    ML --> REDUCE

    REDUCE --> ESC{"¿Escala?"}
    ESC -->|"Sí"| HANDOFF["Escalamiento idempotente\n+ respuesta que abstiene/deriva\n(safe-handoff-v1, determinista, sin LLM)"]
    ESC -->|"No"| ANSWER["ResponseAgent\nsolo afirma con evidencia citada"]
    HANDOFF --> SUMMARY["CallSummary v1.2\nreportado/negado/no evaluado + citas"]
    ANSWER --> SUMMARY

    FAIL["Fallo de modelo/RAG/persistencia\ncon riesgo"] -.->|"fail-safe"| REDUCE
```

Invariante clínica: **la salida del modelo nunca rebaja** un nivel producido
por una regla determinista; silencio/dato ausente no es negación; sin
evidencia activa no hay afirmación clínica.
