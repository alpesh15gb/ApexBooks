import { useEffect, useRef, useState } from 'react';
import { createPostingRequest } from './postingRequest.js';
import { registerPostingRequest } from './postingRegistry.js';

export function usePostingRequest(options) {
  const request = useRef(null);
  request.current ||= createPostingRequest(options);
  const [, redraw] = useState(0);
  useEffect(() => registerPostingRequest(request.current), []);
  const run = async (operation) => {
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
