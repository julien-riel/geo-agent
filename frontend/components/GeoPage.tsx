"use client";

import { ThreadsProvider, useCoAgent, useCoAgentStateRender, useCopilotMessagesContext } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useEffect, useState } from "react";

import { ChatHeader } from "@/components/ChatHeader";
import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { getOrCreateThreadId, resetThreadId } from "@/lib/threadId";
import { AgentState, DatasetMetaLite } from "@/lib/types";

export function GeoPage() {
  const [threadId, setThreadId] = useState<string | null>(null);
  // datasets and active_layers live in this outer component (not inside ThreadsProvider)
  // so resetting threadId can clear them without remounting MapView (which crashes
  // headless browsers on rapid remount).
  const [datasets, setDatasets] = useState<DatasetMetaLite[]>([]);
  const [activeLayers, setActiveLayers] = useState<string[]>([]);

  useEffect(() => {
    setThreadId(getOrCreateThreadId());
  }, []);

  if (!threadId) return null;

  return (
    <ThreadsProvider threadId={threadId}>
      <GeoPageBody
        threadId={threadId}
        setThreadId={setThreadId}
        datasets={datasets}
        setDatasets={setDatasets}
        activeLayers={activeLayers}
        setActiveLayers={setActiveLayers}
      />
    </ThreadsProvider>
  );
}

interface GeoPageBodyProps {
  threadId: string;
  setThreadId: (id: string) => void;
  datasets: DatasetMetaLite[];
  setDatasets: React.Dispatch<React.SetStateAction<DatasetMetaLite[]>>;
  activeLayers: string[];
  setActiveLayers: React.Dispatch<React.SetStateAction<string[]>>;
}

function GeoPageBody({
  setThreadId,
  datasets,
  setDatasets,
  activeLayers,
  setActiveLayers,
}: GeoPageBodyProps) {
  const { state: agentState, setState: setAgentState } = useCoAgent<AgentState>({
    name: "geo-agent",
    initialState: { datasets: [], active_layers: [], last_error: null },
  });
  const { setMessages } = useCopilotMessagesContext();
  const [drawing, setDrawing] = useState(false);

  // Mirror local state into agent state on every change so build_prompt
  // (server-side) sees the current datasets in its system prompt.
  useEffect(() => {
    setAgentState({
      ...(agentState ?? { datasets: [], active_layers: [], last_error: null }),
      datasets,
      active_layers: activeLayers,
    });
    // Intentionally only on local changes, not agentState changes (AGUI
    // would otherwise echo back and cause an infinite loop).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasets, activeLayers]);

  useCoAgentStateRender<AgentState>({
    name: "geo-agent",
    render: ({ state }) =>
      state?.last_error ? <div style={{ color: "red" }}>Erreur : {state.last_error}</div> : null,
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
    setDatasets((prev) => [...prev, meta]);
    setActiveLayers((prev) => [...prev, meta.id]);
  };

  const onToggle = (id: string) => {
    setActiveLayers((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const onNewConversation = () => {
    const fresh = resetThreadId();
    setThreadId(fresh);
    setDatasets([]);
    setActiveLayers([]);
    setMessages([]);
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
