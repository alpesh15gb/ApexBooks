// Capture the originating workspace/session at render, including away-and-back
// generations. A recovered response must never populate another company.
export function inlinePartyCreator({ api, companyId, isCurrent, token, getToken, onCreated }) {
  const current = () => isCurrent() && token === getToken();
  return async (body, key) => {
    if (!current()) throw new Error('Company or session changed. Reopen the invoice in the current workspace.');
    const created = await api(`/companies/${companyId}/records`, {
      method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(body),
    });
    if (!current()) return null;
    if (!created?.id || created.kind !== 'party' || !created.name) throw new Error('Party response could not be confirmed. Retry the same save to recover it.');
    onCreated(created);
    return created;
  };
}
