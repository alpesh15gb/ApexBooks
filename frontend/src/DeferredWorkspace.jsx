import React, { useEffect, useState } from "react";
import { hasPendingPostings } from "./postingRegistry.js";

/**
 * Fetch a feature only when it is opened, and cache it for later visits.
 * Loading happens outside the rendered feature: a failed chunk cannot replace
 * an already mounted editor or clear its pending posting request.
 */
export function deferWorkspace(importFeature, label) {
  let loaded = null;
  let loading = null;
  function load() {
    if (loaded) return Promise.resolve(loaded);
    if (!loading) {
      loading = Promise.resolve().then(importFeature).then(module => {
        loaded = module.default;
        if (!loaded) throw new Error("Feature module has no component");
        return loaded;
      }).catch(error => {
        loading = null;
        throw error;
      });
    }
    return loading;
  }
  function DeferredWorkspace(props) {
    const [view, setView] = useState(() => ({ Component: loaded, failed: false }));
    const [attempt, setAttempt] = useState(0);
    const [reloadMessage, setReloadMessage] = useState("");
    useEffect(() => {
      if (view.Component) return;
      let active = true;
      setView({ Component: null, failed: false });
      load().then(Component => {
        if (active) setView({ Component, failed: false });
      }).catch(() => {
        if (active) setView({ Component: null, failed: true });
      });
      return () => { active = false; };
    }, [attempt]);
    if (view.Component) return <view.Component {...props} />;
    if (view.failed) return <section className="panel settings-panel" data-workspace-load="failed">
      <div role="alert"><h2>Couldn’t load {label.toLowerCase()}</h2><p>Check your connection and retry. If retry does not work, reload to get the latest app version.</p></div>
      <div className="heading-actions" style={{ marginTop: 16, flexWrap: "wrap" }}>
        <button type="button" className="button primary" onClick={() => { setReloadMessage(""); setView({ Component: null, failed: false }); setAttempt(value => value + 1); }}>Retry loading</button>
        <button type="button" className="button secondary" onClick={() => {
          if (hasPendingPostings()) { setReloadMessage("Finish or retry the pending save before reloading."); return; }
          if (document.querySelector('.overlay .modal')) { setReloadMessage("Close or save your open form before reloading."); return; }
          window.location.reload();
        }}>Reload app</button>
      </div>
      {reloadMessage && <p role="status">{reloadMessage}</p>}
    </section>;
    return <section className="panel settings-panel" role="status" aria-busy="true" data-workspace-load="loading"><p>Loading {label.toLowerCase()}…</p></section>;
  }
  DeferredWorkspace.displayName = `Deferred${label.replace(/\W/g, "")}`;
  return DeferredWorkspace;
}
