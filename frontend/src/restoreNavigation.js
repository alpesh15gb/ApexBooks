// A confirmed restore remains committed even if refreshing its navigation fails.
// Check ownership again after the read; never let an older callback select a company.
export async function refreshRestoredCompany({id, readCompanies, current, verify, apply}) {
  const owned = () => {
    if (!current()) return false;
    try { verify(); return true; } catch { return false; }
  };
  if (!owned()) return false;
  let rows;
  try { rows = await readCompanies(); }
  catch (error) { if (!owned()) return false; throw error; }
  if (!owned()) return false;
  if (!Array.isArray(rows) || !rows.some(row => row.id === id)) {
    throw Error('Restore completed, but the restored company is not available in the refreshed company list. Refresh your companies before continuing; do not restore again.');
  }
  apply(rows, id);
  return true;
}
