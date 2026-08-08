import type { Metadata } from "next";
import { Nunito_Sans, Inter } from "next/font/google";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

const nunitoSans = Nunito_Sans({
  variable: "--font-nunito-sans",
  subsets: ["latin"],
  weight: ["600", "700", "800", "900"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Care Companion — Seguimiento postoperatorio",
  description:
    "Seguimiento postoperatorio por voz con evidencia clínica, agentes de responsabilidad única y supervisión humana.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={`${nunitoSans.variable} ${inter.variable}`}>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
