"use client";

import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";

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

  // Expose setSelected on window for e2e testing (non-production only).
  useEffect(() => {
    if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
      (window as unknown as { __testSetSelected: typeof setSelected }).__testSetSelected = setSelected;
    }
  }, [setSelected]);

  return <SelectedFeatureContext.Provider value={value}>{children}</SelectedFeatureContext.Provider>;
}

export function useSelectedFeature(): Ctx {
  const ctx = useContext(SelectedFeatureContext);
  if (!ctx) throw new Error("useSelectedFeature must be used inside SelectedFeatureProvider");
  return ctx;
}
