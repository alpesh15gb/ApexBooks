import React, { useEffect, useRef, useState } from "react";
import { Eye, X } from "lucide-react";
import { revealUnsupported } from "./amountPrivacy.js";

export default function RevealAmountsDialog({ api, onRevealed, onClose }) {
  const [password, setPassword] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const input = useRef(null), opener = useRef(typeof document === "undefined" ? null : document.activeElement);
  useEffect(() => {
    input.current?.focus();
    const previous = opener.current;
    return () => previous?.focus?.();
  }, []);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!password) { setError("Enter your password to show amounts."); input.current?.focus(); return; }
    setBusy(true); setError("");
    try {
      await api("/auth/verify-password", { method: "POST", body: JSON.stringify({ password }) });
      setPassword("");
      onRevealed();
    } catch (failure) {
      if (revealUnsupported(failure)) { setPassword(""); onRevealed(); return; }
      setPassword(""); setBusy(false);
      setError(failure.status === 429 ? "Too many attempts. Wait a few minutes and try again."
        : failure.status === 403 ? "That password is not correct." : failure.message);
      input.current?.focus();
    }
  }
  return (
    <div className="overlay" onMouseDown={e => e.target === e.currentTarget && !busy && onClose()}>
      <form className="modal reveal-amounts" role="dialog" aria-modal="true" aria-labelledby="reveal-amounts-title" onSubmit={submit}
        onKeyDown={e => e.key === "Escape" && !busy && onClose()}>
        <div className="modal-heading">
          <div><h2 id="reveal-amounts-title">Show amounts</h2><p>Enter your account password to show the amounts on this dashboard.</p></div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close" disabled={busy}><X size={19} /></button>
        </div>
        <label>Password
          <input ref={input} type="password" autoComplete="current-password" maxLength={128} value={password} disabled={busy}
            aria-invalid={error ? "true" : undefined} aria-describedby={error ? "reveal-amounts-error" : undefined}
            onChange={e => { setPassword(e.target.value); if (error) setError(""); }} />
        </label>
        {error && <div className="error banner" id="reveal-amounts-error" role="alert">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="button primary" disabled={busy}><Eye size={16} />{busy ? "Checking…" : "Show amounts"}</button>
        </div>
      </form>
    </div>
  );
}
