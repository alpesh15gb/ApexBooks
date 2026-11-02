import React, {useState} from 'react';

export default function AccountSecurity({onChanged}) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  async function signOutOtherSessions() {
    setBusy(true); setError(''); setNotice('');
    try {
      const response = await fetch('/api/auth/logout-other-sessions', {method: 'POST', headers: {Authorization: `Bearer ${localStorage.token}`}});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || 'Could not end other sessions');
      setNotice(`${data.revoked} other session${data.revoked === 1 ? '' : 's'} signed out.`);
    } catch (err) {setError(err.message);} finally {setBusy(false);}
  }

  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      const response = await fetch('/api/auth/change-password', {method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}`}, body: JSON.stringify({current_password: currentPassword, new_password: newPassword})});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || 'Could not change password');
      setCurrentPassword(''); setNewPassword('');
      onChanged();
    } catch (err) {setError(err.message);}
    finally {setBusy(false);}
  }

  return <div className="settings-section account-security"><h3>Account security</h3><p>Change your password to end every existing sign-in session. You will sign in again.</p><form className="account-security-form" onSubmit={submit}><label>Current password<input type="password" autoComplete="current-password" required value={currentPassword} onChange={event => setCurrentPassword(event.target.value)}/></label><label>New password<input type="password" autoComplete="new-password" minLength="8" maxLength="128" required value={newPassword} onChange={event => setNewPassword(event.target.value)}/></label><button className="button secondary" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button></form><p>End other sign-ins if you no longer use those devices.</p><button type="button" className="button secondary" disabled={busy} onClick={signOutOtherSessions}>Sign out other sessions</button>{notice && <p role="status">{notice}</p>}{error && <div className="error">{error}</div>}</div>;
}
