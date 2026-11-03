export function bankUnmatchBlockReason(capabilities) {
  if (!capabilities) return 'Checking API support for protected bank unmatching. Wait or check support again.';
  if (capabilities.status === 'unverified') return 'Protected bank unmatching could not be verified. Retry the API support check; existing matches remain unchanged.';
  if (capabilities.status !== 'verified' || !capabilities.features?.includes('bank_match_revisions'))
    return 'The connected API needs an update for protected bank unmatching. Update the API and check support again before removing a whole-line match.';
  return '';
}
export function captureBankUnmatch(companyId, line) {
  if (typeof companyId !== 'string' || !companyId || typeof line?.id !== 'string' || !line.id || typeof line.matched_record_id !== 'string' || !line.matched_record_id)
    throw new Error('The reviewed bank match is unavailable. Reload the statement before unmatching.');
  if (!Number.isSafeInteger(line.match_revision) || line.match_revision < 0)
    throw new Error('The bank match revision is missing or invalid. Reload the statement from an updated API before unmatching.');
  return Object.freeze({
    path: `/companies/${encodeURIComponent(companyId)}/bank-statement/${encodeURIComponent(line.id)}/match`,
    body: JSON.stringify({expected_record_id:line.matched_record_id,expected_match_revision:line.match_revision}),
  });
}
export function bankMatchRowBlockReason(line) {
  try { captureBankUnmatch('checked-company', line); return ''; }
  catch (error) { return error.message; }
}
export function isChangedBankMatch(error) {
  return error?.status === 409 && error.message === 'Bank match changed; reload the statement and review its current match';
}
