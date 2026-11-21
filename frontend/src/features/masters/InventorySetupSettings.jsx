import React, { useEffect, useMemo, useState } from "react";
import { Archive, ArchiveRestore, Car, MapPin, Plus, Search, Trash2, X } from "lucide-react";
import {
  addLocations, addMake, addModel, draftChanged, draftFromSetup, effectiveCatalog, rangeNames, removeMake, removeModel,
  restoreMake, setupPayload, tidy, useInventorySetup,
} from "./inventorySetup.js";

const TYPE_ORDER = ["car", "two_wheeler", "commercial", "three_wheeler"];

function Notice({ tone, children }) {
  return children ? <div className={tone === "error" ? "error banner" : "info-box"} role={tone === "error" ? "alert" : "status"}>{children}</div> : null;
}

function LocationsEditor({ draft, setDraft, canEdit }) {
  const [name, setName] = useState(""), [prefix, setPrefix] = useState("Rack"), [from, setFrom] = useState("1"), [to, setTo] = useState("10"), [message, setMessage] = useState("");
  const apply = (result) => { if (result.error) setMessage(result.error); else { setMessage(""); setDraft(result.draft); } return !result.error; };
  const edit = (index, change) => setDraft({ ...draft, locations: draft.locations.map((row, at) => (at === index ? { ...row, ...change } : row)) });
  return (
    <section id="setting-locations" className="inventory-block">
      <h3><MapPin size={17} /> Item locations</h3>
      <p>Name the places you keep stock, such as Rack 1, Shelf B or Counter drawer. Items can then be filed under one or more of them, and shown and searched by location.</p>
      {canEdit && (
        <div className="inventory-add">
          <form className="inventory-inline" onSubmit={(event) => { event.preventDefault(); if (apply(addLocations(draft, [name]))) setName(""); }}>
            <label>New location<input value={name} maxLength={40} placeholder="e.g. Rack 1 · Shelf B" onChange={(e) => setName(e.target.value)} /></label>
            <button className="button secondary" type="submit"><Plus size={16} />Add</button>
          </form>
          <form className="inventory-inline" onSubmit={(event) => { event.preventDefault(); const made = rangeNames(prefix, from, to); if (made.error) setMessage(made.error); else apply(addLocations(draft, made.names)); }}>
            <label>Add a numbered series
              <span className="inventory-range">
                <input aria-label="Series name" value={prefix} maxLength={30} onChange={(e) => setPrefix(e.target.value)} />
                <input aria-label="First number" inputMode="numeric" value={from} onChange={(e) => setFrom(e.target.value)} />
                <span aria-hidden="true">to</span>
                <input aria-label="Last number" inputMode="numeric" value={to} onChange={(e) => setTo(e.target.value)} />
              </span>
            </label>
            <button className="button secondary" type="submit"><Plus size={16} />Add series</button>
          </form>
        </div>
      )}
      <Notice tone="error">{message}</Notice>
      {draft.locations.length === 0 ? (
        <p className="inventory-empty">No locations yet. Add the first one above.</p>
      ) : (
        <ul className="inventory-list" aria-label="Item locations">
          {draft.locations.map((row, index) => (
            <li key={row.id || `new-${index}`} className={row.active ? "" : "is-archived"}>
              <input aria-label={`Location ${index + 1} name`} value={row.name} maxLength={40} disabled={!canEdit} onChange={(e) => edit(index, { name: e.target.value })} />
              {!row.id && <span className="status-badge draft">New</span>}
              {row.id && !row.active && <span className="status-badge cancelled">Archived</span>}
              {canEdit && (
                <span className="inventory-row-actions">
                  <button type="button" className="button secondary" onClick={() => edit(index, { active: !row.active })}>
                    {row.active ? <Archive size={15} /> : <ArchiveRestore size={15} />}{row.active ? "Archive" : "Restore"}
                  </button>
                  <button type="button" className="icon-button" aria-label={`Remove ${row.name}`} onClick={() => setDraft({ ...draft, locations: draft.locations.filter((_, at) => at !== index) })}><Trash2 size={16} /></button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="inventory-hint">Archived locations stay on the items that already use them but cannot be chosen for new items. A location that items use can be archived, not removed.</p>
    </section>
  );
}

function VehicleEditor({ setup, draft, setDraft, canEdit }) {
  const defaults = setup.default_catalog || [];
  const types = setup.vehicle_types || {};
  const [type, setType] = useState("all"), [query, setQuery] = useState(""), [makeName, setMakeName] = useState(""), [makeType, setMakeType] = useState("car"), [message, setMessage] = useState(""), [modelDrafts, setModelDrafts] = useState({});
  const catalog = useMemo(() => effectiveCatalog(defaults, draft), [defaults, draft]);
  const needle = tidy(query).toLowerCase();
  const visible = catalog.filter((entry) => !entry.hidden && (type === "all" || entry.type === type)
    && (!needle || entry.make.toLowerCase().includes(needle) || entry.models.some((model) => model.name.toLowerCase().includes(needle))));
  const hidden = catalog.filter((entry) => entry.hidden);
  const apply = (result) => { if (result.error) setMessage(result.error); else { setMessage(""); setDraft(result.draft); } return !result.error; };
  const total = catalog.filter((entry) => !entry.hidden).reduce((sum, entry) => sum + entry.models.length, 0);
  return (
    <section id="setting-vehicles" className="inventory-block">
      <h3><Car size={17} /> Vehicle makes and models</h3>
      <p>These lists fill the pickers when you describe which vehicles a part fits. They start with {defaults.length} makes and common models for cars, two-wheelers, trucks and three-wheelers. Add your own, and hide any you never sell for.</p>
      <div className="inventory-filter">
        <label className="inventory-search"><Search size={15} /><input aria-label="Search makes and models" placeholder="Search a make or model" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
        <div className="inventory-chips" role="group" aria-label="Vehicle type">
          {["all", ...TYPE_ORDER.filter((key) => types[key])].map((key) => (
            <button key={key} type="button" aria-pressed={type === key} className={type === key ? "chip selected" : "chip"} onClick={() => setType(key)}>{key === "all" ? "All" : types[key]}</button>
          ))}
        </div>
      </div>
      <p className="inventory-hint" role="status">{visible.length} {visible.length === 1 ? "make" : "makes"} shown · {total} models in your list</p>
      {canEdit && (
        <form className="inventory-inline" onSubmit={(event) => { event.preventDefault(); if (apply(addMake(defaults, draft, makeName, makeType))) setMakeName(""); }}>
          <label>Add a make<input value={makeName} maxLength={40} placeholder="e.g. Local Coachworks" onChange={(e) => setMakeName(e.target.value)} /></label>
          <label>Type<select className="form-select" value={makeType} onChange={(e) => setMakeType(e.target.value)}>{TYPE_ORDER.map((key) => <option key={key} value={key}>{types[key] || key}</option>)}</select></label>
          <button className="button secondary" type="submit"><Plus size={16} />Add make</button>
        </form>
      )}
      <Notice tone="error">{message}</Notice>
      <div className="inventory-makes">
        {visible.map((entry) => (
          <details key={entry.make} open={!!needle && entry.models.some((model) => model.name.toLowerCase().includes(needle)) && visible.length < 6}>
            <summary><strong>{entry.make}</strong><span>{types[entry.type] || entry.type} · {entry.models.length} models{entry.custom ? " · yours" : ""}</span></summary>
            <div className="inventory-models">
              {entry.models.map((model) => (
                <span key={model.name} className={model.custom ? "inventory-model is-custom" : "inventory-model"}>
                  {model.name}
                  {canEdit && <button type="button" aria-label={`${model.custom ? "Remove" : "Hide"} ${entry.make} ${model.name}`} onClick={() => apply(removeModel(defaults, draft, entry.make, model.name))}><X size={12} /></button>}
                </span>
              ))}
              {!entry.models.length && <span className="inventory-hint">No models yet.</span>}
            </div>
            {canEdit && (
              <form className="inventory-inline" onSubmit={(event) => { event.preventDefault(); if (apply(addModel(defaults, draft, entry.make, modelDrafts[entry.make] || ""))) setModelDrafts({ ...modelDrafts, [entry.make]: "" }); }}>
                <label>Add a model to {entry.make}<input value={modelDrafts[entry.make] || ""} maxLength={60} onChange={(e) => setModelDrafts({ ...modelDrafts, [entry.make]: e.target.value })} /></label>
                <button className="button secondary" type="submit"><Plus size={16} />Add model</button>
                <button className="button secondary" type="button" onClick={() => apply(removeMake(defaults, draft, entry.make))}>{entry.custom ? <Trash2 size={15} /> : <Archive size={15} />}{entry.custom ? "Remove make" : "Hide make"}</button>
              </form>
            )}
          </details>
        ))}
        {!visible.length && <p className="inventory-empty">No makes match. Clear the search or add the make above.</p>}
      </div>
      {hidden.length > 0 && (
        <details className="inventory-hidden">
          <summary>{hidden.length} hidden make{hidden.length === 1 ? "" : "s"}</summary>
          <ul className="inventory-list">
            {hidden.map((entry) => (
              <li key={entry.make}><span>{entry.make}</span>{canEdit && <button type="button" className="button secondary" onClick={() => apply(restoreMake(draft, entry.make))}><ArchiveRestore size={15} />Show again</button>}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export default function InventorySetupSettings({ api, companyId, canEdit }) {
  const { setup, reload, replace } = useInventorySetup();
  const [draft, setDraft] = useState(() => draftFromSetup(setup));
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState("");
  useEffect(() => { if (setup) setDraft(draftFromSetup(setup)); }, [setup]);
  if (!setup) return <p role="status">Loading stock setup…</p>;
  const changed = draftChanged(setup, draft);
  async function save() {
    if (busy || !canEdit) return;
    setBusy(true); setError(""); setSaved("");
    try {
      const result = await api(`/companies/${companyId}/inventory-setup`, { method: "PUT", body: JSON.stringify(setupPayload(setup.version, draft)) });
      replace(result); setDraft(draftFromSetup(result)); setSaved("Saved. Items and the point of sale now use these settings.");
    } catch (failure) {
      setError(failure.message);
      if (failure.status === 409 && !/used by/.test(failure.message)) await reload();
    } finally { setBusy(false); }
  }
  return (
    <div className="inventory-setup">
      {!canEdit && <Notice>Only the owner can change item locations and business modules. You can see how they are set up.</Notice>}
      <LocationsEditor draft={draft} setDraft={setDraft} canEdit={canEdit} />
      <section id="setting-automobile" className="inventory-block">
        <h3><Car size={17} /> Automobile module</h3>
        <p>Turn this on for a parts counter, workshop, dealer, or tyre and battery shop. Items then get vehicle details: the makes and models a part fits, a part number, brand and grade. Turning it off hides those details but keeps what you entered.</p>
        <label className="stock-toggle">
          <input type="checkbox" checked={draft.automobile_enabled} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, automobile_enabled: e.target.checked })} />
          <span>Automobile shop — add vehicle details to items</span>
        </label>
      </section>
      {draft.automobile_enabled && <VehicleEditor setup={setup} draft={draft} setDraft={setDraft} canEdit={canEdit} />}
      <Notice tone="error">{error}</Notice>
      <Notice>{saved}</Notice>
      {canEdit && (
        <div className="inventory-save">
          <button type="button" className="button primary" disabled={busy || !changed} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
          <button type="button" className="button secondary" disabled={busy || !changed} onClick={() => { setDraft(draftFromSetup(setup)); setError(""); setSaved(""); }}>Discard changes</button>
          {changed && <span className="inventory-hint" role="status">You have unsaved changes.</span>}
        </div>
      )}
    </div>
  );
}
