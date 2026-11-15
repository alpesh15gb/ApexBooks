import { createContext, useContext } from "react";

// Company-wide inventory setup: item locations, the optional Automobile module and its vehicle list.
// `setup` is the server's /inventory-setup response (or null while unknown or unsupported).
export const InventorySetupContext = createContext({ setup: null, reload: async () => {}, supported: false });
export const useInventorySetup = () => useContext(InventorySetupContext);

export const tidy = (text) => String(text ?? "").replace(/\s+/g, " ").trim();
export const sameName = (a, b) => tidy(a).toLowerCase() === tidy(b).toLowerCase();
const lower = (text) => tidy(text).toLowerCase();

export function locationMap(setup) {
  return new Map((setup?.locations || []).map((row) => [row.id, row]));
}
export function locationNames(setup, ids) {
  const known = locationMap(setup);
  return (ids || []).map((id) => known.get(id)?.name).filter(Boolean);
}

export function yearsLabel(from, to) {
  if (from && to) return from === to ? `${from}` : `${from}–${to}`;
  if (from) return `${from} onwards`;
  if (to) return `up to ${to}`;
  return "";
}
export function fitmentLabel(row) {
  const years = yearsLabel(row.year_from, row.year_to);
  return [tidy(row.make), tidy(row.model), years].filter(Boolean).join(" ");
}

// What a list row or POS tile shows for an item. Only meaningful details are returned.
export function itemSummary(record, setup) {
  const data = record?.data || {};
  const fits = (data.vehicle_fitment || []).map(fitmentLabel).filter(Boolean);
  return {
    locations: locationNames(setup, data.location_ids),
    fits,
    oem: tidy(data.oem_number),
    brand: tidy(data.part_brand),
    grade: data.part_grade || "",
  };
}
export const GRADE_LABELS = { oem: "OEM", aftermarket: "Aftermarket", used: "Used", refurbished: "Refurbished" };

// Registers and the POS find items by location, part number, brand or the vehicle they fit.
export function itemSearchText(record, setup) {
  const summary = itemSummary(record, setup);
  const data = record?.data || {};
  return [record?.name, record?.number, data.hsn, data.barcode, ...summary.locations, summary.oem, summary.brand,
    GRADE_LABELS[summary.grade], ...summary.fits].filter(Boolean).join(" ").toLowerCase();
}

// ---- Editing the vehicle list (owner, Settings). The server stores only the edits, not the built-in catalogue. ----
export function effectiveCatalog(defaults, draft) {
  const hiddenMakes = new Set((draft.vehicle_hidden_makes || []).map(lower));
  const hiddenModels = new Set((draft.vehicle_hidden_models || []).map((row) => `${lower(row.make)}|${lower(row.model)}`));
  const added = new Map((draft.vehicle_added || []).map((row) => [lower(row.make), row]));
  const result = [];
  const used = new Set();
  for (const entry of defaults || []) {
    const makeKey = lower(entry.make);
    used.add(makeKey);
    const extra = added.get(makeKey);
    const models = entry.models.filter((name) => !hiddenModels.has(`${makeKey}|${lower(name)}`)).map((name) => ({ name, custom: false }));
    const seen = new Set(models.map((row) => lower(row.name)));
    for (const name of extra?.models || []) if (!seen.has(lower(name))) models.push({ name, custom: true });
    result.push({ make: entry.make, type: entry.type, custom: false, hidden: hiddenMakes.has(makeKey), models: models.sort((a, b) => a.name.localeCompare(b.name)) });
  }
  for (const [makeKey, entry] of added) {
    if (used.has(makeKey)) continue;
    result.push({ make: entry.make, type: entry.type || "car", custom: true, hidden: false,
      models: (entry.models || []).map((name) => ({ name, custom: true })).sort((a, b) => a.name.localeCompare(b.name)) });
  }
  return result;
}

const defaultEntry = (defaults, make) => (defaults || []).find((entry) => sameName(entry.make, make));
const addedIndex = (draft, make) => (draft.vehicle_added || []).findIndex((row) => sameName(row.make, make));

