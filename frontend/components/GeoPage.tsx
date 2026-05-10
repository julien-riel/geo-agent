"use client";

import { ThreadsProvider, useCoAgent, useCoAgentStateRender, useCopilotAction } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useEffect, useRef, useState } from "react";

import maplibregl from "maplibre-gl";
import { ChatHeader } from "@/components/ChatHeader";
import { DatasetPanel } from "@/components/DatasetPanel";
import { DatasetLayer } from "@/components/Map/DatasetLayer";
import { DrawTool } from "@/components/Map/DrawTool";
import { MapView } from "@/components/Map/MapView";
import { MetadataWidget } from "@/components/Widgets/MetadataWidget";
import { getOrCreateThreadId, resetThreadId } from "@/lib/threadId";
import { AgentState, DatasetMetaLite } from "@/lib/types";
import { SelectedFeatureProvider } from "@/lib/selectedFeature";
import { FeatureDrawer } from "@/components/Map/FeatureDrawer";

const EMPTY_STATE: AgentState = { datasets: [], active_layers: [], errors: [] };

// Gemma sometimes emits a fenced code block with no body (```json\n```), which
// CopilotKit's markdown renderer turns into String(undefined) === "undefined"
// inside a styled CodeBlock. Override `code` to suppress that artefact while
// preserving inline-code styling and a basic block render for real content.
function MarkdownCode({
  children,
  className,
  ...rest
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  const content = children == null ? "" : String(children);
  if (content === "" || content === "undefined") return null;
  const match = /language-(\w+)/.exec(className ?? "");
  const isInline = !match && !content.includes("\n");
  if (isInline) {
    return (
      <code
        className={`copilotKitMarkdownElement copilotKitInlineCode ${className ?? ""}`}
        {...rest}
      >
        {children}
      </code>
    );
  }
  return (
    <code className={className} {...rest}>
      {children}
    </code>
  );
}
const markdownTagRenderers = { code: MarkdownCode };

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
  const [hydratedDatasets, setHydratedDatasets] = useState<DatasetMetaLite[] | null>(null);
  const pushed = useRef(false);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const datasets = agentState?.datasets ?? [];
  const activeLayers = agentState?.active_layers ?? [];

  // Step 1: fetch datasets that already live on disk (e.g. from prior browser
  // sessions — the result store has no session isolation in this POC).
  useEffect(() => {
    fetch("/api/datasets")
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((rows: Array<{ id: string; alias: string | null; feature_count: number; bbox: [number, number, number, number]; source: { layer: string | null }; lineage: { operation: string } }>) => {
        setHydratedDatasets(
          rows.map((m) => ({
            id: m.id,
            alias: m.alias,
            feature_count: m.feature_count,
            bbox: m.bbox,
            layer: m.source?.layer ?? null,
            operation: m.lineage?.operation ?? "unknown",
          }))
        );
      })
      .catch((err) => console.error("hydrate datasets failed", err));
  }, []);

  // Step 2: once both the fetched list and a properly-shaped agentState are
  // available, push them in. This effect runs with a fresh setAgentState
  // closure on every agentState change, sidestepping the stale-callback issue
  // that arises when the CopilotKit runtime replaces the provisional agent
  // with the real one mid-fetch.
  useEffect(() => {
    if (pushed.current) return;
    if (!hydratedDatasets) return;
    if (!agentState || !("datasets" in agentState)) return;
    if (datasets.length > 0) return; // some other path already populated
    pushed.current = true;
    setAgentState({ ...agentState, datasets: hydratedDatasets });
  }, [hydratedDatasets, agentState, datasets.length, setAgentState]);

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

  const onShowOnMap = (id: string) => {
    const current = agentState ?? EMPTY_STATE;
    if (current.active_layers.includes(id)) return;
    setAgentState({ ...current, active_layers: [...current.active_layers, id] });
  };

  const onFitMap = (bbox: [number, number, number, number]) => {
    const m = mapRef.current;
    if (!m) return;
    m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 80, maxZoom: 16 });
  };

  useCopilotAction({
    name: "describe_dataset",
    // available: "disabled" → render-only (no handler); required by CopilotKit 1.57+
    available: "disabled",
    render: ({ args, result, status }) => {
      if (status === "executing" || !result) {
        return <MetadataWidget data={result as never} datasetId={(args as { id_or_alias?: string })?.id_or_alias ?? ""} status="executing" />;
      }
      return (
        <MetadataWidget
          data={result as never}
          datasetId={(args as { id_or_alias?: string })?.id_or_alias ?? ""}
          status="complete"
          onShowOnMap={onShowOnMap}
          onFitMap={onFitMap}
        />
      );
    },
  });

  useCopilotAction({
    name: "select_features",
    available: "disabled",
    render: ({ result, status }) => {
      if (status === "executing" || !result) {
        return <MetadataWidget data={result as never} datasetId="" status="executing" />;
      }
      const r = result as { dataset_id?: string; meta?: unknown };
      const meta = r.meta ?? r;
      const id = (meta as { id?: string })?.id ?? r.dataset_id ?? "";
      return (
        <MetadataWidget data={meta as never} datasetId={id} status="complete" onShowOnMap={onShowOnMap} onFitMap={onFitMap} />
      );
    },
  });

  useCopilotAction({
    name: "filter_attributes",
    available: "disabled",
    render: ({ result, status }) => {
      if (status === "executing" || !result) {
        return <MetadataWidget data={result as never} datasetId="" status="executing" />;
      }
      const r = result as { dataset_id?: string; meta?: unknown };
      const meta = r.meta ?? r;
      const id = (meta as { id?: string })?.id ?? r.dataset_id ?? "";
      return (
        <MetadataWidget data={meta as never} datasetId={id} status="complete" onShowOnMap={onShowOnMap} onFitMap={onFitMap} />
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
    <SelectedFeatureProvider>
      <div style={{ position: "relative", height: "100vh", width: "100vw" }}>
        <MapView mapRef={mapRef}>
          {drawing && <DrawTool onPolygon={onPolygon} />}
          {activeLayers.map((id) => (
            <DatasetLayer key={id} datasetId={id} />
          ))}
        </MapView>

        <FeatureDrawer onAskAgent={(prompt) => {
          // Best-effort: focus the chat textarea and pre-fill it.
          const ta = document.querySelector<HTMLTextAreaElement>("textarea[data-copilot-input], .copilotKitInput textarea");
          if (ta) {
            ta.value = prompt;
            ta.focus();
            ta.dispatchEvent(new Event("input", { bubbles: true }));
          }
        }} />

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
          markdownTagRenderers={markdownTagRenderers}
        />
      </div>
    </SelectedFeatureProvider>
  );
}
