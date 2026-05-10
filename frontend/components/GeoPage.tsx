"use client";

import { useCoAgent, useCoAgentStateRender } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useState } from "react";

import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { AgentState, DatasetMetaLite } from "@/lib/types";

export function GeoPage() {
  const { state, setState } = useCoAgent<AgentState>({
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
    const currentDatasets = state?.datasets ?? [];
    const currentActive = state?.active_layers ?? [];
    setState({
      ...(state ?? { datasets: [], active_layers: [], last_error: null }),
      datasets: [...currentDatasets, meta],
      active_layers: [...currentActive, meta.id],
    });
  };

  const onToggle = (id: string) => {
    const current = state?.active_layers || [];
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
    setState({
      ...(state ?? { datasets: [], active_layers: [], last_error: null }),
      active_layers: next,
    });
  };

  return (
    <div style={{ position: "relative", height: "100vh", width: "100vw" }}>
      <MapView>
        {drawing && <DrawTool onPolygon={onPolygon} />}
        {state?.active_layers?.map((id) => (
          <DatasetLayer key={id} datasetId={id} />
        ))}
      </MapView>

      <DatasetPanel
        datasets={(state?.datasets as DatasetMetaLite[]) || []}
        activeLayers={state?.active_layers || []}
        onToggle={onToggle}
        onDraw={onDraw}
        drawingActive={drawing}
      />

      <CopilotSidebar
        defaultOpen={true}
        instructions="Demande des analyses spatiales sur les couches WFS de Montréal. Dessine une zone, puis pose ta question."
        labels={{ title: "Géo-agent", initial: "Je peux interroger les couches WFS de Montréal. Dessine une zone et demande." }}
      />
    </div>
  );
}
