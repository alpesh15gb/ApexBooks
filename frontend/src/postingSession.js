export function currentPostingSession() {
  return globalThis.localStorage?.getItem('token') ?? null;
}

export function assertPostingSession(session, phase = 'send') {
  if (currentPostingSession() === session) return;
  const message = phase === 'send'
    ? 'The signed-in session changed. No save was sent.'
    : 'The signed-in session changed while this request was running. Its response was not applied here; the original request may have completed.';
  const error = new Error(`${message} Restore the original session to retry; if it is no longer available, reload and review the original company history before creating another transaction.`);
  // Never expose an old response's 401/403 to replacement-session handlers or
  // treat it as proof that an uncertain financial command did not commit.
  error.status = 0;
  error.code = 'POSTING_SESSION_CHANGED';
  throw error;
}
