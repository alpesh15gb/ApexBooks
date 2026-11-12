import React, { useEffect } from 'react';
export class WorkspaceBoundary extends React.Component {
  constructor(props) { super(props); this.state = { failed: false }; }
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.error('Apex Books workspace could not render', error); }
  render() { return this.state.failed ? <main className="auth-page"><section className="auth-form"><div className="auth-box"><h1>Let’s reopen your workspace</h1><p>The page could not be displayed. Reload to reconnect to your saved company data.</p><button className="button primary" onClick={() => window.location.reload()}>Reload Apex Books</button></div></section></main> : this.props.children; }
}

/** Keep the foreground dialog interactive and every background branch inert. */
export function DialogFocus() {
  useEffect(() => {
    let dialog = null, previous = null, scrollStyles = null;
    const parents = [];
    const scrollLock = locked => {
      if (locked && !scrollStyles) {
        scrollStyles = [document.documentElement.style.overflow, document.body.style.overflow];
        document.documentElement.style.overflow = 'hidden';
        document.body.style.overflow = 'hidden';
      } else if (!locked && scrollStyles) {
        [document.documentElement.style.overflow, document.body.style.overflow] = scrollStyles;
        scrollStyles = null;
      }
    };
    const inertNodes = new Map();
    const restore = () => {
      for (const [node, wasInert] of inertNodes) {
        if (wasInert) node.setAttribute('inert', '');
        else node.removeAttribute('inert');
      }
      inertNodes.clear();
    };
    const fields = () => dialog ? [...dialog.querySelectorAll('input,select,textarea,button,a[href],summary,[tabindex]')]
      .filter(node => node.tabIndex >= 0 && !node.matches(':disabled') && !node.closest('[inert]') && node.getClientRects().length) : [];
    const focusInside = () => (fields()[0] || dialog)?.focus();
    const scan = () => {
      const found = [...document.querySelectorAll('.overlay .modal')].at(-1)
        || document.querySelector('[data-focus-surface]') || null;
      if (found === dialog) return;
      let returnFocus = null;
      if (found && parents.at(-1)?.surface === found) returnFocus = parents.pop().focused;
      else if (dialog?.isConnected && found) parents.push({ surface: dialog, focused: document.activeElement });
      restore();
      const wasOpen = !!dialog;
      dialog = found;
      scrollLock(!!dialog);
      if (!dialog) {
        if (wasOpen && previous?.isConnected) previous.focus();
        previous = null;
        parents.length = 0;
        return;
      }
      if (!wasOpen) previous = document.activeElement;
      dialog.setAttribute('tabindex', '-1');
      // Ancestor-aware: dialogs rendered inside a workspace must not inert their
      // own parent. Only siblings off the foreground path are disabled.
      for (let branch = dialog; branch.parentElement && branch !== document.body; branch = branch.parentElement) {
        for (const sibling of branch.parentElement.children) {
          if (sibling === branch || sibling.classList.contains('mobile-backdrop') || ['SCRIPT', 'STYLE', 'LINK'].includes(sibling.tagName)) continue;
          if (!inertNodes.has(sibling)) inertNodes.set(sibling, sibling.hasAttribute('inert'));
          sibling.setAttribute('inert', '');
        }
      }
      const active = dialog;
      requestAnimationFrame(() => {
        if (dialog !== active || !active.isConnected) return;
        if (returnFocus?.isConnected && active.contains(returnFocus) && !returnFocus.matches(':disabled')) returnFocus.focus();
        else focusInside();
      });
    };
    const key = event => {
      if (!dialog) return;
      if (event.key === 'Escape') {
        const close = dialog.querySelector('button[aria-label="Close"]');
        if (close) { event.preventDefault(); event.stopPropagation(); close.click(); }
      }
      const choices = fields();
      if (event.key === 'Tab') {
        const first = choices[0], last = choices.at(-1);
        if (!choices.length) { event.preventDefault(); dialog.focus(); }
        else if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    };
    const focus = event => { if (dialog && !dialog.contains(event.target)) focusInside(); };
    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('keydown', key, true);
    document.addEventListener('focusin', focus, true);
    scan();
    return () => { observer.disconnect(); document.removeEventListener('keydown', key, true); document.removeEventListener('focusin', focus, true); restore(); scrollLock(false); };
  }, []);
  return null;
}
