import { businessPeriodDates as periodDates } from "./businessDate.js";
import React from "react";
import { CalendarDays } from "lucide-react";

export { businessDate as localDate, businessPeriodDates as periodDates } from "./businessDate.js";
export default function DateRangeFilter({ value, onChange, allowAll = true }) {
  return (
    <div
      className={`period-controls ${value.period === "custom" ? "custom-period" : ""}`}
    >
      <CalendarDays size={17} aria-hidden="true" />
      <label>
        Period
        <select
          value={value.period}
          onChange={(e) =>
            onChange({
              period: e.target.value,
              ...(e.target.value === "custom"
                ? { from: value.from, to: value.to }
                : periodDates(e.target.value)),
            })
          }
        >
          {allowAll && <option value="all">All dates</option>}
          <option value="today">Today</option>
          <option value="month">This month</option>
          <option value="last_month">Last month</option>
          <option value="year">This financial year</option>
          <option value="custom">Custom dates</option>
        </select>
      </label>
      <label>
        From
        <input
          aria-label="From date"
          type="date"
          value={value.from}
          max={value.to || undefined}
          onInput={(e) =>
            onChange({ ...value, period: "custom", from: e.target.value })
          }
          onChange={(e) =>
            onChange({ ...value, period: "custom", from: e.target.value })
          }
        />
      </label>
      <label>
        To
        <input
          aria-label="To date"
          type="date"
          value={value.to}
          min={value.from || undefined}
          onInput={(e) =>
            onChange({ ...value, period: "custom", to: e.target.value })
          }
          onChange={(e) =>
            onChange({ ...value, period: "custom", to: e.target.value })
          }
        />
      </label>
    </div>
  );
}
