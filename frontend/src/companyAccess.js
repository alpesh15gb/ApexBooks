// Lock one company's in-memory workspace after a current, verified access loss.
// Membership is checked separately: a missing document or owner-only 403 alone
// must not invalidate otherwise authorized books.
let active = '', context = 0, token = '';
const states = new Map();
const state = id => states.get(id) || { epoch: 0, blocked: false };
export function setActiveCompanyAccess(id) {
  const nextToken = globalThis.localStorage?.token || '';
  if (token !== nextToken) { states.clear(); token = nextToken; context++; }
  if (active !== id) { active = id; context++; }
}
export function companyAccessError(status = 403) {
  const error = new Error('Company access was removed or is unavailable. Your unsaved draft is preserved. Refresh company access before continuing.');
  error.status = status; error.companyAccess = true; return error;
}
export function captureCompanyAccess(input) {
  const path = typeof input === 'string' ? input : input?.url;
  const match = path?.match(/(?:^|\/api)\/companies\/([^/?]+)/);
  if (!match) return null;
  const id = decodeURIComponent(match[1]), epoch = state(id).epoch, ownContext = context, wasActive = active === id;
  if (state(id).blocked) throw companyAccessError();
  const verify = () => { if (state(id).blocked || state(id).epoch !== epoch || (wasActive && ownContext !== context)) throw companyAccessError(0); };
  return {id, verify, current: () => active === id && ownContext === context};
}
export function allowCompanyRecovery(id) {
  const previous = state(id); states.set(id, {epoch: previous.epoch + 1, blocked: false});
}
export function blockCompanyAccess(id) {
  if (active !== id) return;
  const previous = state(id); states.set(id, {epoch: previous.epoch + 1, blocked: true});
  window.dispatchEvent(new window.CustomEvent('apex-company-access-lost', {detail: {id}}));
}
export async function checkCompanyDenial(scope, status, verifySession) {
  if (!scope || ![403, 404].includes(status) || !scope.current()) return;
  let companies;
  try {
    const response = await globalThis.fetch('/api/companies', {headers: {Authorization: `Bearer ${globalThis.localStorage?.token || ''}`}});
    verifySession(); scope.verify();
    if (response.ok) companies = await response.json();
    verifySession(); scope.verify();
  } catch { verifySession(); if (!scope.current()) return; }
  if (!scope.current()) return;
  const company = Array.isArray(companies) && companies.find(row => row.id === scope.id);
  if (company) { window.dispatchEvent(new window.CustomEvent('apex-company-access-role', {detail: {company}})); return; }
  blockCompanyAccess(scope.id);
  throw companyAccessError(status);
}
