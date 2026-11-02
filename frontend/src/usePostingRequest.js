import { useRef, useState } from 'react';
import { createPostingRequest } from './postingRequest.js';

export function usePostingRequest() {
  const request = useRef(null);
  request.current ||= createPostingRequest();
  const [, redraw] = useState(0);
  const run = async (operation) => {
    const promise = request.current.run(operation);
    redraw(n => n + 1);
    try { return await promise; }
    finally { redraw(n => n + 1); }
  };
  return { busy: request.current.busy, pending: request.current.pending, run };
}
export const pendingPostingMessage = 'The previous response was not confirmed. Your submitted details are locked. Retry the same save to recover its result; do not create another transaction.';
