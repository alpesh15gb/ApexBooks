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
export async function sessionFetch(...args) {
  requireCurrentSession(); const token = acceptedToken;
  const verify = () => {
    if (token === acceptedToken && sessionMatches()) return;
    window.dispatchEvent(new window.Event('apex-session-changed'));
    const error = new Error('The sign-in changed while this request was pending. Reload before continuing.');
    error.status = 0; throw error;
  };
  const response = await globalThis.fetch(...args); verify();
  // Check after body decoding too: headers may arrive before another tab signs in.
  return new Proxy(response, {get(target, key) {
    const value = Reflect.get(target, key, target);
    if (['json','blob','arrayBuffer','text'].includes(key) && typeof value === 'function')
      return async (...params) => { const result = await value.apply(target, params); verify(); return result; };
    return typeof value === 'function' ? value.bind(target) : value;
  }});
}
