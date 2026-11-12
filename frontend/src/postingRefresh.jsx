import React, { useEffect, useRef, useState } from 'react';
export function useBalanceRefresh(refresh) {
  const inFlight = useRef(false);
  const live = useRef(true);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  async function run() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try { await refresh(); }
    catch (reason) { if (live.current) setError(reason.message); }
    finally { inFlight.current = false; if (live.current) setBusy(false); }
  }
  return { run, busy, error };
}
export function BalanceRefreshNotice({state}) {
  return state.error && <div className="info-box" role="alert">The posting was confirmed, but balances could not refresh: {state.error}.<button type="button" disabled={state.busy} onClick={state.run}>Refresh balances</button></div>;
}
