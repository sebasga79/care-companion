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
  stop: () => void;
  speak: (text: string) => void;
  cancelSpeech: () => void;
}

function getRecognitionCtor(): typeof SpeechRecognition | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

/**
 * Echo suppression (fixes a real bug seen in live testing on a laptop with
 * speakers + built-in mic: the agent's own TTS was picked up by the
 * microphone and sent back as a *patient* turn — the transcript literally
 * showed the patient "saying" the assistant's previous sentence).
 *
 * The Web Speech API gives no access to the underlying audio stream, so we
 * cannot enable hardware echo cancellation. Instead we suppress by content:
 * while the assistant is speaking (plus a short tail, because recognition
 * delivers finals late), any transcript that substantially overlaps the text
 * we are speaking is treated as echo and dropped.
 *
 * This preserves real barge-in: speech that does NOT match what we're saying
 * still interrupts the assistant normally.
 */
const ECHO_TAIL_MS = 1500;
const ECHO_TOKEN_OVERLAP_THRESHOLD = 0.6;
const ECHO_MIN_CHARS = 8;

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

  const cancelSpeech = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    speakingRef.current = false;
    setSpeaking(false);
  }, []);

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
      utter.onstart = () => {
        speakingRef.current = true;
        setSpeaking(true);
      };
      utter.onend = () => {
        speakingRef.current = false;
        setSpeaking(false);
        // Keep suppressing briefly: finals for audio captured during
        // playback often arrive after synthesis already ended.
        echoWindowUntilRef.current = Date.now() + ECHO_TAIL_MS;
      };
      window.speechSynthesis.speak(utter);
    },
    [lang],
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
    // agent interrupted itself on every reply. Barge-in now triggers from
    // `onresult` only when the recognized text is NOT our own echo.

    recognition.onresult = (event: SpeechRecognitionEvent) => {
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
            if (speakingRef.current) {
              // Real speech over the assistant → genuine barge-in.
              cancelSpeech();
              cbRef.current.onBargeIn?.();
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
        if (speakingRef.current) {
          cancelSpeech();
          cbRef.current.onBargeIn?.();
        }
        setPartial(interim);
        cbRef.current.onPartial?.(interim);
      }
    };

    recognition.onerror = () => {
      // Recoverable errors (no-speech, aborted) just end the current run; the
      // onend handler restarts if the user still wants to listen.
    };

    recognition.onend = () => {
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
  }, [lang, cancelSpeech, isEcho]);

  const stop = useCallback(() => {
    wantListeningRef.current = false;
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onend = null;
      recognition.stop();
    }
    setListening(false);
    setPartial("");
    cancelSpeech();
  }, [cancelSpeech]);

  useEffect(() => {
    return () => {
      wantListeningRef.current = false;
      recognitionRef.current?.abort();
      recognitionRef.current = null;
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return { supported, listening, speaking, partial, start, stop, speak, cancelSpeech };
}
