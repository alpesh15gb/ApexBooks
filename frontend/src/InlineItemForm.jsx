import React, { useEffect, useRef } from 'react';
import MasterForm from './MasterForm.jsx';
import { usePostingRequest } from './usePostingRequest.js';

export default function InlineItemForm({ features, createItem, onCreated, close, onLockChange, today }) {
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
      const result = await posting.run(() => createItem(submitted, key));
      if (result && alive.current) onCreated(result.value);
    } finally {
      if (alive.current) onLockChange(posting.isLocked());
    }
  }
  return <MasterForm kind="item" embedded features={features}
    close={close} save={save} locked={posting.pending}
    notice={posting.pending && !posting.busy ? 'The item save response was not confirmed. Details are locked. Retry the same save to recover the result without creating another item.' : 'Creates a reusable item or service and adds a new invoice line. Existing lines stay unchanged. Review the new line before saving your invoice. This does not post the invoice, opening stock or accounting entries. A new stock-tracked item has no stock; record a purchase or opening stock before selling it.'} />;
}
