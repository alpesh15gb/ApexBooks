import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Menu,
  Plus,
  Search,
  UsersRound,
  Package,
  ShoppingBag,
  Wallet,
  X,
} from "lucide-react";
import { SHORTCUTS, isHelpKey, shortcutFor } from "./shortcuts.js";

export default function WorkspaceHeader({
  company,
  page,
  labels,
  records,
  onNavigate,
  onOpenRecord,
  onCreate,
  onMenu,
  menuOpen = false,
  onCreateMenuChange,
}) {
  const [query, setQuery] = useState(""),
    [open, setOpen] = useState(false),
    [create, setCreate] = useState(false),
    [active, setActive] = useState(0),
    [help, setHelp] = useState(false);
  const actions = useRef({});
  actions.current = { onNavigate, onCreate };
  const input = useRef(null),
    searchBox = useRef(null),
    createBox = useRef(null),
    createTrigger = useRef(null);
  const canWrite = ["owner", "editor"].includes(company?.role);
  useEffect(() => { onCreateMenuChange?.(create); }, [create]);
  useEffect(() => {
    if (create) createBox.current?.querySelector('[role="menuitem"]')?.focus();
  }, [create]);
  useEffect(() => {
    setOpen(false);
    setQuery("");
    setCreate(false);
  }, [company?.id, page]);
  useEffect(() => {
    const openFromSidebar = () => {
      createTrigger.current = document.querySelector('.sidebar-create');
      setCreate(value => !value);
    };
    window.addEventListener('apex-open-create', openFromSidebar);
    function key(e) {
      const blocked = !!document.querySelector('[aria-modal="true"], .overlay, .modal');
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        if (blocked) return;
        e.preventDefault();
        input.current?.focus();
        setOpen(true);
      }
      if (e.key === "Escape") {
        setOpen(false);
        setCreate(false);
        setHelp(false);
      }
      // Alt+N new invoice, Alt+R payment, Alt+D day book … never while an editor or dialog is open.
      const shortcut = shortcutFor(e, blocked);
      if (shortcut) {
        e.preventDefault();
        if (shortcut.action === "create") actions.current.onCreate?.(shortcut.target);
        else actions.current.onNavigate?.(shortcut.target);
      } else if (!blocked && isHelpKey(e)) {
        e.preventDefault();
        setHelp((value) => !value);
      }
    }
    function outside(e) {
      if (!searchBox.current?.contains(e.target)) setOpen(false);
      if (!createBox.current?.contains(e.target) && !e.target.closest('.sidebar-create')) setCreate(false);
    }
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", outside);
    return () => {
      window.removeEventListener('apex-open-create', openFromSidebar);
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", outside);
    };
  }, []);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pages = Object.entries(labels)
      .filter(
        ([k, name]) =>
          !["stock_opening", "stock_adjustment", "bank_transfer"].includes(k) &&
          name.toLowerCase().includes(q),
      )
      .slice(0, q ? 4 : 5)
      .map(([kind, title]) => ({
        key: "page-" + kind,
        kind,
        title,
        note: "Workspace",
        icon:
          kind === "party" ? UsersRound : kind === "item" ? Package : FileText,
      }));
    const rows = q
      ? records
          .filter((r) => `${r.name} ${r.number}`.toLowerCase().includes(q))
          .slice(0, 7)
          .map((r) => ({
            key: r.id,
            record: r,
            kind: r.kind,
            title: r.number || r.name,
            reference: r.number || r.name,
            note: `${r.name} · ${labels[r.kind] || r.kind.replaceAll("_", " ")}`,
            icon: r.kind === "party" ? UsersRound : FileText,
          }))
      : [];
    return [...pages, ...rows].slice(0, 9);
  }, [query, records, labels]);
  function select(result) {
    if (result.record && onOpenRecord) onOpenRecord(result.record);
    else onNavigate(result.kind, result.reference || "");
    setOpen(false);
    setQuery("");
    input.current?.blur();
  }
  const creation = [
    ["sales_invoice", "Sales invoice", FileText],
    ["purchase_bill", "Purchase bill", ShoppingBag],
    ["payment_in", "Payment in", Wallet],
    ["payment_out", "Payment out", Wallet],
    ["estimate", "Estimate", FileText],
    ["sales_order", "Sales order", FileText],
    ["proforma", "Proforma invoice", FileText],
    ["expense", "Expense", ShoppingBag],
    ["purchase_order", "Purchase order", ShoppingBag],
    ["credit_note", "Credit note", FileText],
    ["debit_note", "Debit note", FileText],
    ["party", "New party", UsersRound],
    ["item", "New item", Package],
  ];
  return (
    <header className="topbar workspace-topbar">
      <button
        className="mobile-menu icon-button"
        onClick={onMenu}
        aria-label="Open menu"
        aria-expanded={menuOpen}
        aria-controls="workspace-navigation"
      >
        <Menu size={21} />
      </button>
      <div className="workspace-location">
        <span>Apex Books</span>
        <ChevronRight size={13} />
        <strong>{labels[page] || "Overview"}</strong>
      </div>
      <div className="workspace-search" ref={searchBox} onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}>
        <Search size={17} />
        <input
          ref={input}
          role="combobox"
          aria-label="Search workspace"
          aria-expanded={open}
          aria-controls="workspace-search-results"
          aria-autocomplete="list"
          aria-activedescendant={
            open && matches[active]
              ? `workspace-search-option-${active}`
              : undefined
          }
          placeholder="Search transactions, parties, items…"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((x) => open ? Math.max(0, Math.min(matches.length - 1, x + 1)) : 0);
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setOpen(true);
              setActive((x) => Math.max(0, x - 1));
            }
            if (e.key === "Enter" && open && matches[active]) { e.preventDefault(); select(matches[active]); }
          }}
        />
        {query ? (
          <button
            aria-label="Clear workspace search"
            onClick={() => {
              setQuery("");
              setActive(0);
              input.current?.focus();
            }}
          >
            <X size={14} />
          </button>
        ) : (
          <kbd>Ctrl K</kbd>
        )}
        {open && (
          <div
            className="workspace-search-results"
            id="workspace-search-results"
            role="listbox"
            aria-label="Workspace search results"
          >
            <span className="search-heading">
              {query ? "SEARCH RESULTS" : "JUMP TO YOUR WORKSPACE"}
            </span>
            {matches.length ? (
              matches.map((r, i) => (
                <button
                  key={r.key}
                  id={`workspace-search-option-${i}`}
                  role="option"
                  tabIndex={-1}
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={event => event.preventDefault()}
                  onClick={() => select(r)}
                >
                  <r.icon size={18} />
                  <span>
                    <strong>{r.title}</strong>
                    <small>{r.note}</small>
                  </span>
                  <ChevronRight size={14} />
                </button>
              ))
            ) : (
              <p>No matching transactions or pages.</p>
            )}
            <small className="search-hint">
              ↑ ↓ to move · Enter to open · Esc to close
            </small>
          </div>
        )}
      </div>
      <div className="workspace-header-actions">
        <div className="create-control" ref={createBox}>
          <button
            className="button primary global-create"
            aria-label="Create"
            disabled={!canWrite}
            aria-haspopup="menu"
            aria-expanded={create}
            onKeyDown={event => {
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                createTrigger.current = event.currentTarget;
                setCreate(true);
              }
            }}
            onClick={event => { createTrigger.current = event.currentTarget; setCreate((x) => !x); }}
          >
            <Plus size={18} />
            <span>Create</span>
            <ChevronDown size={13} />
          </button>
          {create && (
            <div
              className="create-menu"
              role="menu"
              aria-label="Create a transaction"
              onKeyDown={event => {
                const items = [...event.currentTarget.querySelectorAll('[role="menuitem"]')];
                const index = items.indexOf(document.activeElement);
                let next;
                if (event.key === "ArrowDown") next = (index + 1) % items.length;
                if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
                if (event.key === "Home") next = 0;
                if (event.key === "End") next = items.length - 1;
                if (next !== undefined) { event.preventDefault(); items[next]?.focus(); }
                if (event.key === "Escape" || event.key === "Tab") {
                  if (event.key === "Escape") event.preventDefault();
                  setCreate(false);
                  (createTrigger.current || createBox.current?.querySelector('.global-create'))?.focus();
                }
              }}
            >
              <span className="search-heading">What would you like to create?</span>
              <div className="create-groups">
                {[
                  ['Sales', ['sales_invoice', 'payment_in', 'estimate', 'sales_order', 'proforma', 'credit_note']],
                  ['Purchases', ['purchase_bill', 'payment_out', 'expense', 'purchase_order', 'debit_note']],
                  ['Directory', ['party', 'item']],
                ].map(([group, kinds]) => <div key={group} role="group" aria-label={group}><span className="create-group-title">{group}</span>{creation.filter(([kind]) => kinds.includes(kind)).map(([kind, title, Icon]) => (
                  <button
                    key={kind}
                    role="menuitem"
                    tabIndex={-1}
                    onClick={() => {
                      (createTrigger.current || createBox.current?.querySelector('.global-create'))?.focus();
                      setCreate(false);
                      onCreate(kind);
                    }}
                  >
                    <Icon size={17} />
                    {title}
                  </button>
                ))}</div>)}
              </div>
            </div>
          )}
        </div>
        <button
          className="workspace-profile"
          onClick={() => onNavigate("settings")}
          aria-label="Open company settings"
        >
          <span className="avatar">
            {company?.name?.[0]?.toUpperCase() || "A"}
          </span>
          <span>
            <strong>{company?.name || "Your company"}</strong>
            <small>
              {company?.role || "Company"} ·{" "}
              {company?.tax_mode === "regular"
                ? "GST registered"
                : company?.tax_mode === "composition"
                  ? "Composition"
                  : "Non-GST"}
            </small>
          </span>
          <ChevronDown size={13} />
        </button>
      </div>
      <button type="button" className="icon-button shortcut-hint" aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" onClick={() => setHelp(true)}>?</button>
      {help && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setHelp(false); }}>
          <section className="modal shortcut-help" role="dialog" aria-modal="true" aria-labelledby="shortcut-title">
            <header><h2 id="shortcut-title">Keyboard shortcuts</h2><button type="button" className="icon-button" aria-label="Close" onClick={() => setHelp(false)}><X size={18} /></button></header>
            <dl>
              {SHORTCUTS.map((s) => <React.Fragment key={s.key}><dt><kbd>Alt</kbd> + <kbd>{s.key.toUpperCase()}</kbd></dt><dd>{s.label}</dd></React.Fragment>)}
              <dt><kbd>Ctrl</kbd> + <kbd>K</kbd></dt><dd>Search everything</dd>
              <dt><kbd>Ctrl</kbd> + <kbd>Enter</kbd></dt><dd>Save the open document</dd>
              <dt><kbd>Esc</kbd></dt><dd>Close menus and dialogs</dd>
              <dt><kbd>?</kbd></dt><dd>Show this list</dd>
            </dl>
          </section>
        </div>
      )}
    </header>
  );
}
