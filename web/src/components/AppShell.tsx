"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/call", label: "Llamada" },
  { href: "/knowledge", label: "Conocimiento" },
  { href: "/audit", label: "Auditoría" },
] as const;

type ReadinessStatus = "checking" | "ready" | "error";

function useBackendReadiness(): ReadinessStatus {
  const [status, setStatus] = useState<ReadinessStatus>("checking");

  useEffect(() => {
    let cancelled = false;

    api
      .health()
      .then(() => {
        if (!cancelled) setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}

const READINESS_COPY: Record<ReadinessStatus, string> = {
  checking: "Backend: verificando…",
  ready: "Backend: listo",
  error: "Backend: no disponible",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const readiness = useBackendReadiness();

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Saltar al contenido principal
      </a>

      <header className="topbar">
        <Link href="/call" className="brand" aria-label="Ir a la llamada de Care Companion">
          <span className="brand-mark" aria-hidden="true">
            <span className="bar-h" />
            <span className="bar-v" />
          </span>
          <span>Care Companion</span>
        </Link>

        <span className="prototype-badge">Prototipo clínico</span>

        <nav className="primary-nav" aria-label="Navegación principal">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname?.startsWith(item.href) ?? false;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="nav-item"
                aria-current={isActive ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="header-status">
          <span className="chip chip-neutral" title="Supervisión humana requerida en decisiones de riesgo">
            Supervisión humana visible
          </span>

          <span className="readiness-pill" data-status={readiness}>
            <span className="dot" aria-hidden="true" />
            {READINESS_COPY[readiness]}
          </span>

          <details className="help-disclosure">
            <summary>Ayuda técnica</summary>
            <div className="help-panel" role="note">
              <p style={{ margin: 0 }}>
                Prototipo del reto Care Companion. Consulta{" "}
                <code>docs/architecture.md</code> y <code>docs/design.md</code> para
                el contrato técnico completo. Ningún dato mostrado corresponde a un
                paciente real.
              </p>
            </div>
          </details>
        </div>
      </header>

      <main className="page-wrap" id="main-content">
        {children}
      </main>

      <footer>
        <span>Care Companion · prototipo de concurso</span>
        <span>Producto conceptual · sin integración ni acciones clínicas reales</span>
      </footer>
    </div>
  );
}
