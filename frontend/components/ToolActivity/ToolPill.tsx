"use client";

import { useEffect, useRef, useState } from "react";
import type { ToolEvent } from "@/lib/types";
import { humanise } from "./humanise";

const APPEAR_MS = 150;
const HIDE_MS = 100;
const STALLED_MS = 60_000;

interface Props {
  events: ToolEvent[];
}

export function ToolPill({ events }: Props) {
  const running = [...events].reverse().find((e) => e.status === "running");
  const [visible, setVisible] = useState<ToolEvent | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (running) {
      timerRef.current = setTimeout(() => setVisible(running), APPEAR_MS);
    } else if (visible) {
      timerRef.current = setTimeout(() => setVisible(null), HIDE_MS);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [running, visible]);

  // Live counter — refresh every 250ms while visible
  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [visible]);

  if (!visible) return null;
  const elapsedMs = now - visible.started_at * 1000;
  const stalled = elapsedMs > STALLED_MS;
  const seconds = (elapsedMs / 1000).toFixed(1);

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: stalled ? "#fbbf24" : "#0ea5e9",
        color: "#fff",
        padding: "6px 12px",
        borderRadius: 999,
        fontFamily: "system-ui",
        fontSize: 12,
        fontWeight: 500,
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
      }}
    >
      <span aria-hidden style={{ animation: "spin 1.2s linear infinite" }}>⟳</span>
      <span>{humanise(visible.tool)}</span>
      <span style={{ opacity: 0.85, fontFamily: "monospace" }}>{seconds}s</span>
      {stalled && (
        <span style={{ marginLeft: 4, fontStyle: "italic" }}>
          L&apos;opération prend plus longtemps que prévu
        </span>
      )}
    </div>
  );
}
