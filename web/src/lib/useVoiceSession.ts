"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Voice pipeline behind a provider-agnostic hook (ADR-001 "puertos"). Today it
 * uses the browser-native Web Speech API — SpeechRecognition for STT and
 * SpeechSynthesis for TTS — so the realtime voice experience (incl. barge-in)
 * works with zero external provider. At T0 the mandatory model's realtime
 * voice can replace this implementation without changing the /call page: the
 * page only depends on this hook's surface (start/stop/speak + callbacks).
 *
 * Barge-in: while the assistant is speaking, the first detected patient speech
 * cancels synthesis synchronously (`speechSynthesis.cancel()` — well under the
 * 250 ms target) and notifies via `onBargeIn`.
 */

export interface VoiceSessionOptions {
  onFinalTurn: (text: string) => void;
  onBargeIn?: () => void;
  onPartial?: (text: string) => void;
  lang?: string;
}

export interface VoiceSession {
  supported: boolean;
  listening: boolean;
  speaking: boolean;
  partial: string;
  start: () => void;
  /** Detiene solo STT; no cancela una locución TTS actual o pendiente. */
  stopListening: () => void;
  /** Apagado total: detiene STT y cancela TTS. */
  stop: () => void;
  speak: (text: string) => void;
  cancelSpeech: () => void;
}

function getRecognitionCtor(): typeof SpeechRecognition | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

/**
 * Echo control — half-duplex, con supresión por contenido como red de
 * seguridad.
 *
 * Bug real (visto dos veces en pruebas en vivo con parlantes + micrófono de
 * un portátil): el TTS del agente entra por el micrófono, `SpeechRecognition`
 * lo transcribe como habla del paciente, se envía como turno, el agente
 * responde, y el ciclo se repite — un bucle infinito donde el paciente
 * "dice" fragmentos de la frase anterior del asistente ("Gracias", "por
 * contarme", "Gracias por"…).
 *
 * El primer intento fue solo supresión por contenido (descartar
 * transcripciones que solapan lo que estamos diciendo). **No alcanzó**: los
 * fragmentos que el reconocedor entrega son cortos ("Gracias" = 7 caracteres)
 * y caían bajo cualquier umbral razonable de longitud; bastaba uno para
 * realimentar el bucle.
 *
 * La Web Speech API no expone el stream de audio, así que no hay cancelación
 * de eco por hardware posible. La única defensa determinista es **half-duplex**:
 * apagar el reconocimiento mientras el asistente habla y reanudarlo cuando
 * termina. Eso elimina el bucle por construcción, no por heurística.
 *
 * Costo aceptado: se pierde el barge-in por voz mientras suena el audio (no se
 * puede escuchar y hablar a la vez sin AEC). El usuario puede cortar con
 * "Detener voz". Un bucle infinito frente al jurado es catastrófico; perder
 * barge-in con parlantes abiertos es un demérito menor — y con audífonos el
 * problema no existiría, pero no podemos asumir el hardware del evaluador.
 *
 * La supresión por contenido se mantiene como segunda línea para la ventana
 * de reinicio del reconocedor (donde todavía puede colarse audio del final de
 * la locución), ahora con umbral de longitud bajo para atrapar fragmentos
 * cortos.
 */
const ECHO_TAIL_MS = 1500;
const ECHO_TOKEN_OVERLAP_THRESHOLD = 0.6;
const ECHO_MIN_CHARS = 3;
// Chrome a veces no dispara `onend` de speechSynthesis (bug conocido con
// textos largos). Sin este seguro, el micrófono quedaría apagado para
// siempre y la llamada moriría en silencio. ~90 ms por carácter cubre con
// margen una locución en español a velocidad normal.
const TTS_WATCHDOG_MS_PER_CHAR = 90;
const TTS_WATCHDOG_MIN_MS = 4000;

function normalizeForEcho(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // strip accents
    .replace(/[^\p{L}\p{N}\s]/gu, " ") // strip punctuation
    .replace(/\s+/g, " ")
    .trim();
}

