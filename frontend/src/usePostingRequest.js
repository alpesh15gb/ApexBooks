import { useEffect, useRef, useState } from 'react';
import { createPostingRequest } from './postingRequest.js';
import { registerPostingRequest } from './postingRegistry.js';

export function usePostingRequest(options) {
  // Keep the form's originating session only in memory. A fresh login, even
  // for the same account, is not evidence that an older financial intent may run.
  const session = useRef(globalThis.localStorage?.getItem('token') ?? null);
  const request = useRef(null);
  request.current ||= createPostingRequest(options);
  const [, redraw] = useState(0);
  useEffect(() => registerPostingRequest(request.current), []);
  const run = async (operation) => {
    if ((globalThis.localStorage?.getItem('token') ?? null) !== session.current) {
      // Check on every invocation, not only storage events: another tab can
      // replace the token without this component having rendered again.
      throw new Error('The signed-in session changed. No save was sent. Restore the original session to retry; if it is no longer available, reload and review the original company history before creating another transaction.');
    }
    const promise = request.current.run(operation);
    redraw(n => n + 1);
    try { return await promise; }
    finally { redraw(n => n + 1); }
  };
  return {
    busy: request.current.busy, pending: request.current.pending, run,
    // Recover without rebuilding inputs from a refreshed or removed source row.
    retry: () => request.current.pending ? run() : Promise.resolve(false),
    // Event handlers need authoritative state before React commits a redraw.
    isLocked: () => request.current.busy || request.current.pending,
  };
}
export const pendingPostingMessage = 'The previous response was not confirmed. Your submitted details are locked. Retry the same save to recover its result; do not create another transaction.';
