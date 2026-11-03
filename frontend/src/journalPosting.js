export function journalPostingBlockReason(capabilities) {
  if (!capabilities) return 'Checking API support for safe journal retries. Wait or check support again before posting.';
  if (capabilities.status === 'unverified') return 'Safe journal retry support could not be verified. Retry the API support check; your entered details stay here.';
  if (capabilities.status !== 'verified' || !capabilities.features?.includes('journal_idempotency'))
    return 'The connected API needs an update for safe journal retries. Update the API and check support again before posting a journal or reversal.';
  return '';
}
export function captureJournalRequest(companyId, entry, session, reversalId = null) {
  if (!companyId || !session) throw new Error('Sign in to the original account before posting a journal.');
  if (!entry.date || !entry.reference.trim()) throw new Error('Enter the journal date and reference.');
  if (reversalId) {
    if (!entry.reason.trim()) throw new Error('Enter a reason for the reversal.');
  } else {
    if (!entry.debit_account || !entry.credit_account || entry.debit_account === entry.credit_account) throw new Error('Choose different accounts for debit and credit');
    if (!Number.isFinite(Number(entry.amount)) || Number(entry.amount) <= 0) throw new Error('Enter a positive journal amount.');
  }
  const body = reversalId ? {date:entry.date,reference:entry.reference,reason:entry.reason} : {
    date:entry.date,reference:entry.reference,memo:entry.memo,
    lines:[{account_id:entry.debit_account,debit:entry.amount},{account_id:entry.credit_account,credit:entry.amount}],
  };
  return Object.freeze({
    path:`/companies/${encodeURIComponent(companyId)}/journals${reversalId ? `/${encodeURIComponent(reversalId)}/reverse` : ''}`,
    body:JSON.stringify(body),key:crypto.randomUUID(),session,companyId,reversalId,
  });
}
export async function sendJournalRequest(api, request, currentSession, currentCompany = request.companyId) {
  // Keep credentials in memory only. Never replay under another login context.
  if (currentCompany !== request.companyId) throw new Error("Return to the original company before retrying its journal request.");
  if (currentSession !== request.session) throw new Error('The signed-in session changed. The original journal request remains locked; recover the original session before retrying.');
  const response = await api(request.path,{method:'POST',body:request.body,headers:{'Idempotency-Key':request.key,Authorization:`Bearer ${request.session}`}});
  const original = JSON.parse(request.body);
  if (!response || typeof response.id !== 'string' || !response.id.trim() || response.reference !== original.reference.trim() ||
      (request.reversalId ? response.reversal_of !== request.reversalId : response.date !== original.date))
    throw new Error('The journal response could not be verified. Keep the original request and retry to recover its confirmed result.');
  return response;
}
const DEFINITE_JOURNAL_CONFLICTS = new Set([
  'Journal retry key was used for a different request',
  'Journal reference already exists',
  'Journal is already reversed or is itself a reversal',
  'Reference already exists or journal was already reversed',
  'Date is in a locked accounting period',
  'Reverse source documents through their document workflow',
]);
export function isDefiniteJournalConflict(error) {
  return error?.status === 409 && DEFINITE_JOURNAL_CONFLICTS.has(error.message);
}
export const journalReconciliationWarning = 'This attempt was rejected, but an earlier interrupted attempt may have completed. Review journal history and reconcile the result before changing the reference or starting a new request.';
