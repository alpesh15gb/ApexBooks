import {createRequestScope} from './requestScope.js';
import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, Clock3, Tag } from 'lucide-react';
export default function PriceHistory({ api, companyId, party, item, side, Modal, close, apply }) {
  const [loaded, setResult] = useState(null), [failed, setError] = useState(null), [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([companyId, party.id, item.item_id, side]);
  const scope = useRef(createRequestScope(key));
  scope.current.setContext(key);
  const result = loaded?.current() ? loaded.value : null;
  const error = failed?.current() ? failed.message : '';
  const applyCurrent = value => { if (loaded?.current()) apply(value); };
  useEffect(() => () => scope.current.setContext(Symbol('unmounted')), []);
  useEffect(() => {
    let active = true;
    const ownsRequest = scope.current.latest();
    const current = () => active && ownsRequest();
    setResult(null); setError(null);
    api(`/companies/${companyId}/parties/${party.id}/item-prices?item_id=${encodeURIComponent(item.item_id)}&side=${side}`)
      .then(value => { if (current()) setResult({value, current}); }).catch(reason => { if (current()) setError({message: reason.message || 'Could not load previous prices.', current}); });
    return () => { active = false; };
  }, [companyId, party.id, item.item_id, side, attempt]);
  const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value || 0));
  return <Modal title="Previous prices" subtitle={`${party.name} · ${item.description} · ${side === 'purchase' ? 'Purchased' : 'Sold'}`} close={close}>
    <p className="info-box">Choose a price to apply to this line. Rates are never changed automatically. Existing documents stay unchanged.</p>
    {error && <div><p className="error" role="alert">{error}</p><button type="button" className="button secondary" onClick={() => setAttempt(value => value + 1)}>Retry prices</button></div>}
    {!result && !error && <p role="status">Finding the last five posted prices…</p>}
    {result && <div className="price-history-list">
      <div className="price-history-row"><Tag size={19} /><div><strong>Catalogue default</strong><small>Excluding tax · before discounts</small></div><strong>{money(result.default_rate)}</strong><button type="button" className="button secondary" onClick={() => applyCurrent({ rate: result.default_rate, price_includes_tax: false })}>Use default<ArrowRight size={14} /></button></div>
      {result.history.map((row, index) => <div className="price-history-row" key={`${row.record_id}-${row.line_index}-${index}`}><Clock3 size={19} /><div><strong>{row.number || 'Posted document'}</strong><small>{row.date} · Qty {row.quantity}</small><small>{row.price_includes_tax ? 'Including tax' : 'Excluding tax'} · GST {row.gst_rate}%</small>{(Number(row.discount_percent) > 0 || Number(row.discount_amount) > 0) && <small>Original discount: {row.discount_percent}% / {money(row.discount_amount)} (not copied)</small>}</div><strong>{money(row.rate)}</strong><button type="button" className="button secondary" onClick={() => applyCurrent({ rate: row.rate, price_includes_tax: row.price_includes_tax })}>Apply price<ArrowRight size={14} /></button></div>)}
      {!result.history.length && <p className="detail-caption">No posted prices for this exact party and item yet. Drafts and other parties are excluded.</p>}
    </div>}
    <div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Keep current price</button></div>
  </Modal>;
}
