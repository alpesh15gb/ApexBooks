import { businessDate } from "../../businessDate.js";
import { usePostingRequest, pendingPostingMessage } from "../../usePostingRequest.js";
import {useEffect, useState} from 'react';
import {X} from 'lucide-react';

export default function StockAdjustment({items, api, companyId, canCount = false, close, save, onOpenCount, readOnly = false}) {
  const [form, setForm] = useState({item_id: items[0]?.id || '', date: businessDate(), direction: 'decrease', quantity: '', unit_cost: '', reason: ''});
  const [countMode, setCountMode] = useState(false);
  const [scan, setScan] = useState('');
  const [count, setCount] = useState('');
  const [snapshot, setSnapshot] = useState(null);
  const [snapshotError, setSnapshotError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [needsRecount, setNeedsRecount] = useState(false);
  const [savedCount, setSavedCount] = useState(null);
  // Both stock routes check the original retry key before returning a conflict.
  const posting = usePostingRequest({definitiveRetryStatuses: [409]});
  const { busy, pending } = posting;
  const [submissionKey, setSubmissionKey] = useState(() => crypto.randomUUID());
  const requestClose = () => { if (!busy && !pending) close(); };
  const [error, setError] = useState('');
  const change = event => setForm(current => ({...current, [event.target.name]: event.target.value}));
  const countItems = items.filter(item => (item.data?.item_type || 'goods') === 'goods');
  const snapshotItemId = countMode && !savedCount && countItems.some(item => item.id === form.item_id) ? form.item_id : '';
  const currentSnapshot = snapshot?.item_id === snapshotItemId ? snapshot : null;

  useEffect(() => {
    if (!snapshotItemId) return;
    const controller = new AbortController();
    api(`/companies/${companyId}/stock/counts/${encodeURIComponent(snapshotItemId)}`, {signal: controller.signal})
      .then(value => { if (!controller.signal.aborted) setSnapshot(value); })
      .catch(reason => { if (!controller.signal.aborted) setSnapshotError(reason.message); });
    return () => controller.abort();
  }, [api, companyId, snapshotItemId, refresh]);

  // Work in thousandths to keep fractional counts exact at the API's precision.
  const difference = currentSnapshot && count !== ''
    ? Math.round(Number(count) * 1000) - Math.round(Number(currentSnapshot.on_hand) * 1000)
    : null;
  const increase = countMode ? difference > 0 : form.direction === 'increase';

  function clearCount() {
    setSnapshot(null);
    setSnapshotError('');
    setCount('');
    setNeedsRecount(false);
    setError('');
  }

  function selectItem(id) {
    if (id === form.item_id) return;
    clearCount();
    setForm(current => ({...current, item_id: id, unit_cost: ''}));
  }

  function scanBarcode(event) {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const barcode = scan.trim();
    if (!barcode) return;
    const matches = countItems.filter(item => item.data?.barcode === barcode);
    if (matches.length !== 1) {
      setError(matches.length ? 'More than one item has this barcode. Select the item by name.' : 'No tracked goods match this barcode.');
      return;
    }
    selectItem(matches[0].id);
    setScan('');
    setError('');
  }

  async function submit(event) {
    event.preventDefault();
    if (busy || readOnly || (countMode && !pending && (!difference || needsRecount))) return;
    setError('');
    const unit_cost = increase ? form.unit_cost : null;
    const payload = countMode
      ? {item_id: form.item_id, date: currentSnapshot?.date, stock_snapshot: currentSnapshot?.stock_snapshot, counted_quantity: count, reason: form.reason, unit_cost}
      : {...form, unit_cost};
    try {
      const result = await posting.run(() => save(payload, submissionKey, countMode));
      if (countMode && result?.value?.id) setSavedCount(result.value);
    }
    catch (err) {
      if (countMode && err.status === 409 && /refresh on-hand stock/i.test(err.message)) setNeedsRecount(true);
      setError(err.message);
    }
  }

  function newCount() {
    clearCount();
    setSavedCount(null);
    setScan('');
    setForm(current => ({...current, item_id: '', unit_cost: '', reason: ''}));
    setSubmissionKey(crypto.randomUUID());
  }

  return <div className="overlay" onMouseDown={event => event.target === event.currentTarget && requestClose()}>
    <div className="modal" role="dialog" aria-modal="true" aria-label={countMode ? 'Physical stock count' : 'Stock adjustment'}>
      <div className="modal-heading"><div><h2>{countMode ? 'Physical stock count' : 'Stock adjustment'}</h2><p>{countMode ? 'Count the units physically on hand and review the difference before posting.' : 'Record a stock increase or loss with its reason.'}</p></div><button className="icon-button" aria-label="Close" onClick={requestClose} disabled={busy || pending}><X size={18}/></button></div>
      {savedCount ? <>
        <p role="status">Count posted for {savedCount.name}. On hand after the count was {savedCount.data.stock_count.counted_quantity} {savedCount.data.unit || 'units'}.</p>
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={requestClose}>Done</button>
          {onOpenCount && <button type="button" className="button secondary" onClick={() => onOpenCount(savedCount)}>View {savedCount.number || 'adjustment'}</button>}
          <button type="button" className="button primary" disabled={readOnly} onClick={newCount}>Count another item</button>
        </div>
      </> : <form className="form-grid" onSubmit={submit}>
        <fieldset className="form-grid full submission-fields" disabled={busy || pending || readOnly}>
        {canCount && <label className="full">Entry method<select aria-label="Entry method" className="form-select" value={countMode ? 'count' : 'adjustment'} onChange={event => {
          clearCount();
          setScan('');
          setCountMode(event.target.value === 'count');
          setForm(current => ({...current, unit_cost: ''}));
        }}><option value="adjustment">Adjust by a quantity</option><option value="count">Enter a physical count</option></select></label>}
        {countMode && <label className="full">Scan item barcode<input name="barcode" value={scan} onChange={event => setScan(event.target.value)} onKeyDown={scanBarcode} placeholder="Scan or type a barcode, then press Enter"/></label>}
        <label className="full">Tracked item<select className="form-select" name="item_id" required value={countMode ? snapshotItemId : form.item_id} onChange={event => selectItem(event.target.value)}><option value="">Select an item</option>{(countMode ? countItems : items).map(item => <option key={item.id} value={item.id}>{item.name} · {item.data.unit || 'unit'}</option>)}</select></label>
        {countMode ? <>
          {snapshotItemId && <div className="info-box full">
            <p role={snapshotError ? 'alert' : 'status'}>{snapshotError || (currentSnapshot ? `On hand ${currentSnapshot.on_hand} as of ${currentSnapshot.date}` : 'Loading on-hand quantity…')}</p>
            <button type="button" className="button secondary" onClick={() => { clearCount(); setForm(current => ({...current, unit_cost: ''})); setRefresh(value => value + 1); }}>Refresh on hand</button>
          </div>}
          <label>Counted quantity<input name="counted_quantity" type="number" min="0" max="999999999999.999" step="0.001" required disabled={!currentSnapshot || needsRecount} value={count} onChange={event => setCount(event.target.value)}/></label>
          {difference !== null && !needsRecount && <p role="status">{difference === 0 ? 'Count matches on-hand stock.' : `Stock will ${difference > 0 ? 'increase' : 'decrease'} by ${Math.abs(difference) / 1000}.`}</p>}
        </> : <>
          <label>Date<input name="date" type="date" required value={form.date} onChange={change}/></label>
          <label>Change<select className="form-select" name="direction" value={form.direction} onChange={change}><option value="decrease">Decrease · loss/damage</option><option value="increase">Increase · found stock</option></select></label>
          <label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" required value={form.quantity} onChange={change}/></label>
        </>}
        {increase && <label>Cost per unit (₹)<input name="unit_cost" type="number" min="0.01" step="0.01" required value={form.unit_cost} onChange={change}/></label>}
        <label className="full">Reason<input name="reason" required maxLength="500" value={form.reason} onChange={change} placeholder="e.g. stock count or damage"/></label>
        <div className="info-box full">A decrease uses the current moving average cost and posts an inventory loss. An increase uses the entered cost and posts an inventory gain. Adjustments cannot be backdated before the latest stock movement.</div>
        </fieldset>
        {readOnly && <p className="info-box full" role="status">Read-only access. Your stock draft is preserved; posting requires owner or editor access.</p>}
        {pending && !busy && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
        {error && <div className="error full" role="alert">{error}</div>}
        <div className="modal-actions full"><button type="button" className="button secondary" onClick={requestClose} disabled={busy || pending}>{countMode && difference === 0 ? 'Done' : 'Cancel'}</button><button className="button primary" disabled={busy || readOnly || !items.length || (countMode && !pending && (!difference || needsRecount))}>{busy ? 'Posting…' : 'Post adjustment'}</button></div>
      </form>}
    </div>
  </div>;
}
