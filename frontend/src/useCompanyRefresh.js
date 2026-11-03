import { useEffect, useRef, useState } from 'react';
import { hasPendingPostings } from './postingRegistry.js';
import { currentPostingSession } from './postingSession.js';

// Event-driven catch-up only. One intent, one trailing throttle timer, no polling.
export function useCompanyRefresh({ signed, companyId, refresh }) {
  const [deferred, setDeferred] = useState(false);
  const [sessionChanged, setSessionChanged] = useState(false);
  const context = useRef(null);
  const refreshLatest = useRef(refresh);
  refreshLatest.current = refresh;
  useEffect(() => {
    const scope = { companyId, token: currentPostingSession(), pending: false, timer: null, lastStart: 0, active: true };
    context.current = scope;
    setDeferred(false); setSessionChanged(false);
    const cancelTimer = () => { if (scope.timer !== null) clearTimeout(scope.timer); scope.timer = null; };
    const invalidate = () => { cancelTimer(); scope.pending = false; setDeferred(false); setSessionChanged(true); };
    scope.flush = (manual = false) => {
      if (!scope.active || context.current !== scope || !signed || !companyId || !scope.pending) return;
      if (currentPostingSession() !== scope.token) { invalidate(); return; }
      if (document.visibilityState === 'hidden' || document.querySelector('.overlay .modal') || hasPendingPostings()) return;
      const remaining = 1500 - (Date.now() - scope.lastStart);
      if (!manual && remaining > 0) {
        if (scope.timer === null) scope.timer = setTimeout(() => { scope.timer = null; scope.flush(); }, remaining);
        return;
      }
      cancelTimer(); scope.pending = false; scope.lastStart = Date.now();
      setDeferred(false); setSessionChanged(false);
      refreshLatest.current();
    };
    scope.queue = (manual = false) => {
      if (!signed || !companyId || (!manual && document.visibilityState === 'hidden')) return;
      if (currentPostingSession() !== scope.token) { invalidate(); return; }
      scope.pending = true; setDeferred(true); scope.flush(manual);
    };
    const event = () => scope.queue();
    const storage = change => { if (change.key === 'token' || change.key === null) invalidate(); };
    window.addEventListener('focus', event);
    document.addEventListener('visibilitychange', event);
    window.addEventListener('storage', storage);
    return () => {
      scope.active = false; cancelTimer();
      window.removeEventListener('focus', event);
      document.removeEventListener('visibilitychange', event);
      window.removeEventListener('storage', storage);
    };
  }, [signed, companyId]);
  // Main-owned modal/page changes rerender App. Child-only overlays may need an
  // explicit Refresh after closing: deliberately no DOM observer or polling.
  useEffect(() => { context.current?.flush(); });
  return { deferred, sessionChanged, requestRefresh: () => context.current?.queue(true) };
}
