"use client";

import { createContext, ReactNode, useContext, useMemo, useState } from "react";

export interface SelectedFeature {
  datasetId: string;
  index: number;
  feature: GeoJSON.Feature;
  lngLat: [number, number];
}

interface Ctx {
  selected: SelectedFeature | null;
  setSelected: (s: SelectedFeature | null) => void;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
}

const SelectedFeatureContext = createContext<Ctx | null>(null);

export function SelectedFeatureProvider({ children }: { children: ReactNode }) {
  const [selected, setSelectedState] = useState<SelectedFeature | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const setSelected = (s: SelectedFeature | null) => {
    setSelectedState(s);
    if (s === null) setDrawerOpen(false);
  };

  const value = useMemo(() => ({ selected, setSelected, drawerOpen, setDrawerOpen }), [selected, drawerOpen]);
  return <SelectedFeatureContext.Provider value={value}>{children}</SelectedFeatureContext.Provider>;
}

export function useSelectedFeature(): Ctx {
  const ctx = useContext(SelectedFeatureContext);
  if (!ctx) throw new Error("useSelectedFeature must be used inside SelectedFeatureProvider");
  return ctx;
}
