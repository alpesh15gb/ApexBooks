import React, {useEffect, useState} from 'react';
import {sessionMatches} from './sessionScope.js';
import {hasPendingPostings} from './postingRegistry.js';
export default function SessionBoundary({children}) {
  const [locked,setLocked]=useState(!sessionMatches());
  useEffect(()=>{
    const check=()=>setLocked(!sessionMatches());
    const storage=event=>{if(event.storageArea===localStorage&&(event.key==='token'||event.key===null))check();};
    window.addEventListener('storage',storage);
    for(const name of ['focus','apex-session-accepted','apex-session-changed'])window.addEventListener(name,check);
    document.addEventListener('visibilitychange',check);
    return()=>{window.removeEventListener('storage',storage);for(const name of ['focus','apex-session-accepted','apex-session-changed'])window.removeEventListener(name,check);document.removeEventListener('visibilitychange',check);};
  },[]);
  return <><div hidden={locked} inert={locked ? true : undefined}>{children}</div>{locked&&<div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="session-change-title"><h2 id="session-change-title">Sign-in changed in another tab</h2><p>This workspace is locked to keep accounts separate. Your drafts remain in memory while this tab stays open.</p><p role="alert">{hasPendingPostings()?'A save may already have posted. Reloading loses its retry details. Check the original company’s transactions before creating it again.':'Reload to use the current sign-in. Reloading discards unsaved drafts.'}</p><button className="button primary" onClick={()=>window.location.reload()}>Reload Apex Books</button></section></div>}</>;
}
