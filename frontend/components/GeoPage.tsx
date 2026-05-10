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

export function GeoPage() {
  const [threadId, setThreadId] = useState<string | null>(null);
  // datasets and active_layers live here (outside ThreadsProvider) so that:
  // 1. They are cleared explicitly on "Nouveau" without remounting MapView.
  // 2. MapView stays mounted, avoiding headless-browser crashes on remount.
  const [datasets, setDatasets] = useState<DatasetMetaLite[]>([]);
  const [activeLayers, setActiveLayers] = useState<string[]>([]);

  useEffect(() => {
    setThreadId(getOrCreateThreadId());
  }, []);

  const onNewConversation = () => {
    const fresh = resetThreadId();
    setThreadId(fresh);
    setDatasets([]);
    setActiveLayers([]);
  };

  if (!threadId) return null;

  // No key on ThreadsProvider — GeoPageBody stays mounted across thread changes.
  // State is cleared explicitly in onNewConversation above.
  return (
    <ThreadsProvider threadId={threadId}>
      <GeoPageBody
        threadId={threadId}
        onNewConversation={onNewConversation}
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
  onNewConversation: () => void;
  datasets: DatasetMetaLite[];
  setDatasets: React.Dispatch<React.SetStateAction<DatasetMetaLite[]>>;
  activeLayers: string[];
  setActiveLayers: React.Dispatch<React.SetStateAction<string[]>>;
}

function GeoPageBody({
  onNewConversation,
  datasets,
  setDatasets,
  activeLayers,
  setActiveLayers,
}: GeoPageBodyProps) {
  const { state: agentState } = useCoAgent<AgentState>({
    name: "geo-agent",
    initialState: { datasets: [], active_layers: [], last_error: null },
  });
  const [drawing, setDrawing] = useState(false);

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
