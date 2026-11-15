import {useEffect, useState} from 'react';

const kinds = {
  stock_opening: 'Opening stock',
  stock_adjustment: 'Stock adjustment',
  purchase_bill: 'Purchase bill',
  debit_note: 'Purchase return',
  sales_invoice: 'Sales invoice',
  pos: 'POS receipt',
  credit_note: 'Sales return',
  stock_return: 'Stock return',
};
const currency = new Intl.NumberFormat('en-IN', {style: 'currency', currency: 'INR'});
const signed = value => Number(value) > 0 ? `+${value}` : value;

export default function StockMovementHistory({api, companyId, item, from, to, onOpen}) {
  const [page, setPage] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [attempt, retry] = useState(0);
  const rowTitle = `Stock movements for ${item.name}`;

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({from_date: from, to_date: to});
    if (page) {
      params.set('before_date', page.date);
      params.set('before_id', page.id);
    }
    api(`/companies/${companyId}/reports/stock/${encodeURIComponent(item.item_id)}/movements?${params}`)
      .then(data => { if (active) setResult(data); })
      .catch(reason => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [api, companyId, item.item_id, from, to, page, attempt]);

  function openPage(value) {
    setResult(null);
    setError('');
    setPage(value);
  }

  return <section aria-label={rowTitle}>
    <h3>{rowTitle}</h3>
    {error ? <div role="alert">{error} <button type="button" className="button secondary" onClick={() => {setError('');retry(value => value + 1);}}>Retry</button></div>
      : !result ? <p role="status">Loading stock movements…</p>
      : result.rows.length ? <div className="table-wrap" tabIndex={0}>
        <table aria-label={rowTitle}>
          <thead><tr><th>Date</th><th>Source</th><th className="right">Quantity change</th><th className="right">Cost change</th></tr></thead>
          <tbody>{result.rows.map(row => {
            const description = `${kinds[row.kind] || row.kind.replaceAll('_', ' ')}${row.number ? ` · ${row.number}` : ''}`;
            return <tr key={row.id}>
              <td>{row.date}</td>
              <td>{onOpen ? <button type="button" className="link" onClick={() => onOpen({id: row.record_id})}>{description}</button> : description}</td>
              <td className="right">{signed(row.quantity)} {item.unit}</td>
              <td className="right">{row.cost_value === null ? 'Unvalued' : currency.format(Number(row.cost_value))}</td>
            </tr>;
          })}</tbody>
        </table>
      </div> : <p>No movements during this period.</p>}
    {page && <button type="button" className="button secondary" onClick={() => openPage(null)}>First page</button>}
    {result?.next && <button type="button" className="button secondary" onClick={() => openPage(result.next)}>Next page</button>}
  </section>;
}
