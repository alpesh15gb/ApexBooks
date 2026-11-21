// Memory-only command recovery shared by form instances in one workspace.
export function createCommerceRecovery() {
  let state = {request:null,busy:false,uncertain:false,error:'',completed:false};
  const listeners = new Set();
  return {
    snapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); },
    update: patch => { state = {...state,...patch}; for (const listener of listeners) listener(); },
  };
}
