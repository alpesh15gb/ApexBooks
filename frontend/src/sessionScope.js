import {captureCompanyAccess,checkCompanyDenial} from './companyAccess.js';
let acceptedToken = globalThis.localStorage?.token || '';
export function sessionMatches() { return (globalThis.localStorage?.token || '') === acceptedToken; }
export function acceptLocalSession() {
  acceptedToken = globalThis.localStorage?.token || '';
  window.dispatchEvent(new window.Event('apex-session-accepted'));
}
export function requireCurrentSession() {
  if (sessionMatches()) return;
  window.dispatchEvent(new window.Event('apex-session-changed'));
  const error = new Error('Your sign-in changed in another tab. Reload Apex Books before continuing.');
  error.status = 0; throw error;
}
export function captureSession() {
  requireCurrentSession(); const token = acceptedToken;
  return () => {
    if (token === acceptedToken && sessionMatches()) return;
    window.dispatchEvent(new window.Event('apex-session-changed'));
    const error = new Error('The sign-in changed while this request was pending. Reload before continuing.');
    error.status = 0; throw error;
  };
}
export async function sessionFetch(...args) {
  const verifySession = captureSession(); const company = captureCompanyAccess(args[0]);
  const verify = () => { verifySession(); company?.verify(); };
  const response = await globalThis.fetch(...args); verify();
  await checkCompanyDenial(company, response.status, verifySession);
  let body;
  return new Proxy(response, {get(target, key) {
    if (key === 'body' && target.body?.getReader) {
      if (!body) body = new Proxy(target.body, {get(stream, property) {
        if (property === 'getReader') return (...params) => {
          verify(); const reader = stream.getReader(...params);
          return new Proxy(reader, {get(source, method) {
            if (method === 'read') return async (...readArgs) => {
              try { verify(); const result = await source.read(...readArgs); verify(); return result; }
              catch (error) { try { await source.cancel(error); } catch { /* preserve ownership failure */ } throw error; }
            };
            const value = Reflect.get(source, method, source);
            return typeof value === 'function' ? value.bind(source) : value;
          }});
        };
        const value = Reflect.get(stream, property, stream);
        return typeof value === 'function' ? value.bind(stream) : value;
      }});
      return body;
    }
    const value = Reflect.get(target, key, target);
    if (['json','blob','arrayBuffer','text'].includes(key) && typeof value === 'function')
      return async (...params) => { const result = await value.apply(target, params); verify(); return result; };
    return typeof value === 'function' ? value.bind(target) : value;
  }});
}