// Pure edit helpers. Each returns { draft, error } so the UI can show why an edit was refused.
export function addMake(defaults, draft, makeName, type) {
  const make = tidy(makeName);
  if (!make) return { draft, error: "Enter a make name." };
  if (make.length > 40) return { draft, error: "Make names can be up to 40 characters." };
  const builtIn = defaultEntry(defaults, make);
  if (builtIn) {
    if ((draft.vehicle_hidden_makes || []).some((name) => sameName(name, make)))
      return { draft: { ...draft, vehicle_hidden_makes: draft.vehicle_hidden_makes.filter((name) => !sameName(name, make)) } };
    return { draft, error: `${builtIn.make} is already in the list.` };
  }
  if (addedIndex(draft, make) >= 0) return { draft, error: `${make} is already in the list.` };
  return { draft: { ...draft, vehicle_added: [...draft.vehicle_added, { make, type, models: [] }] } };
}
export function addModel(defaults, draft, makeName, modelName) {
  const model = tidy(modelName);
  if (!model) return { draft, error: "Enter a model name." };
  if (model.length > 60) return { draft, error: "Model names can be up to 60 characters." };
  const builtIn = defaultEntry(defaults, makeName);
  const hidden = (draft.vehicle_hidden_models || []).find((row) => sameName(row.make, makeName) && sameName(row.model, model));
  if (hidden) return { draft: { ...draft, vehicle_hidden_models: draft.vehicle_hidden_models.filter((row) => row !== hidden) } };
  const current = effectiveCatalog(defaults, draft).find((entry) => sameName(entry.make, makeName));
  if (current?.models.some((row) => sameName(row.name, model))) return { draft, error: `${model} is already listed under ${current.make}.` };
  const index = addedIndex(draft, makeName);
  const added = [...draft.vehicle_added];
  if (index >= 0) added[index] = { ...added[index], models: [...added[index].models, model] };
  else added.push({ make: builtIn?.make || tidy(makeName), type: builtIn?.type || "car", models: [model] });
  return { draft: { ...draft, vehicle_added: added } };
}
export function removeModel(defaults, draft, makeName, modelName) {
  const index = addedIndex(draft, makeName);
  if (index >= 0 && draft.vehicle_added[index].models.some((name) => sameName(name, modelName))) {
    const added = [...draft.vehicle_added];
    added[index] = { ...added[index], models: added[index].models.filter((name) => !sameName(name, modelName)) };
    return { draft: { ...draft, vehicle_added: added } };
  }
  const builtIn = defaultEntry(defaults, makeName);
  if (!builtIn) return { draft };
  return { draft: { ...draft, vehicle_hidden_models: [...draft.vehicle_hidden_models, { make: builtIn.make, model: tidy(modelName) }] } };
}
export function removeMake(defaults, draft, makeName) {
  const builtIn = defaultEntry(defaults, makeName);
  if (!builtIn) return { draft: { ...draft, vehicle_added: draft.vehicle_added.filter((row) => !sameName(row.make, makeName)) } };
  return { draft: { ...draft, vehicle_hidden_makes: [...draft.vehicle_hidden_makes.filter((name) => !sameName(name, makeName)), builtIn.make] } };
}
export function restoreMake(draft, makeName) {
  return { draft: { ...draft, vehicle_hidden_makes: draft.vehicle_hidden_makes.filter((name) => !sameName(name, makeName)) } };
}

// ---- Editing item locations ----
export function rangeNames(prefix, from, to) {
  const start = Number(from), end = Number(to), label = tidy(prefix);
  if (!label) return { error: "Enter a name such as Rack." };
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) return { error: "Enter a start number that is not above the end number." };
  if (end - start >= 200) return { error: "Add at most 200 locations at a time." };
  return { names: Array.from({ length: end - start + 1 }, (_, index) => `${label} ${start + index}`) };
}
export function addLocations(draft, names) {
  const known = new Set(draft.locations.map((row) => lower(row.name)));
  const fresh = [];
  for (const name of names.map(tidy).filter(Boolean)) {
    if (name.length > 40) return { draft, error: "Location names can be up to 40 characters." };
    if (!known.has(lower(name))) { known.add(lower(name)); fresh.push({ id: null, name, active: true }); }
  }
  if (!fresh.length) return { draft, error: "Those locations are already in the list." };
  if (draft.locations.length + fresh.length > 300) return { draft, error: "A company can have at most 300 locations." };
  return { draft: { ...draft, locations: [...draft.locations, ...fresh] } };
}

export function draftFromSetup(setup) {
  return {
    automobile_enabled: !!setup?.automobile_enabled,
    locations: (setup?.locations || []).map((row) => ({ id: row.id, name: row.name, active: row.active })),
    vehicle_added: (setup?.vehicle_added || []).map((row) => ({ make: row.make, type: row.type, models: [...row.models] })),
    vehicle_hidden_makes: [...(setup?.vehicle_hidden_makes || [])],
    vehicle_hidden_models: (setup?.vehicle_hidden_models || []).map((row) => ({ ...row })),
  };
}
export const setupPayload = (version, draft) => ({
  version,
  automobile_enabled: draft.automobile_enabled,
  locations: draft.locations.map((row) => ({ ...(row.id ? { id: row.id } : {}), name: tidy(row.name), active: row.active })),
  vehicle_added: draft.vehicle_added,
  vehicle_hidden_makes: draft.vehicle_hidden_makes,
  vehicle_hidden_models: draft.vehicle_hidden_models,
});
export const draftChanged = (setup, draft) => JSON.stringify(setupPayload(0, draftFromSetup(setup))) !== JSON.stringify(setupPayload(0, draft));
