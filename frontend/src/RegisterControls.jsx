import React, { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import DateRangeFilter from "./DateRangeFilter.jsx";

export default function RegisterControls({
  value,
  onChange,
  records,
  onReset,
}) {
  const [expanded, setExpanded] = useState(false);
  const extraFilters = Number(!!value.party) + Number(!!value.sort && value.sort !== "newest");
  const parties = [...new Set(records.map((r) => r.name).filter(Boolean))].sort(
    (a, b) => a.localeCompare(b),
  );
  return (
    <div
      className={`register-controls panel ${expanded ? "expanded-controls" : ""}`}
    >
      <DateRangeFilter
        value={value}
        onChange={(dates) => onChange({ ...value, ...dates })}
      />
      <button
        className="mobile-filter-toggle link"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        <SlidersHorizontal size={15} />
        {expanded ? "Fewer filters" : "More filters"}
        {extraFilters > 0 && <span className="filter-count">{extraFilters} active</span>}
      </button>
      <label>
        Party
        <select
          className="form-select"
          value={value.party}
          onChange={(e) => onChange({ ...value, party: e.target.value })}
        >
          <option value="">All parties</option>
          {parties.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      </label>
      <label>
        Sort by
        <select
          className="form-select"
          value={value.sort}
          onChange={(e) => onChange({ ...value, sort: e.target.value })}
        >
          <option value="newest">Date · newest first</option>
          <option value="oldest">Date · oldest first</option>
          <option value="amount">Amount · high to low</option>
          <option value="balance">Balance · high to low</option>
        </select>
      </label>
      <button
        className={`link reset-filters ${extraFilters ? "has-active-filters" : ""}`}
        onClick={() =>
          onReset
            ? onReset()
            : onChange({
                period: "all",
                from: "",
                to: "",
                party: "",
                sort: "newest",
              })
        }
      >
        <SlidersHorizontal size={15} />
        Reset filters
      </button>
    </div>
  );
}
