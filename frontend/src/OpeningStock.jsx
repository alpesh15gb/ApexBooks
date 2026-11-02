import {useState} from 'react';
import {X} from 'lucide-react';

export default function OpeningStock({items, close, save}) {
  const [form, setForm] = useState({item_id: items[0]?.id || '', date: new Date().toLocaleDateString('en-CA'), quantity: '', unit_cost: ''});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const change = event => setForm(current => ({...current, [event.target.name]: event.target.value}));
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {await save(form);} catch (err) {setError(err.message);} finally {setBusy(false);}
  }
  const value = Number(form.quantity || 0) * Number(form.unit_cost || 0);
  return <div className="overlay" onMouseDown={event => event.target === event.currentTarget && close()}>
    <div className="modal" role="dialog" aria-modal="true" aria-label="Opening stock">
      <div className="modal-heading"><div><h2>Opening stock</h2><p>Introduce stock already owned when you begin these books.</p></div><button className="icon-button" aria-label="Close" onClick={close}><X size={18}/></button></div>
      <form className="form-grid" onSubmit={submit}>
        <label className="full">Tracked item<select className="form-select" name="item_id" required value={form.item_id} onChange={change}><option value="">Select an item</option>{items.map(item => <option key={item.id} value={item.id}>{item.name} · {item.data.unit || 'unit'}</option>)}</select></label>
        <label>Date<input name="date" type="date" required value={form.date} onChange={change}/></label>
        <label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" required value={form.quantity} onChange={change}/></label>
        <label>Cost per unit (₹)<input name="unit_cost" type="number" min="0.01" step="0.01" required value={form.unit_cost} onChange={change}/></label>
        <div className="info-box full">Opening value: {new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR'}).format(value)}. This debits inventory and credits opening equity. Post it before the first purchase or sale of this item.</div>
        {error && <div className="error full">{error}</div>}
        <div className="modal-actions full"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={busy || !items.length}>{busy ? 'Posting…' : 'Post opening stock'}</button></div>
      </form>
    </div>
  </div>;
}
