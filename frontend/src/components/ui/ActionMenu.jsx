import React, { useEffect, useId, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";

/** The top layer keeps register actions clear of scrolling table boundaries. */
export default function ActionMenu({ label, actions }) {
  const id = useId();
  const trigger = useRef(null), menu = useRef(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const dismiss = event => { if (event.type === 'resize' || !menu.current?.contains(event.target)) menu.current?.hidePopover?.(); };
    window.addEventListener('scroll', dismiss, true);
    window.addEventListener('resize', dismiss);
    return () => { window.removeEventListener('scroll', dismiss, true); window.removeEventListener('resize', dismiss); };
  }, [open]);
  const items = () => [...menu.current.querySelectorAll('button:not(:disabled)')];
  function close(restore = false) {
    menu.current?.hidePopover?.();
    if (restore) trigger.current?.focus();
  }
  function show(last = false) {
    const surface = menu.current;
    surface.showPopover();
    const rect = trigger.current.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom - 16;
    const above = rect.top - 16;
    const upward = below < Math.min(surface.scrollHeight, 220) && above > below;
    surface.style.maxHeight = `${Math.max(48, upward ? above : below)}px`;
    surface.style.left = `${Math.max(12, Math.min(rect.right - surface.offsetWidth, window.innerWidth - surface.offsetWidth - 12))}px`;
    surface.style.top = `${upward ? Math.max(12, rect.top - surface.offsetHeight - 6) : rect.bottom + 6}px`;
    (last ? items().at(-1) : items()[0])?.focus();
  }
  return <>
    <button ref={trigger} className="row-menu-trigger" aria-label={label} title="More actions"
      aria-haspopup="menu" aria-expanded={open} aria-controls={id}
      onClick={() => open ? close() : show()}
      onKeyDown={event => {
        if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); show(event.key === "ArrowUp"); }
      }}><MoreHorizontal size={17} /></button>
    <div ref={menu} id={id} popover="auto" className="action-menu" role="menu" aria-label={label}
      onToggle={event => setOpen(event.newState === "open")}
      onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) close(); }}
      onKeyDown={event => {
        const choices = items(), index = choices.indexOf(document.activeElement);
        const next = { ArrowDown: (index + 1) % choices.length, ArrowUp: (index - 1 + choices.length) % choices.length, Home: 0, End: choices.length - 1 }[event.key];
        if (next !== undefined) { event.preventDefault(); choices[next]?.focus(); }
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(true); }
        if (event.key === "Tab") close(true);
      }}>
      {actions.map(action => <button key={action.key} role="menuitem" tabIndex={-1} disabled={action.disabled}
        onClick={() => { close(true); action.run(); }}>{action.label}</button>)}
    </div>
  </>;
}
