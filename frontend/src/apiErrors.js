export function apiErrorMessage(status, payload = {}, mutation = false) {
  const recovery = mutation ? ' Retry the same save to recover its result; do not create another transaction.' : ' Please retry shortly.';
  if (status === 0) return 'Cannot reach Apex Books. Check your connection.' + (mutation ? recovery : ' Try refreshing when you are connected.');
  if (status === 408) return 'The request timed out.' + recovery;
  if (status >= 500) return 'The service is temporarily unavailable.' + recovery;
  if (status === 429) return 'Too many requests. Please wait a moment and try again.';
  if (typeof payload.detail === 'string') return payload.detail;
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail.slice(0, 3).map(item => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean);
    if (messages.length) return messages.join(' · ');
  }
  if (status === 401) return 'Your session has ended. Sign in again.';
  if (status === 403) return 'Your account does not have permission for this action.';
  if (status === 404) return 'This record or company is no longer available to your account.';
  if (status === 409) return 'This record changed. Refresh and review it before trying again.';
  return 'Please check your details and try again.';
}
