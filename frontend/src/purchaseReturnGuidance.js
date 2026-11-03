// Describe only stored source-line classifications. Missing historical values
// stay unspecified here; the server applies the original posting's fallback.
export function sourceInputTaxSummary(lines) {
  if (!Array.isArray(lines) || !lines.length) return '';
  const counts={pending_review:0,ineligible:0,unspecified:0};
  for (const line of lines) counts[line.itc_treatment === 'pending_review' || line.itc_treatment === 'ineligible' ? line.itc_treatment : 'unspecified']++;
  const labels={pending_review:'input GST pending review',ineligible:'GST included in cost (ineligible)',unspecified:'historical classification unspecified'};
  return Object.entries(counts).filter(([,count])=>count).map(([kind,count])=>`${count} ${count===1?'line':'lines'}: ${labels[kind]}`).join(' · ');
}
