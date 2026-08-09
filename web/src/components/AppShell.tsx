"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/call", label: "Llamada" },
  { href: "/knowledge", label: "Base clínica" },
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
  checking: "Servidor: verificando…",
  ready: "Servidor: listo",
  error: "Servidor: no disponible",
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

        <span className="prototype-badge">Seguimiento inteligente</span>

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
                Consulta{" "}
                <code>docs/architecture.md</code> y <code>docs/design.md</code> para
                el contrato técnico completo y la trazabilidad del sistema.
              </p>
            </div>
          </details>
        </div>
      </header>

      <main className="page-wrap" id="main-content">
        {children}
      </main>

      <footer>
        <span>Care Companion · seguimiento postoperatorio inteligente</span>
        <span>Conversación, evidencia y supervisión humana</span>
      </footer>
    </div>
  );
}
