// The API supports bounded pages of 500. Avoid one network round-trip per 100
// records, and stop an obsolete company's scan before requesting another page.
export const COMPANY_PAGE_SIZE = 500;
export async function fetchCompanyRecords(request, companyId, { isCurrent = () => true, signal, onProgress = () => {} } = {}) {
  // Offset pagination can overlap when another client posts or reorders a row.
  // Never silently deduplicate: that would conceal a potentially missing row.
  // Retry one complete scan, then keep the last confirmed workspace with an error.
  for (let attempt = 0; attempt < 2; attempt++) {
    const rows = [];
    const seen = new Set();
    if (attempt) onProgress(0);
    let overlap = false;
    for (let offset = 0; ; offset += COMPANY_PAGE_SIZE) {
      if (!isCurrent() || signal?.aborted) return null;
      const batch = await request(`/companies/${companyId}/records?compact=true&limit=${COMPANY_PAGE_SIZE}&offset=${offset}`, { signal });
      if (!isCurrent() || signal?.aborted) return null;
      if (!Array.isArray(batch) || batch.length > COMPANY_PAGE_SIZE || batch.some(row => !row || typeof row !== 'object' || Array.isArray(row) || typeof row.id !== 'string' || !row.id.trim())) {
        throw new Error('Invalid company records response. Refresh again; no partial records were loaded.');
      }
      for (const row of batch) {
        if (seen.has(row.id)) { overlap = true; break; }
        seen.add(row.id);
      }
      if (overlap) break;
      rows.push(...batch);
      onProgress(rows.length);
      if (batch.length < COMPANY_PAGE_SIZE) return rows;
    }
  }
  throw new Error('Company data changed while loading. Refresh again before using these totals; no partial records were loaded.');
}
