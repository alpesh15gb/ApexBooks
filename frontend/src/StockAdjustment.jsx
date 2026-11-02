import {useState} from 'react';
import {X} from 'lucide-react';

export default function StockAdjustment({items, close, save}) {
  const [form, setForm] = useState({item_id: items[0]?.id || '', date: new Date().toLocaleDateString('en-CA'), direction: 'decrease', quantity: '', unit_cost: '', reason: ''});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = event => setForm(current => ({...current, [event.target.name]: event.target.value}));
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {await save({...form, unit_cost: form.direction === 'increase' ? form.unit_cost : null});}
    catch (err) {setError(err.message);} finally {setBusy(false);}
  }
  return <div className="overlay" onMouseDown={event => event.target === event.currentTarget && close()}>
    <div className="modal" role="dialog" aria-modal="true" aria-label="Stock adjustment">
      <div className="modal-heading"><div><h2>Stock adjustment</h2><p>Record a counted increase or loss with its reason.</p></div><button className="icon-button" aria-label="Close" onClick={close}><X size={18}/></button></div>
      <form className="form-grid" onSubmit={submit}>
        <label className="full">Tracked item<select className="form-select" name="item_id" required value={form.item_id} onChange={change}><option value="">Select an item</option>{items.map(item => <option key={item.id} value={item.id}>{item.name} · {item.data.unit || 'unit'}</option>)}</select></label>
        <label>Date<input name="date" type="date" required value={form.date} onChange={change}/></label>
        <label>Change<select className="form-select" name="direction" value={form.direction} onChange={change}><option value="decrease">Decrease · loss/damage</option><option value="increase">Increase · found stock</option></select></label>
        <label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" required value={form.quantity} onChange={change}/></label>
        {form.direction === 'increase' && <label>Cost per unit (₹)<input name="unit_cost" type="number" min="0.01" step="0.01" required value={form.unit_cost} onChange={change}/></label>}
        <label className="full">Reason<input name="reason" required maxLength="500" value={form.reason} onChange={change} placeholder="e.g. stock count or damage"/></label>
        <div className="info-box full">A decrease uses the current moving average cost and posts an inventory loss. An increase uses the entered cost and posts an inventory gain. Adjustments cannot be backdated before the latest stock movement.</div>
        {error && <div className="error full">{error}</div>}
        <div className="modal-actions full"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={busy || !items.length}>{busy ? 'Posting…' : 'Post adjustment'}</button></div>
      </form>
    </div>
  </div>;
}
