"use client";

import { useCoAgent, useCoAgentStateRender } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useState } from "react";

import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { AgentState } from "@/lib/types";

export function GeoPage() {
  const { state, setState } = useCoAgent<AgentState>({
    name: "geo-agent",
    initialState: { datasets: [], current_drawing: null, active_layers: [], last_error: null },
  });
  const [drawing, setDrawing] = useState(false);

  useCoAgentStateRender<AgentState>({
    name: "geo-agent",
    render: ({ state }) =>
      state?.last_error ? <div style={{ color: "red" }}>Erreur : {state.last_error}</div> : null,
  });

  const onDraw = () => setDrawing(true);
  const onPolygon = (polygon: GeoJSON.Polygon) => {
    setState({ ...state, current_drawing: { type: "Feature", geometry: polygon, properties: {} } });
    setDrawing(false);
  };
  const onToggle = (id: string) => {
    const next = state.active_layers.includes(id)
      ? state.active_layers.filter((x) => x !== id)
      : [...state.active_layers, id];
    setState({ ...state, active_layers: next });
  };

  return (
    <div style={{ position: "relative", height: "100vh", width: "100vw" }}>
      <MapView>
        {drawing && <DrawTool onPolygon={onPolygon} />}
        {state.active_layers.map((id) => (
          <DatasetLayer key={id} datasetId={id} />
        ))}
      </MapView>

      <DatasetPanel
        datasets={state.datasets as any}
        activeLayers={state.active_layers}
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
