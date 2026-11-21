import React from 'react';
const money=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(Number(value));
const known=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value));
export default function DocumentAmounts({record}) {
 const data=record.data||{};
 if(!Array.isArray(data.lines)||!data.lines.length)return null;
 const ready=['taxable','cgst','sgst','igst','round_off'].every(key=>known(data[key]));
 if(!ready)return <section className="detail-section"><h3>Document totals</h3><p>Stored subtotal and tax breakdown are unavailable for this record. The document total above is retained; no tax breakdown has been estimated.</p></section>;
 const rows=[['Subtotal after discounts',data.taxable],...['cgst','sgst','igst'].filter(key=>Number(data[key])!==0).map(key=>[key==='sgst'?'SGST / UTGST':key.toUpperCase(),data[key]]),...(known(data.supplier_tax)&&Number(data.supplier_tax)!==0?[['Supplier tax (unclassified)',data.supplier_tax]]:[]),...(Number(data.round_off)!==0?[['Round off',data.round_off]]:[]),['Document total',record.amount]];
 return <section className="detail-section"><h3>Document totals</h3><dl>{rows.map(([label,value])=><div className="detail-value-row" key={label}><dt>{label}</dt><dd>{money(value)}</dd></div>)}</dl><p className="detail-caption">Stored document amounts. Line and document discounts shown above are already included in the subtotal. These figures do not establish GST eligibility or filing status.</p></section>;
}
