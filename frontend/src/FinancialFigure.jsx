import React from 'react';

// Preserve the full formatted amount while fitting narrow summary cards.
export default function FinancialFigure({ children }) {
  const text = String(children ?? '—');
  return <strong className="financial-figure" style={{ '--figure-size': `${Math.min(14, 145 / text.length)}cqi` }}>{text}</strong>;
}
