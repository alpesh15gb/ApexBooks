import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { InventorySetupContext } from "./inventorySetup.js";
import { supportsFeature } from "./capabilities.js";

// Loads the company's item locations and Automobile setting once, and shares them with the item form,
// registers, POS and Settings. Servers without the feature simply provide nothing.
export function useInventorySetupValue(api, companyId, features = []) {
  const supported = supportsFeature(features, "inventory_setup");
  const [setup, setSetup] = useState(null);
  const ticket = useRef(0);
  const reload = useCallback(async () => {
    if (!companyId || !supported) { setSetup(null); return null; }
    const mine = ++ticket.current;
    try {
      const result = await api(`/companies/${companyId}/inventory-setup`);
      if (mine === ticket.current) setSetup(result);
      return result;
    } catch {
      return null;
    }
  }, [api, companyId, supported]);
  useEffect(() => {
    setSetup(null);
    reload();
    return () => { ticket.current++; };
  }, [reload]);
  return useMemo(() => ({ setup, reload, replace: setSetup, supported }), [setup, reload, supported]);
}

export default function InventorySetupProvider({ api, companyId, features = [], children }) {
  const value = useInventorySetupValue(api, companyId, features);
  return <InventorySetupContext.Provider value={value}>{children}</InventorySetupContext.Provider>;
}