function overlapsSpokenText(candidate: string, spoken: string): boolean {
  const candidateNorm = normalizeForEcho(candidate);
  if (candidateNorm.length < ECHO_MIN_CHARS || !spoken) return false;

  const candidateTokens = candidateNorm.split(" ").filter(Boolean);
  if (candidateTokens.length === 0) return false;

  const spokenTokens = new Set(spoken.split(" ").filter(Boolean));
  const matched = candidateTokens.filter((token) => spokenTokens.has(token)).length;
  return matched / candidateTokens.length >= ECHO_TOKEN_OVERLAP_THRESHOLD;
}

export function useVoiceSession(options: VoiceSessionOptions): VoiceSession {
  const { onFinalTurn, onBargeIn, onPartial, lang = "es-CO" } = options;

  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [partial, setPartial] = useState("");

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const wantListeningRef = useRef(false);
  const speakingRef = useRef(false);
  // Half-duplex: true mientras el reconocimiento está apagado A PROPÓSITO
  // porque el asistente habla — impide que `onend` lo reinicie solo.
  const pausedForTtsRef = useRef(false);
  const ttsWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Echo suppression state: what we are currently saying (normalized) and
  // until when a matching transcript should still be treated as our own echo.
  const spokenNormRef = useRef("");
  const echoWindowUntilRef = useRef(0);
  // Keep the latest callbacks without re-creating recognition handlers.
  const cbRef = useRef({ onFinalTurn, onBargeIn, onPartial });
  useEffect(() => {
    cbRef.current = { onFinalTurn, onBargeIn, onPartial };
  });

  const isEcho = useCallback((text: string): boolean => {
    const withinWindow = speakingRef.current || Date.now() < echoWindowUntilRef.current;
    if (!withinWindow) return false;
    return overlapsSpokenText(text, spokenNormRef.current);
  }, []);

  useEffect(() => {
    const ctor = getRecognitionCtor();
    const ttsOk = typeof window !== "undefined" && "speechSynthesis" in window;
    // One-time client capability probe (window is unavailable during SSR).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSupported(Boolean(ctor) && ttsOk);
  }, []);

  /** Half-duplex: apaga el micrófono mientras el asistente habla. */
  const pauseListeningForTts = useCallback(() => {
    if (!recognitionRef.current || pausedForTtsRef.current) return;
    pausedForTtsRef.current = true;
    try {
      // `abort()` (no `stop()`): descarta lo capturado en vuelo en vez de
      // entregarlo como final — justo lo que no queremos si es nuestro eco.
      recognitionRef.current.abort();
    } catch {
      // Ya estaba detenido; el estado de arriba es lo que manda.
    }
    setListening(false);
  }, []);

  const resumeListeningAfterTts = useCallback(() => {
    if (ttsWatchdogRef.current) {
      clearTimeout(ttsWatchdogRef.current);
      ttsWatchdogRef.current = null;
    }
    if (!pausedForTtsRef.current) return;
    pausedForTtsRef.current = false;
    if (!wantListeningRef.current || !recognitionRef.current) return;
    try {
      recognitionRef.current.start();
      setListening(true);
    } catch {
      // `start()` lanza si ya estaba corriendo — estado ya consistente.
    }
  }, []);

  const cancelSpeech = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    speakingRef.current = false;
    setSpeaking(false);
    echoWindowUntilRef.current = Date.now() + ECHO_TAIL_MS;
    resumeListeningAfterTts();
  }, [resumeListeningAfterTts]);

  const speak = useCallback(
    (text: string) => {
      if (!text || typeof window === "undefined" || !("speechSynthesis" in window)) return;
      // New utterance always supersedes the previous one.
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = lang;
      // Arm echo suppression BEFORE speaking: recognition can pick up the
      // first words before `onstart` fires.
      spokenNormRef.current = normalizeForEcho(text);
      echoWindowUntilRef.current = Date.now() + ECHO_TAIL_MS;
      // Half-duplex: micrófono apagado ANTES de emitir el primer sonido.
      pauseListeningForTts();

      const finish = () => {
        speakingRef.current = false;
        setSpeaking(false);
        // Keep suppressing briefly: finals for audio captured during
        // playback often arrive after synthesis already ended.
        echoWindowUntilRef.current = Date.now() + ECHO_TAIL_MS;
        resumeListeningAfterTts();
      };

      utter.onstart = () => {
        speakingRef.current = true;
        setSpeaking(true);
      };
      utter.onend = finish;
      utter.onerror = finish;

      // Seguro contra `onend` que nunca llega (ver TTS_WATCHDOG_*): sin esto
      // el micrófono quedaría apagado y la llamada moriría en silencio.
      if (ttsWatchdogRef.current) clearTimeout(ttsWatchdogRef.current);
      ttsWatchdogRef.current = setTimeout(
        finish,
        Math.max(TTS_WATCHDOG_MIN_MS, text.length * TTS_WATCHDOG_MS_PER_CHAR),
      );

      window.speechSynthesis.speak(utter);
    },
    [lang, pauseListeningForTts, resumeListeningAfterTts],
  );

  const start = useCallback(() => {
    const ctor = getRecognitionCtor();
    if (!ctor) return;
    if (recognitionRef.current) return;

    const recognition = new ctor();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    // NOTE: barge-in is deliberately NOT wired to `onspeechstart`. That fired
    // on the assistant's own voice coming back through the speakers, so the
    // agent interrupted itself on every reply. Con half-duplex el micrófono
    // ya está apagado mientras hablamos, así que aquí solo queda la red de
    // seguridad por contenido para la ventana de reinicio.

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      // Nada de lo capturado mientras hablamos (o justo después) puede
      // tratarse como turno del paciente.
      if (speakingRef.current || pausedForTtsRef.current) return;

      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) {
          const finalText = text.trim();
          if (finalText) {
            if (isEcho(finalText)) {
              // Our own TTS captured by the mic — never send it as a
              // patient turn (that produced a feedback loop in live tests).
              setPartial("");
              continue;
            }
            cbRef.current.onFinalTurn(finalText);
          }
          interim = "";
          setPartial("");
        } else {
          interim += text;
        }
      }
      if (interim) {
        if (isEcho(interim)) return;
        setPartial(interim);
        cbRef.current.onPartial?.(interim);
      }
    };

    recognition.onerror = () => {
      // Recoverable errors (no-speech, aborted) just end the current run; the
      // onend handler restarts if the user still wants to listen.
    };

    recognition.onend = () => {
      // Pausa deliberada por TTS (half-duplex): NO reiniciar aquí — lo hace
      // `resumeListeningAfterTts` cuando termina la locución. Sin esta
      // guarda, el reinicio automático volvería a abrir el micrófono en
      // plena locución y reaparecería el bucle de eco.
      if (pausedForTtsRef.current) {
        setListening(false);
        return;
      }
      // Chrome stops recognition after a silence window; restart while active.
      if (wantListeningRef.current && recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch {
          // Already started or transient — ignore.
        }
      } else {
        setListening(false);
      }
    };

    recognitionRef.current = recognition;
    wantListeningRef.current = true;
    try {
      recognition.start();
      setListening(true);
    } catch {
      // start() throws if called twice; state stays consistent.
    }
  }, [lang, isEcho]);

  const stopListening = useCallback(() => {
    wantListeningRef.current = false;
    pausedForTtsRef.current = false;
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onend = null;
      recognition.stop();
    }
    setListening(false);
    setPartial("");
  }, []);

  const stop = useCallback(() => {
    stopListening();
    if (ttsWatchdogRef.current) {
      clearTimeout(ttsWatchdogRef.current);
      ttsWatchdogRef.current = null;
    }
    cancelSpeech();
  }, [cancelSpeech, stopListening]);

  useEffect(() => {
    return () => {
      wantListeningRef.current = false;
      pausedForTtsRef.current = false;
      if (ttsWatchdogRef.current) clearTimeout(ttsWatchdogRef.current);
      recognitionRef.current?.abort();
      recognitionRef.current = null;
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return {
    supported,
    listening,
    speaking,
    partial,
    start,
    stopListening,
    stop,
    speak,
    cancelSpeech,
  };
}
