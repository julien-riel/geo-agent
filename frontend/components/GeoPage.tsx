"use client";

import { ThreadsProvider, useCoAgent, useCoAgentStateRender } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useEffect, useState } from "react";

import { ChatHeader } from "@/components/ChatHeader";
import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { getOrCreateThreadId, resetThreadId } from "@/lib/threadId";
import { AgentState, DatasetMetaLite } from "@/lib/types";

const EMPTY_STATE: AgentState = { datasets: [], active_layers: [], errors: [] };

export function GeoPage() {
  const [threadId, setThreadId] = useState<string | null>(null);

  useEffect(() => {
    setThreadId(getOrCreateThreadId());
  }, []);

  if (!threadId) return null;

  return (
    <ThreadsProvider threadId={threadId}>
      <GeoPageBody />
    </ThreadsProvider>
  );
}

function GeoPageBody() {
  const { state: agentState, setState: setAgentState } = useCoAgent<AgentState>({
    name: "geo-agent",
    initialState: EMPTY_STATE,
  });
  const [drawing, setDrawing] = useState(false);

  const datasets = agentState?.datasets ?? [];
  const activeLayers = agentState?.active_layers ?? [];

  useCoAgentStateRender<AgentState>({
    name: "geo-agent",
    render: ({ state }) => {
      const last = state?.errors?.[state.errors.length - 1];
      if (!last) return null;
      return (
        <div style={{ color: "red" }}>
          <strong>Erreur ({last.code}) :</strong> {last.message}
          {last.suggestion ? <div style={{ opacity: 0.8 }}>↳ {last.suggestion}</div> : null}
        </div>
      );
    },
  });

  const onDraw = () => setDrawing(true);

  const onPolygon = async (polygon: GeoJSON.Polygon) => {
    setDrawing(false);
    const r = await fetch("/api/datasets/drawing", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ polygon }),
    });
    if (!r.ok) {
      console.error("failed to save drawing", await r.text());
      return;
    }
    const meta = (await r.json()) as DatasetMetaLite;
    const current = agentState ?? EMPTY_STATE;
    setAgentState({
      ...current,
      datasets: [...current.datasets, meta],
      active_layers: [...current.active_layers, meta.id],
    });
  };

  const onToggle = (id: string) => {
    const current = agentState ?? EMPTY_STATE;
    const next = current.active_layers.includes(id)
      ? current.active_layers.filter((x) => x !== id)
      : [...current.active_layers, id];
    setAgentState({ ...current, active_layers: next });
  };

  const onNewConversation = () => {
    resetThreadId();
    // CopilotSidebar reads messages from a runtime context we can't reliably
    // clear without remounting the whole CopilotKit provider tree. A page
    // reload is the simplest reliable reset; the new threadId persists in
    // sessionStorage, so we resume on a fresh thread on next mount.
    window.location.reload();
  };

  return (
    <div style={{ position: "relative", height: "100vh", width: "100vw" }}>
      <MapView>
        {drawing && <DrawTool onPolygon={onPolygon} />}
        {activeLayers.map((id) => (
          <DatasetLayer key={id} datasetId={id} />
        ))}
      </MapView>

      <DatasetPanel
        datasets={datasets}
        activeLayers={activeLayers}
        onToggle={onToggle}
        onDraw={onDraw}
        drawingActive={drawing}
      />

      <CopilotSidebar
        defaultOpen={true}
        instructions="Demande des analyses spatiales sur les couches WFS de Montréal. Dessine une zone, puis pose ta question."
        labels={{ title: "Géo-agent", initial: "Je peux interroger les couches WFS de Montréal. Dessine une zone et demande." }}
        Header={() => <ChatHeader onNewConversation={onNewConversation} />}
      />
    </div>
  );
}
