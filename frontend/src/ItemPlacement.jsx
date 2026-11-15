import React from "react";
import { MapPin, Plus, Trash2 } from "lucide-react";
import { GRADE_LABELS, useInventorySetup } from "./inventorySetup.js";

const yearValue = (value) => (value === null || value === undefined ? "" : String(value));

// Item form section: where the item is kept, and (Automobile module) which vehicles it fits.
export default function ItemPlacement({ form, setForm: replaceForm, disabled, onEdit }) {
  const { setup, supported } = useInventorySetup();
  const setForm = (next) => { replaceForm(next); onEdit?.(); };
  if (!supported || !setup) return null;
  const chosen = form.location_ids || [];
  const options = setup.locations.filter((row) => row.active || chosen.includes(row.id));
  const toggle = (id) => setForm({ ...form, location_ids: chosen.includes(id) ? chosen.filter((value) => value !== id) : [...chosen, id] });
  const atLimit = chosen.length >= (setup.location_limit_per_item || 5);
  const fitment = form.vehicle_fitment || [];
  const setFit = (index, change) => setForm({ ...form, vehicle_fitment: fitment.map((row, at) => (at === index ? { ...row, ...change } : row)) });
  const modelsFor = (make) => (setup.vehicle_options.find((entry) => entry.make.toLowerCase() === String(make || "").trim().toLowerCase())?.models || []);
  return (
    <>
      <fieldset className="full item-placement">
        <legend><MapPin size={15} /> Where it is kept</legend>
        {options.length === 0 ? (
          <p className="inventory-hint">No locations yet. The owner can add them in Settings → Stock & modules.</p>
        ) : (
          <div className="inventory-chips" role="group" aria-label="Item locations">
            {options.map((row) => {
              const on = chosen.includes(row.id);
              return (
                <label key={row.id} className={on ? "chip selected" : "chip"}>
                  <input type="checkbox" checked={on} disabled={disabled || (!on && atLimit)} onChange={() => toggle(row.id)} />
                  {row.name}{row.active ? "" : " (archived)"}
                </label>
              );
            })}
          </div>
        )}
        {atLimit && <p className="inventory-hint">An item can be filed under up to {setup.location_limit_per_item || 5} locations.</p>}
      </fieldset>
      {setup.automobile_enabled && (
        <fieldset className="full item-vehicle">
          <legend>Vehicle details</legend>
          <div className="form-grid">
            <label>Part number (OEM)<input name="oem_number" maxLength={40} value={form.oem_number || ""} disabled={disabled} onChange={(e) => setForm({ ...form, oem_number: e.target.value })} /></label>
            <label>Brand<input name="part_brand" maxLength={40} value={form.part_brand || ""} disabled={disabled} onChange={(e) => setForm({ ...form, part_brand: e.target.value })} /></label>
            <label>Part grade
              <select className="form-select" name="part_grade" value={form.part_grade || ""} disabled={disabled} onChange={(e) => setForm({ ...form, part_grade: e.target.value })}>
                <option value="">Not specified</option>
                {Object.entries(GRADE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          </div>
          <div className="fitment" role="group" aria-label="Vehicles this part fits">
            <strong>Fits these vehicles</strong>
            <datalist id="fitment-makes">{setup.vehicle_options.map((entry) => <option key={entry.make} value={entry.make} />)}</datalist>
            {fitment.length === 0 && <p className="inventory-hint">Add each make and model this part fits. Leave the model blank if it fits every model of that make.</p>}
            {fitment.map((row, index) => (
              <div className="fitment-row" key={index}>
                <label>Make<input aria-label={`Vehicle ${index + 1} make`} list="fitment-makes" maxLength={40} value={row.make || ""} disabled={disabled} onChange={(e) => setFit(index, { make: e.target.value })} /></label>
                <label>Model
                  <input aria-label={`Vehicle ${index + 1} model`} list={`fitment-models-${index}`} maxLength={60} value={row.model || ""} disabled={disabled} onChange={(e) => setFit(index, { model: e.target.value })} />
                  <datalist id={`fitment-models-${index}`}>{modelsFor(row.make).map((model) => <option key={model.name} value={model.name} />)}</datalist>
                </label>
                <label>From<input aria-label={`Vehicle ${index + 1} from year`} inputMode="numeric" maxLength={4} placeholder="Year" value={yearValue(row.year_from)} disabled={disabled}
                  onChange={(e) => setFit(index, { year_from: e.target.value.trim() === "" ? null : Number(e.target.value.replace(/\D/g, "")) || null })} /></label>
                <label>To<input aria-label={`Vehicle ${index + 1} to year`} inputMode="numeric" maxLength={4} placeholder="Year" value={yearValue(row.year_to)} disabled={disabled}
                  onChange={(e) => setFit(index, { year_to: e.target.value.trim() === "" ? null : Number(e.target.value.replace(/\D/g, "")) || null })} /></label>
                <button type="button" className="icon-button" aria-label={`Remove vehicle ${index + 1}`} disabled={disabled} onClick={() => setForm({ ...form, vehicle_fitment: fitment.filter((_, at) => at !== index) })}><Trash2 size={16} /></button>
              </div>
            ))}
            <button type="button" className="button secondary" disabled={disabled || fitment.length >= 60} onClick={() => setForm({ ...form, vehicle_fitment: [...fitment, { make: "", model: "", year_from: null, year_to: null }] })}><Plus size={16} />Add vehicle</button>
          </div>
        </fieldset>
      )}
    </>
  );
}
