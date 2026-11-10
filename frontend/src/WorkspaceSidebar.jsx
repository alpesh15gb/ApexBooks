import React, { useEffect, useState } from "react";
import { X } from "lucide-react";

export default function WorkspaceSidebar({ open, onClose, children }) {
  const [compact, setCompact] = useState(() => window.matchMedia?.('(max-width: 1100px)').matches ?? false);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia('(max-width: 1100px)');
    const change = () => { setCompact(media.matches); if (!media.matches) onClose(); };
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, [onClose]);
  return <aside id="workspace-navigation" className={`sidebar ${open ? 'open' : ''}`}
    role={compact && open ? 'dialog' : undefined}
    aria-label="Workspace navigation" aria-modal={compact && open ? true : undefined}
    data-focus-surface={compact && open ? '' : undefined}>
    <button className="icon-button sidebar-close" aria-label="Close" onClick={onClose}><X size={20} /></button>
    {children}
  </aside>;
}
