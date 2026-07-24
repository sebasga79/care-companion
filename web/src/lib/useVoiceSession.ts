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

export function useVoiceSession(options: VoiceSessionOptions): VoiceSession {
  const { onFinalTurn, onBargeIn, onPartial, lang = "es-CO" } = options;

  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [partial, setPartial] = useState("");

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const wantListeningRef = useRef(false);
  const speakingRef = useRef(false);
  // Keep the latest callbacks without re-creating recognition handlers.
  const cbRef = useRef({ onFinalTurn, onBargeIn, onPartial });
  useEffect(() => {
    cbRef.current = { onFinalTurn, onBargeIn, onPartial };
  });

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
      utter.onstart = () => {
        speakingRef.current = true;
        setSpeaking(true);
      };
      utter.onend = () => {
        speakingRef.current = false;
        setSpeaking(false);
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

    recognition.onspeechstart = () => {
      // Barge-in: patient speaks over the assistant → cut TTS immediately.
      if (speakingRef.current) {
        cancelSpeech();
        cbRef.current.onBargeIn?.();
      }
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? "";
        if (result.isFinal) {
          const finalText = text.trim();
          if (finalText) cbRef.current.onFinalTurn(finalText);
          interim = "";
          setPartial("");
        } else {
          interim += text;
        }
      }
      if (interim) {
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
  }, [lang, cancelSpeech]);

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
