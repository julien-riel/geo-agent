const LABELS: Record<string, string> = {
  list_wfs_layers: "Liste des couches WFS",
  describe_wfs_layer: "Inspection de la couche WFS",
  select_features: "Sélection de features WFS",
  filter_attributes: "Filtrage par attribut",
  aggregate: "Agrégation",
  describe_dataset: "Lecture des métadonnées",
  spatial_overlay: "Overlay spatial",
  spatial_join: "Jointure spatiale",
  transform_geometry: "Transformation géométrique",
  delete_dataset: "Suppression du dataset",
  rename_dataset: "Renommage du dataset",
  clear_all_datasets: "Nettoyage de tous les datasets",
  show_on_map: "Affichage sur la carte",
  hide_on_map: "Masquage de la couche",
  inspect_dataset: "Inspection du dataset",
};

export function humanise(tool: string): string {
  return LABELS[tool] ?? tool;
}
