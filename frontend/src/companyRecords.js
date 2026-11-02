// The API supports bounded pages of 500. Avoid one network round-trip per 100
// records, and stop an obsolete company's scan before requesting another page.
export const COMPANY_PAGE_SIZE = 500;
export async function fetchCompanyRecords(request, companyId, { isCurrent = () => true, signal, onProgress = () => {} } = {}) {
  const rows = [];
  for (let offset = 0; ; offset += COMPANY_PAGE_SIZE) {
    if (!isCurrent() || signal?.aborted) return null;
    const batch = await request(`/companies/${companyId}/records?compact=true&limit=${COMPANY_PAGE_SIZE}&offset=${offset}`, { signal });
    if (!isCurrent() || signal?.aborted) return null;
    rows.push(...batch);
    onProgress(rows.length);
    if (batch.length < COMPANY_PAGE_SIZE) return rows;
  }
}
