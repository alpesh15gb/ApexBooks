import React, { useEffect, useRef } from 'react';
import MasterForm from './MasterForm.jsx';
import { usePostingRequest } from './usePostingRequest.js';

export default function InlinePartyForm({ features, initialName, createParty, onCreated, close, onLockChange, today }) {
  const posting = usePostingRequest();
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onLockChange(posting.busy || posting.pending); }, [posting.busy, posting.pending, onLockChange]);
  async function save(body) {
    onLockChange(true);
    const key = crypto.randomUUID();
    // Avoid a server-default date changing the idempotency hash after midnight.
    const submitted = { ...body, date: today() };
    try {
      const result = await posting.run(() => createParty(submitted, key));
      if (result && alive.current) onCreated(result.value);
    } finally {
      if (alive.current) onLockChange(posting.isLocked());
    }
  }
  return <MasterForm kind="party" embedded initialName={initialName} features={features}
    close={close} save={save} locked={posting.pending}
    notice={posting.pending && !posting.busy ? 'The party save response was not confirmed. Details are locked. Retry the same save to recover the result without creating another party.' : 'Your invoice stays open. Creating a party does not save or post the invoice.'} />;
}
