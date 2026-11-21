import React from "react";
import { MapPin } from "lucide-react";
import { GRADE_LABELS, itemSummary, useInventorySetup } from "./inventorySetup.js";

// Register row detail: where the item is kept, its part number and the vehicles it fits.
export default function ItemMeta({ record }) {
  const { setup } = useInventorySetup();
  const summary = itemSummary(record, setup);
  const part = [summary.oem && `Part ${summary.oem}`, summary.brand, GRADE_LABELS[summary.grade]].filter(Boolean).join(" · ");
  if (!summary.locations.length && !part && !summary.fits.length) return null;
  return (
    <div className="item-meta">
      {summary.locations.length > 0 && <span className="item-meta-line item-meta-location"><MapPin size={12} aria-hidden="true" /> {summary.locations.join(" · ")}</span>}
      {part && <span className="item-meta-line">{part}</span>}
      {summary.fits.length > 0 && (
        <span className="item-meta-line">Fits {summary.fits.slice(0, 2).join(", ")}{summary.fits.length > 2 ? ` +${summary.fits.length - 2} more` : ""}</span>
      )}
    </div>
  );
}
