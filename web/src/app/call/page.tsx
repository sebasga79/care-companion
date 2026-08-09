"use client";

import { useCallback, useEffect, useState } from "react";
import { CallModal } from "@/components/CallModal";
import { StatusBanner } from "@/components/StatusBanner";
import { api, ApiError, type CaseSummary } from "@/lib/api";

function formatSurgeryDate(value: string | null): string {
  if (!value) return "Fecha no disponible";
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-CO", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function CallPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [casesError, setCasesError] = useState<string | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [patientQuery, setPatientQuery] = useState("");

  const fetchCases = useCallback(async () => {
    try {
      const result = await api.listCases();
      setCases(result);
      setCasesError(null);
    } catch (error) {
      setCasesError(error instanceof ApiError ? error.message : "Error desconocido.");
    } finally {
      setLoadingCases(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCases();
  }, [fetchCases]);

  // Esta lista es "los 160 pacientes reales" — los 3 casos de prueba
  // (Camila/Julián/Sofía) se excluyen a propósito. Viven en `/knowledge`,
  // donde tiene sentido abrir una llamada sin el protocolo completo de
  // historial longitudinal (ver `CombinedCaseAdapter` en el backend).
  const realCases = cases.filter((item) => !item.isSyntheticDemo);
  const selectedCase = realCases.find((item) => item.id === selectedCaseId) ?? null;
  const normalizedPatientQuery = patientQuery.trim().toLocaleLowerCase("es");
  const visibleCases = normalizedPatientQuery
    ? realCases.filter((item) =>
        `${item.patientAlias} ${item.procedure}`
          .toLocaleLowerCase("es")
          .includes(normalizedPatientQuery),
      )
    : realCases;

  return (
    <>
      <section className="patient-picker card card-pad" aria-labelledby="patient-picker-heading">
        <div className="patient-picker-head">
          <div>
            <p className="eyebrow">Pacientes con historia longitudinal</p>
            <h1 id="patient-picker-heading">Selecciona el paciente que recibirá la llamada</h1>
            <p>
              Cada tarjeta reúne su cirugía y la evolución registrada en los cuatro
              seguimientos anteriores.
            </p>
          </div>
          <label className="patient-search">
            <span className="sr-only">Buscar paciente o cirugía</span>
            <input
              type="search"
              placeholder="Buscar paciente o cirugía…"
              value={patientQuery}
              onChange={(event) => setPatientQuery(event.target.value)}
            />
          </label>
        </div>

        {loadingCases ? (
          <p className="patient-picker-status">Cargando pacientes…</p>
        ) : visibleCases.length === 0 ? (
          <p className="patient-picker-status">No encontramos pacientes con ese criterio.</p>
        ) : (
          <div className="patient-card-grid" aria-label="Pacientes disponibles">
            {visibleCases.map((item) => (
              <button
                type="button"
                key={item.id}
                className="patient-card"
                data-selected="false"
                onClick={() => setSelectedCaseId(item.id)}
              >
                <span className="patient-card-check" aria-hidden="true">
                  {item.patientAlias.slice(0, 1)}
                </span>
                <span className="patient-card-copy">
                  <strong>{item.patientAlias}</strong>
                  <span>{item.procedure}</span>
                  <small>Cirugía: {formatSurgeryDate(item.surgeryDate)}</small>
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {casesError ? <StatusBanner message={casesError} onRetry={fetchCases} /> : null}

      {selectedCase ? (
        <CallModal patientCase={selectedCase} onClose={() => setSelectedCaseId("")} />
      ) : null}
    </>
  );
}
