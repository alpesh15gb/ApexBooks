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

export default function WorkspaceHeader({
  company,
  page,
  labels,
  records,
  onNavigate,
  onCreate,
  onMenu,
}) {
  const [query, setQuery] = useState(""),
    [open, setOpen] = useState(false),
    [create, setCreate] = useState(false),
    [active, setActive] = useState(0);
  const input = useRef(null),
    searchBox = useRef(null),
    createBox = useRef(null);
  const canWrite = ["owner", "editor"].includes(company?.role);
  useEffect(() => {
    setOpen(false);
    setQuery("");
    setCreate(false);
  }, [company?.id, page]);
  useEffect(() => {
    function key(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
        setOpen(true);
      }
      if (e.key === "Escape") {
        setOpen(false);
        setCreate(false);
      }
    }
    function outside(e) {
      if (!searchBox.current?.contains(e.target)) setOpen(false);
      if (!createBox.current?.contains(e.target)) setCreate(false);
    }
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", outside);
    return () => {
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
            kind: r.kind,
            title: r.name,
            reference: r.number || r.name,
            note: `${r.number || ""} · ${labels[r.kind] || r.kind.replaceAll("_", " ")}`,
            icon: r.kind === "party" ? UsersRound : FileText,
          }))
      : [];
    return [...pages, ...rows].slice(0, 9);
  }, [query, records, labels]);
  function select(result) {
    onNavigate(result.kind, result.reference || "");
    setOpen(false);
    setQuery("");
    input.current?.blur();
  }
  const creation = [
    ["sales_invoice", "Sales invoice", FileText],
    ["purchase_bill", "Purchase bill / OCR", ShoppingBag],
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
      >
        <Menu size={21} />
      </button>
      <div className="workspace-location">
        <span>Workspace</span>
        <ChevronRight size={13} />
        <strong>{labels[page] || "Overview"}</strong>
      </div>
      <div className="workspace-search" ref={searchBox}>
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
              setActive((x) => Math.min(matches.length - 1, x + 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((x) => Math.max(0, x - 1));
            }
            if (e.key === "Enter" && matches[active]) select(matches[active]);
          }}
        />
        {query ? (
          <button
            aria-label="Clear workspace search"
            onClick={() => {
              setQuery("");
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
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
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
            onClick={() => setCreate((x) => !x)}
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
            >
              <span className="search-heading">NEW IN YOUR WORKSPACE</span>
              <div>
                {creation.map(([kind, title, Icon]) => (
                  <button
                    key={kind}
                    role="menuitem"
                    onClick={() => {
                      setCreate(false);
                      onCreate(kind);
                    }}
                  >
                    <Icon size={17} />
                    {title}
                  </button>
                ))}
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
    </header>
  );
}
