import React from 'react';
const money=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(Number(value));
export default function StockRecordSummary({record}) {
 const data=record.data||{},opening=record.kind==='stock_opening';
 const decrease=data.direction==='decrease',increase=data.direction==='increase';
 const quantity=data.quantity==null?'Not recorded':`${!opening&&decrease?'−':!opening&&increase?'+':''}${data.quantity} ${data.unit||'units'}`;
 return <section className="detail-section"><h3>{opening?'Opening stock':'Stock adjustment'}</h3><dl><div className="detail-value-row"><dt>Item</dt><dd>{record.name}</dd></div><div className="detail-value-row"><dt>{opening?'Opening quantity':decrease||increase?'Quantity change':'Recorded quantity (direction unavailable)'}</dt><dd>{quantity}</dd></div><div className="detail-value-row"><dt>Recorded unit cost</dt><dd>{data.unit_cost!=null&&data.unit_cost!==''?money(data.unit_cost):'Not separately recorded'}</dd></div><div className="detail-value-row"><dt>Stock value {decrease?'removed':opening||increase?'introduced':'(direction unavailable)'}</dt><dd>{money(record.amount)}</dd></div></dl>{data.reason&&<p>Reason: {data.reason}</p>}<p className="detail-caption">This records a stock movement, not a payment. Current stock and historical balances are available in inventory reports.</p></section>;
}
