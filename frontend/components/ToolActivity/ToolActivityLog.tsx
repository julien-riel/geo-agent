"use client";

import { useState } from "react";
import type { ToolEvent } from "@/lib/types";
import { humanise } from "./humanise";

interface Props {
  events: ToolEvent[];
  open: boolean;
  onClose: () => void;
}

export function ToolActivityLog({ events, open, onClose }: Props) {
  if (!open) return null;
  return (
    <div
      data-testid="tool-activity-log"
      style={{
        position: "fixed",
        bottom: 80,
        right: 24,
        width: 480,
        maxHeight: 520,
        overflow: "auto",
        background: "#0f172a",
        color: "#e2e8f0",
        borderRadius: 8,
        padding: 12,
        fontFamily: "system-ui",
        fontSize: 12,
        boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
        zIndex: 1000,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
        <strong style={{ flex: 1 }}>Activité</strong>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: 14 }}
          aria-label="Fermer le log"
        >
          ✕
        </button>
      </div>
      {events.length === 0 ? (
        <div style={{ color: "#94a3b8", fontStyle: "italic" }}>Aucune activité pour l&apos;instant.</div>
      ) : (
        events.map((e) => <LogRow key={e.id} event={e} />)
      )}
    </div>
  );
}

function LogRow({ event }: { event: ToolEvent }) {
  const [forensic, setForensic] = useState(false);
  const icon = event.status === "running" ? "⟳" : event.status === "ok" ? "✓" : "✗";
  const colour = event.status === "running" ? "#7dd3fc" : event.status === "ok" ? "#86efac" : "#fca5a5";

  return (
    <div
      data-testid="tool-event-row"
      style={{
        padding: "8px 0",
        borderBottom: "1px solid #1e293b",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: colour }}>{icon}</span>
        <strong>{humanise(event.tool)}</strong>
        <span style={{ flex: 1 }} />
        {event.duration_ms !== null && (
          <span style={{ color: "#94a3b8", fontFamily: "monospace" }}>
            {(event.duration_ms / 1000).toFixed(2)}s
          </span>
        )}
        <button
          aria-label="Détails forensiques"
          onClick={() => setForensic((v) => !v)}
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}
        >
          {forensic ? "▲" : "▼"}
        </button>
      </div>
      <div style={{ marginTop: 2, fontFamily: "monospace", color: "#94a3b8", fontSize: 11 }}>
        {event.args_summary}
      </div>
      {event.result_summary && (
        <div style={{ marginTop: 2, fontFamily: "monospace", color: "#86efac", fontSize: 11 }}>
          <span aria-hidden style={{ marginRight: 4 }}>→</span>
          <span>{event.result_summary}</span>
        </div>
      )}
      {event.error && (
        <div style={{ marginTop: 2, fontFamily: "monospace", color: "#fca5a5", fontSize: 11 }}>
          {event.error.code}: {event.error.message}
        </div>
      )}
      {forensic && (
        <pre
          style={{
            marginTop: 6,
            padding: 8,
            background: "#1e293b",
            borderRadius: 4,
            fontSize: 10,
            overflow: "auto",
          }}
        >
          {JSON.stringify(event.args_raw, null, 2)}
        </pre>
      )}
    </div>
  );
}
