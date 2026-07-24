"use client";

import { useState, type CSSProperties } from "react";

type ActiveTab = "call" | "knowledge" | "audit";

const waveform = [
  10, 18, 28, 44, 66, 34, 20, 54, 76, 42, 24, 16, 38, 62, 82, 48, 24, 36,
  72, 56, 30, 18, 44, 68, 86, 58, 32, 22, 48, 74, 54, 30, 18, 42, 64, 78,
  46, 28, 16,
];

const tabs: Array<{ id: ActiveTab; label: string }> = [
  { id: "call", label: "Llamada" },
  { id: "knowledge", label: "Conocimiento" },
  { id: "audit", label: "Auditoría" },
];

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("call");
  const [listening, setListening] = useState(true);
  const [alerted, setAlerted] = useState(false);
  const [guideLoaded, setGuideLoaded] = useState(false);
  const [forgetVerified, setForgetVerified] = useState(false);
  const [packageReady, setPackageReady] = useState(false);

  const toggleGuide = () => {
    if (guideLoaded) {
      setGuideLoaded(false);
      setForgetVerified(true);
      return;
    }

    setGuideLoaded(true);
    setForgetVerified(false);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <button
          className="brand brand-button"
          type="button"
          onClick={() => setActiveTab("call")}
          aria-label="Ir a la llamada de Care Companion"
        >
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
          </span>
          <span>Care Companion</span>
        </button>

        <span className="prototype-badge">Prototipo clínico</span>

        <nav className="primary-nav" aria-label="Navegación principal">
          {tabs.map((tab) => (
            <button
              className={`nav-item ${activeTab === tab.id ? "active" : ""}`}
              type="button"
              key={tab.id}
              aria-pressed={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="supervision">
          <span className="supervision-avatar" aria-hidden="true">
            AM
            <i />
          </span>
          <span>
            <strong>Supervisión activa</strong>
            <small>Equipo posoperatorio</small>
          </span>
        </div>
      </header>

      <div className="page-wrap" id="main-content">
        <section className="context-strip" aria-label="Contexto del caso">
          <div className="context-item">
            <span className="context-icon gold" aria-hidden="true">
              ✓
            </span>
            <span>
              <small>Tipo de llamada</small>
              <strong>Seguimiento posoperatorio</strong>
            </span>
          </div>
          <span className="context-divider" aria-hidden="true" />
          <div className="context-item">
            <span className="context-icon blue" aria-hidden="true">
              V
            </span>
            <span>
              <small>Paciente ficticia</small>
              <strong>Valentina R.</strong>
            </span>
          </div>
          <span className="context-divider" aria-hidden="true" />
          <div className="context-item">
            <span className="context-icon aqua" aria-hidden="true">
              +
            </span>
            <span>
              <small>Procedimiento</small>
              <strong>Apendicectomía</strong>
            </span>
          </div>
          <div className={`call-status ${activeTab !== "call" ? "is-static" : ""}`}>
            <span aria-hidden="true" />
            {activeTab === "call"
              ? "En llamada · 04:32"
              : activeTab === "knowledge"
                ? `Conocimiento · v${guideLoaded ? "3" : "2"}`
                : "Trazabilidad activa"}
          </div>
        </section>

        {activeTab === "call" && (
          <CallView
            listening={listening}
            setListening={setListening}
            alerted={alerted}
            setAlerted={setAlerted}
          />
        )}

        {activeTab === "knowledge" && (
          <KnowledgeView
            guideLoaded={guideLoaded}
            forgetVerified={forgetVerified}
            toggleGuide={toggleGuide}
          />
        )}

        {activeTab === "audit" && (
          <AuditView
            packageReady={packageReady}
            setPackageReady={setPackageReady}
          />
        )}
      </div>

      <footer>
        <span>Care Companion · propuesta visual</span>
        <span>
          Producto conceptual · sin integración ni acciones clínicas reales
        </span>
      </footer>
    </main>
  );
}

function CallView({
  listening,
  setListening,
  alerted,
  setAlerted,
}: {
  listening: boolean;
  setListening: (value: boolean | ((current: boolean) => boolean)) => void;
  alerted: boolean;
  setAlerted: (value: boolean) => void;
}) {
  return (
    <div className="call-grid">
      <section className="voice-card" aria-labelledby="voice-heading">
        <div className="voice-card-head">
          <div>
            <p className="eyebrow">Conversación de seguimiento</p>
            <h1 id="voice-heading">
              Una llamada que escucha antes de orientar
            </h1>
          </div>
          <span className="live-pill">
            <i aria-hidden="true" />
            En tiempo real
          </span>
        </div>

        <div
          className={`voice-stage ${listening ? "is-listening" : "is-paused"}`}
          aria-live="polite"
        >
          <div className="waveform" aria-hidden="true">
            {waveform.map((height, index) => (
              <span
                key={`${height}-${index}`}
                style={
                  {
                    "--bar-height": `${height}px`,
                    "--bar-delay": `${index * -36}ms`,
                  } as CSSProperties
                }
              />
            ))}
          </div>

          <button
            className="mic-button"
            type="button"
            aria-pressed={listening}
            aria-label={
              listening
                ? "Pausar escucha del micrófono"
                : "Reanudar escucha del micrófono"
            }
            onClick={() => setListening((value) => !value)}
          >
            <span className="mic-symbol" aria-hidden="true">
              <i />
            </span>
          </button>

          <strong>{listening ? "Escuchando" : "Llamada en pausa"}</strong>
          <p>
            {listening
              ? "Puedes interrumpir al asistente en cualquier momento."
              : "Pulsa el micrófono para continuar la conversación."}
          </p>
        </div>

        <div className="transcript" aria-label="Transcripción en vivo">
          <article className="message assistant-message">
            <span className="speaker-icon assistant-icon" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <div>
              <p className="speaker-label">Asistente · 04:18</p>
              <p>
                Cuéntame con tus propias palabras cómo te has sentido desde que
                llegaste a casa.
              </p>
            </div>
          </article>

          <article className="message patient-message">
            <span className="speaker-icon patient-icon" aria-hidden="true">
              V
            </span>
            <div>
              <p className="speaker-label">Valentina · 04:24</p>
              <p>
                Me duele más que esta mañana y siento como calor en la herida.
              </p>
            </div>
          </article>
        </div>
      </section>

      <aside className="clinical-rail" aria-label="Supervisión clínica">
        <section className="support-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Acompañamiento</p>
              <h2>Supervisión en tiempo real</h2>
            </div>
            <span className="review-chip">Revisión en curso</span>
          </div>
          <p className="section-copy">
            La conversación continúa mientras el sistema verifica señales y
            fuentes clínicas.
          </p>

          <div className="support-stats">
            <div>
              <span className="stat-icon evidence" aria-hidden="true">
                ✓
              </span>
              <span>
                <strong>2 fuentes clínicas</strong>
                <small>Verificadas y vigentes</small>
              </span>
            </div>
            <div>
              <span className="stat-icon progress" aria-hidden="true">
                <i />
              </span>
              <span>
                <strong>Evaluando señales</strong>
                <small>Con supervisión humana</small>
              </span>
            </div>
          </div>
        </section>

        <section className={`alert-card ${alerted ? "is-alerted" : ""}`}>
          <div className="alert-icon" aria-hidden="true">
            !
          </div>
          <div className="alert-copy">
            <p className="eyebrow">
              {alerted ? "Handoff registrado" : "Revisión humana"}
            </p>
            <h2>
              {alerted
                ? "El equipo recibió el contexto"
                : "Una señal necesita valoración"}
            </h2>
            <p>
              {alerted
                ? "La alerta es una simulación auditable para esta propuesta visual."
                : "Dolor en aumento y sensación de calor requieren confirmar información con el equipo."}
            </p>
            <button
              type="button"
              onClick={() => setAlerted(true)}
              disabled={alerted}
            >
              <span aria-hidden="true">{alerted ? "✓" : "+"}</span>
              {alerted ? "Alerta registrada" : "Alertar al equipo"}
            </button>
            <small>
              {alerted
                ? "No se ejecutó ninguna acción hospitalaria real."
                : "La llamada continúa mientras una persona revisa."}
            </small>
          </div>
        </section>

        <figure className="campus-card">
          <img
            src="https://www.akronchildrens.org/images-general/160792/image/large/_mg_4467_1.png"
            alt="Campus principal de Akron Children's"
          />
          <figcaption>
            <span>Referencia institucional</span>
            <strong>Akron Children&apos;s · Akron Campus</strong>
            <small>
              Fotografía oficial usada solo en esta propuesta visual.
            </small>
          </figcaption>
        </figure>
      </aside>
    </div>
  );
}

function KnowledgeView({
  guideLoaded,
  forgetVerified,
  toggleGuide,
}: {
  guideLoaded: boolean;
  forgetVerified: boolean;
  toggleGuide: () => void;
}) {
  return (
    <section className="workspace-view" aria-labelledby="knowledge-heading">
      <div className="view-hero">
        <div>
          <p className="eyebrow">Conocimiento gobernado</p>
          <h1 id="knowledge-heading">
            Aprende una guía nueva y demuestra que puede olvidarla
          </h1>
          <p>
            La experiencia visualiza la prueba crítica del concurso: actualización
            en caliente, recuperación con evidencia y eliminación verificable.
          </p>
        </div>
        <div className="hero-actions">
          <span className="simulation-chip">Simulación visual · sin datos reales</span>
          <button
            className={guideLoaded ? "secondary-action danger-action" : "primary-action"}
            type="button"
            onClick={toggleGuide}
          >
            <span aria-hidden="true">{guideLoaded ? "×" : "+"}</span>
            {guideLoaded ? "Eliminar guía simulada" : "Simular carga de guía"}
          </button>
        </div>
      </div>

      <div className="knowledge-grid">
        <section className="knowledge-status card-surface">
          <div className="status-orbit" aria-hidden="true">
            <span>{guideLoaded ? "v3" : "v2"}</span>
          </div>
          <div>
            <p className="eyebrow">Versión activa</p>
            <h2>
              {guideLoaded
                ? "La guía ya participa en nuevas consultas"
                : forgetVerified
                  ? "La eliminación quedó verificada"
                  : "Base clínica estable y lista"}
            </h2>
            <p>
              {guideLoaded
                ? "Los fragmentos se indexaron sin reiniciar la sesión. Cada respuesta conserva documento, sección y versión."
                : forgetVerified
                  ? "El canario posterior a la eliminación recuperó 0 fragmentos de la guía temporal."
                  : "Carga la guía temporal para recorrer la prueba learn → retrieve → forget."}
            </p>
          </div>
          <div className={`canary-result ${forgetVerified ? "is-success" : ""}`}>
            <span aria-hidden="true">{forgetVerified ? "✓" : "↻"}</span>
            <div>
              <strong>
                {forgetVerified ? "Canario de olvido: 0 resultados" : "Canario listo"}
              </strong>
              <small>
                {forgetVerified
                  ? "Sin fragmentos huérfanos detectados"
                  : "Se ejecuta después de eliminar"}
              </small>
            </div>
          </div>
        </section>

        <section className="pipeline-card card-surface" aria-label="Flujo de conocimiento">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Pipeline auditable</p>
              <h2>Una responsabilidad por agente</h2>
            </div>
            <span className="healthy-chip">Saludable</span>
          </div>
          <ol className="pipeline-list">
            <li className={guideLoaded ? "done" : ""}>
              <span>1</span>
              <div>
                <strong>Ingesta</strong>
                <small>Valida archivo, tipo y versión</small>
              </div>
            </li>
            <li className={guideLoaded ? "done" : ""}>
              <span>2</span>
              <div>
                <strong>Indexación</strong>
                <small>FTS5 + vectores con metadatos</small>
              </div>
            </li>
            <li className={guideLoaded ? "active" : ""}>
              <span>3</span>
              <div>
                <strong>Recuperación</strong>
                <small>Solo fuentes vigentes y permitidas</small>
              </div>
            </li>
            <li className={forgetVerified ? "done" : ""}>
              <span>4</span>
              <div>
                <strong>Olvido</strong>
                <small>Borra índice, caché y fragmentos</small>
              </div>
            </li>
          </ol>
        </section>
      </div>

      <section className="documents-card card-surface">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Fuentes de este caso ficticio</p>
            <h2>Documentos clínicos versionados</h2>
          </div>
          <span className="document-count">
            {guideLoaded ? "3 documentos" : "2 documentos"} · 100% trazables
          </span>
        </div>

        <div className="document-list">
          <DocumentRow
            accent="blue"
            title="Instrucciones de alta · Apendicectomía"
            detail="Versión 2.1 · 8 secciones · vigente"
            status="Verificada"
          />
          <DocumentRow
            accent="aqua"
            title="Protocolo de escalamiento posoperatorio"
            detail="Versión 4.0 · 12 señales · vigente"
            status="Verificada"
          />
          {guideLoaded && (
            <DocumentRow
              accent="gold"
              title="Guía temporal · Cuidado de la herida"
              detail="Versión 1.0 · cargada en esta simulación"
              status="Nueva"
            />
          )}
        </div>
      </section>
    </section>
  );
}

function DocumentRow({
  accent,
  title,
  detail,
  status,
}: {
  accent: "blue" | "aqua" | "gold";
  title: string;
  detail: string;
  status: string;
}) {
  return (
    <article className="document-row">
      <span className={`document-icon ${accent}`} aria-hidden="true">
        ≡
      </span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
      <span className={`document-status ${status === "Nueva" ? "is-new" : ""}`}>
        {status}
      </span>
    </article>
  );
}

function AuditView({
  packageReady,
  setPackageReady,
}: {
  packageReady: boolean;
  setPackageReady: (value: boolean) => void;
}) {
  return (
    <section className="workspace-view" aria-labelledby="audit-heading">
      <div className="view-hero audit-hero">
        <div>
          <p className="eyebrow">Auditoría del caso</p>
          <h1 id="audit-heading">
            Cada decisión importante conserva señal, fuente y responsable
          </h1>
          <p>
            Esta vista muestra evidencia verificable y resultados de agentes.
            No expone razonamiento interno ni reemplaza la revisión clínica.
          </p>
        </div>
        <div className="hero-actions">
          <span className="simulation-chip">Caso ficticio · datos sintéticos</span>
          <button
            className={packageReady ? "success-action" : "primary-action"}
            type="button"
            onClick={() => setPackageReady(true)}
            disabled={packageReady}
          >
            <span aria-hidden="true">{packageReady ? "✓" : "↓"}</span>
            {packageReady ? "Paquete preparado" : "Preparar evidencia"}
          </button>
        </div>
      </div>

      <section className="metrics-band" aria-label="Métricas del concurso">
        <Metric
          label="Latencia P50"
          value="< 1.2 s"
          detail="Objetivo · medir desde el 7 de agosto"
        />
        <Metric
          label="Latencia P95"
          value="< 2.5 s"
          detail="Objetivo · extremo a extremo"
        />
        <Metric
          label="Tokens"
          value="Por turno"
          detail="Trazados · pendiente de medición"
        />
        <Metric
          label="Costo"
          value="Por llamada"
          detail="Estimado · pendiente del LLM obligatorio"
        />
      </section>

      <div className="audit-grid">
        <section className="timeline-card card-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Secuencia verificable</p>
              <h2>Línea de tiempo del handoff</h2>
            </div>
            <span className="review-chip">04:18–04:35</span>
          </div>
          <ol className="audit-timeline">
            <TimelineItem
              time="04:18"
              title="Turno capturado"
              detail="La paciente ficticia describe dolor en aumento."
              tone="aqua"
            />
            <TimelineItem
              time="04:25"
              title="Señal de riesgo detectada"
              detail="Safety Agent clasifica revisión humana prioritaria."
              tone="coral"
            />
            <TimelineItem
              time="04:27"
              title="Evidencia recuperada"
              detail="2 fuentes vigentes; versión y sección preservadas."
              tone="blue"
            />
            <TimelineItem
              time="04:35"
              title="Handoff simulado"
              detail="Contexto resumido y auditable; ninguna acción real ejecutada."
              tone="lime"
            />
          </ol>
        </section>

        <section className="agents-card card-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Responsabilidad única</p>
              <h2>Resultados de agentes</h2>
            </div>
            <span className="healthy-chip">4/4 completos</span>
          </div>
          <div className="agent-results">
            <AgentResult
              label="Orquestador"
              result="Ruta y estado del caso"
              tag="Secuencia"
            />
            <AgentResult
              label="Safety Agent"
              result="Prioridad de revisión"
              tag="Escalar"
              urgent
            />
            <AgentResult
              label="Retrieval Agent"
              result="Fuentes y fragmentos"
              tag="2 citas"
            />
            <AgentResult
              label="Conversation Agent"
              result="Respuesta breve en español"
              tag="Voz"
            />
          </div>
          <div className="audit-note">
            <span aria-hidden="true">i</span>
            <p>
              Se guardan entradas, salidas estructuradas, decisiones y referencias.
              Nunca cadenas privadas de razonamiento.
            </p>
          </div>
        </section>
      </div>

      {packageReady && (
        <div className="prepared-banner" role="status">
          <span aria-hidden="true">✓</span>
          <div>
            <strong>Paquete de evidencia simulado preparado</strong>
            <small>
              Incluye timeline, fuentes, versiones y métricas pendientes; no contiene PHI.
            </small>
          </div>
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function TimelineItem({
  time,
  title,
  detail,
  tone,
}: {
  time: string;
  title: string;
  detail: string;
  tone: "aqua" | "coral" | "blue" | "lime";
}) {
  return (
    <li className={tone}>
      <time>{time}</time>
      <span aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </li>
  );
}

function AgentResult({
  label,
  result,
  tag,
  urgent = false,
}: {
  label: string;
  result: string;
  tag: string;
  urgent?: boolean;
}) {
  return (
    <article className="agent-result">
      <span className="agent-check" aria-hidden="true">
        ✓
      </span>
      <div>
        <strong>{label}</strong>
        <small>{result}</small>
      </div>
      <span className={urgent ? "agent-tag urgent" : "agent-tag"}>{tag}</span>
    </article>
  );
}
