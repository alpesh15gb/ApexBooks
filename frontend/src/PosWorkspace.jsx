import { businessDate } from "./businessDate.js";
import { isActiveMaster } from "./masterLifecycle.js";
import { usePostingRequest } from "./usePostingRequest.js";
import { registerPostingRequest } from "./postingRegistry.js";
import { counterTender, matchCounterProduct } from "./posCounter.js";
import { companyRequestRecovery } from "./companyRequestRecovery.js";
import PosRegisterSummary from "./PosRegisterSummary.jsx";
import PosReturn from "./PosReturn.jsx";
import { itemSearchText, itemSummary, useInventorySetup } from "./inventorySetup.js";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Barcode, ChevronDown, CircleCheck, Download, MapPin, Minus, Package, Plus, Printer, ReceiptText, Search, ShoppingBag, Trash2, Wallet, X } from "lucide-react";
const money = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(n || 0),
  );
const walkIn = "Walk-in customer";
const emptyBilling = state => ({ address: "", gstin: "", phone: "", place: state });
const incrementQuantity = (value, delta) => String(Number((Number(value) + delta).toFixed(3)));

export default function PosWorkspace({
  company,
  records,
  api,
  refresh,
  onPdf,
  onOpen,
  onReturn,
  drafts,
  features = [],
  booksRevision = 0,
  recordsReady = true,
  capabilitiesReady = true,
}) {
  const initial = drafts?.get(company.id);
  const [search, setSearch] = useState(""),
    [cart, setCart] = useState(() => initial?.cart || []),
    [held, setHeld] = useState(() => initial?.held || []),
    [customer, setCustomer] = useState(() => initial?.customer || walkIn),
    [method, setMethod] = useState(() => initial?.method || "cash"),
    [bank, setBank] = useState(() => initial?.bank || ""),
    [bankShare, setBankShare] = useState(() => initial?.bankShare || ""),
    [confirmedBankPayment, setConfirmedBankPayment] = useState(null),
    [banks, setBanks] = useState([]),
    [tender, setTender] = useState(() => initial?.tender || ""),
    [inclusive, setInclusive] = useState(() => initial?.inclusive || false),
    [round, setRound] = useState(() => initial?.round || false),
    [quote, setQuote] = useState(null),
    [quoteAttempt, retryQuote] = useState(0),
    [error, setError] = useState(""),
    [scanMessage, setScanMessage] = useState(""),
    [view, setView] = useState("checkout"),
    [bankError, setBankError] = useState(""),
    [stock, setStock] = useState(null),
    [date, setDate] = useState(businessDate),
    [billing, setBilling] = useState(() => initial?.billing || emptyBilling(company.state_code)),
    [historyDate, setHistoryDate] = useState(""),
    [historySearch, setHistorySearch] = useState(""),
    [historyLimit, setHistoryLimit] = useState(20),
    [receipt, setReceipt] = useState(null),
    [returnSource, setReturnSource] = useState(null),
    [recoveringReturn, setRecoveringReturn] = useState(true),
    [returned, setReturned] = useState(null);
  const [recovery] = useState(() => {
    try {
      const token = globalThis.localStorage?.token;
      const store = companyRequestRecovery(company.id, token, window.sessionStorage, "sale");
      const returns = companyRequestRecovery(company.id, token, window.sessionStorage, "return");
      return { store, operation: store?.read(), returns, returnOperation: returns?.read() };
    } catch (failure) {
      return { error: failure.message };
    }
  });
  const inventory = useInventorySetup();
  const operation = useRef(recovery.operation);
  const recoveredReturn = recoveringReturn ? recovery.returnOperation : null;
  const activeReturn = returnSource || (recoveredReturn && (records.find(row => row.id === recoveredReturn.saleId) || { id: recoveredReturn.saleId, number: "receipt" }));
  const searchInput = useRef(null);
  const cartHeading = useRef(null);
  const posting = usePostingRequest({ definitiveRetryStatuses: [409], definitiveRetryCodes: ["POS_REQUOTE_REQUIRED"] });
  const { busy } = posting;
  const pending = !!operation.current || posting.pending;
  const writable = ["owner", "editor"].includes(company.role);
  const locked = busy || pending || !!activeReturn || !writable || !recordsReady || !!recovery.error;
  const splitSupported = features.includes("pos_split_tender");
  const returnSupported = features.includes("pos_atomic_returns");
  const strictStock = features.includes("pos_require_available_stock");
  const stockSummary = features.includes("pos_stock_summary");
  const items = useMemo(() => records.filter(row => row.kind === "item" && isActiveMaster(row)), [records]);
  const hasTrackedStock = items.some(item => item.data?.track_stock);
  const query = search.trim().toLowerCase();
  const filtered = items.filter(row => itemSearchText(row, inventory.setup).includes(query));
  const exact = query && matchCounterProduct(filtered, search).item;
  const shownProducts = (exact ? [exact, ...filtered.filter(row => row.id !== exact.id)] : filtered).slice(0, 30);
  const lines = useMemo(
    () =>
      cart.map((row) => ({
        item_id: row.item.id,
        description: row.item.name,
        hsn: row.item.data?.hsn || "",
        unit: row.item.data?.unit || "",
        quantity: row.quantity,
        rate: row.rate,
        discount_percent: row.discount,
        price_includes_tax: inclusive,
        gst_rate:
          company.tax_mode === "regular" ? row.item.data?.gst_rate || "0" : "0",
        tax_treatment:
          company.tax_mode === "regular" &&
          Number(row.item.data?.gst_rate || 0) === 0
            ? (row.item.data?.tax_treatment && row.item.data.tax_treatment!=="taxable" ? row.item.data.tax_treatment : "nil_rated")
            : "taxable",
      })),
    [cart, inclusive, company.tax_mode],
  );
  const sale = useMemo(() => ({
    kind: "pos",
    name: customer.trim() || walkIn,
    date,
    data: {
      lines,
      place_of_supply: billing.place,
      party_address: billing.address,
      party_gstin: billing.gstin,
      party_phone: billing.phone,
      round_total: round,
      ...(strictStock ? { require_available_stock: true } : {}),
    },
  }), [billing, customer, date, lines, round, strictStock]);
  const quoteCurrent = quote?.sale === sale && quote.revision === booksRevision && quote.attempt === quoteAttempt;
  const preview = quoteCurrent ? quote.result : null;
  const quoteError = quoteCurrent ? quote.error : "";
  const totals = preview && counterTender(preview.amount, method, bankShare, tender);
  const bankRequired = method !== "cash";
  const selectedBank = banks.find(row => row.id === bank) || (banks.length === 1 ? banks[0] : null);
  const bankPayment = useMemo(() => bankRequired && preview && totals && selectedBank
    ? { quote: preview, bankAmount: totals.bank, bankId: selectedBank.id, method }
    : null, [bankRequired, preview, totals?.bank, selectedBank?.id, method]);
  const bankConfirmed = !!bankPayment && confirmedBankPayment === bankPayment;
  const canCheckout = writable && recordsReady && !recovery.error && !!totals && totals.change >= 0 &&
    (!bankRequired || (bankConfirmed && (method !== "split" || splitSupported)));

  useEffect(() => {
    if (drafts) drafts.set(company.id, { cart, held, customer, billing, method, bank, bankShare, tender, inclusive, round });
  }, [drafts, company.id, cart, held, customer, billing, method, bank, bankShare, tender, inclusive, round]);
  useEffect(() => registerPostingRequest({ get pending() { return !!operation.current; } }), []);
  useEffect(() => {
    const timer = setInterval(() => setDate(businessDate()), 15_000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let live = true;
    setBankError("");
    api(`/companies/${company.id}/bank-accounts`)
      .then((r) => {
        if (live) setBanks(Array.isArray(r) ? r.filter(row => row.is_active !== false) : []);
      })
      .catch((e) => {
        if (live) { setBanks([]); setBankError(e.message); }
      });
    return () => {
      live = false;
    };
  }, [company.id, api, booksRevision]);
  useEffect(() => {
    if (!recordsReady || !capabilitiesReady || !hasTrackedStock) return;
    const controller = new AbortController();
    const path = stockSummary ? "/pos/stock" : `/reports/stock?from_date=${date}&to_date=${date}`;
    api(`/companies/${company.id}${path}`, { signal: controller.signal })
      .then(result => {
        if (!controller.signal.aborted && Array.isArray(result.rows)) {
          setStock({ date: result.date || date, revision: booksRevision, byItem: new Map(result.rows.map(row => [row.item_id, row.closing_quantity])) });
        }
      })
      .catch(() => { if (!controller.signal.aborted) setStock(null); });
    return () => controller.abort();
  }, [api, company.id, date, booksRevision, stockSummary, recordsReady, capabilitiesReady, hasTrackedStock]);
  useEffect(() => {
    if (!sale.data.lines.length || pending || !recordsReady) return;
    let live = true;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api(`/companies/${company.id}/documents/preview`, {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify(sale),
      })
        .then((r) => {
          if (live) setQuote({ sale, revision: booksRevision, attempt: quoteAttempt, result: r });
        })
        .catch((e) => {
          if (live) setQuote({ sale, revision: booksRevision, attempt: quoteAttempt, error: e.message });
        });
    }, 200);
    return () => {
      live = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [sale, company.id, api, pending, booksRevision, quoteAttempt, recordsReady]);
  function focusScanner() {
    if (!window.matchMedia?.("(pointer: coarse)").matches) searchInput.current?.focus({ preventScroll: true });
  }
  function add(item) {
    if (locked) return;
    setCart((current) => {
      const found = current.find((row) => row.item.id === item.id);
      return found
        ? current.map((row) =>
            row.item.id === item.id
              ? { ...row, quantity: incrementQuantity(row.quantity, 1) }
              : row,
          )
        : [
            ...current,
            {
              item,
              quantity: "1",
              rate: String(item.data?.sale_rate || "0"),
              discount: "0",
            },
          ];
    });
    setSearch("");
    setScanMessage("");
    setError("");
    setReceipt(null);
    focusScanner();
  }
  function update(id, field, value) {
    setCart(current =>
      current.map((row) =>
        row.item.id === id ? { ...row, [field]: value } : row,
      ),
    );
    setError("");
  }
  function clearSale() {
    setCart([]);
    setSearch("");
    setScanMessage("");
    setTender("");
    setBankShare("");
    setConfirmedBankPayment(null);
    setCustomer(walkIn);
    setBilling(emptyBilling(company.state_code));
    setMethod("cash");
    setError("");
  }
  function holdSale() {
    if (locked || !cart.length || held.length >= 12) return;
    setHeld(current => [...current, {
      id: crypto.randomUUID(), cart, customer, billing, method, bank, inclusive, round,
    }]);
    clearSale();
    focusScanner();
  }
  function recallSale(saved) {
    if (locked || cart.length) return;
    setHeld(current => current.filter(row => row.id !== saved.id));
    setCart(saved.cart);
    setCustomer(saved.customer);
    setBilling(saved.billing);
    setMethod(saved.method);
    setBank(saved.bank);
    setInclusive(saved.inclusive);
    setRound(saved.round);
    setTender("");
    setBankShare("");
  }
  async function checkout(e) {
    e.preventDefault();
    if (busy || activeReturn || !writable || recovery.error) return;
    setError("");
    const retrying = !!operation.current;
    try {
      if (!retrying) {
        if (!canCheckout || !cart.length) return;
        const currentDate = businessDate();
        if (sale.date !== currentDate) {
          setDate(currentDate);
          return;
        }
        const command = { key: crypto.randomUUID(), body: JSON.stringify({
          ...sale,
          data: {
            ...sale.data,
            payment_account: method,
            ...(bankRequired ? { bank_account_id: selectedBank.id } : {}),
            ...(method === "split" ? { bank_amount: (totals.bank / 100).toFixed(2) } : {}),
            ...((method === "split" || strictStock) ? { expected_total: preview.amount } : {}),
            ...(features.includes("pos_register_sessions") ? { expected_register_session: preview.data.pos_register_session_id ?? null } : {}),
            tender_amount: ((method === "bank" ? totals.bank : totals.tender) / 100).toFixed(2),
          },
        }) };
        recovery.store?.save(command);
        operation.current = command;
      }
      const command = operation.current;
      const result = await posting.run(() => api(`/companies/${company.id}/records`, {
        method: "POST", headers: { "Idempotency-Key": command.key }, body: command.body,
      }));
      if (!result) return;
      recovery.store?.clear(command.key);
      operation.current = null;
      setReceipt(result.value);
      clearSale();
      await refresh();
      focusScanner();
    } catch (e) {
      // Every POS rejection before commit is definitive (committed keys replay first), except timeouts.
      if (operation.current && !posting.isPending() && e.status >= 400 && e.status < 500 && e.status !== 408) {
        recovery.store?.clear(operation.current.key);
        operation.current = null;
        retryQuote(value => value + 1);
      }
      setError(e.message);
    }
  }
  const daySales = records.filter(
    r => r.kind === "pos" && r.posted && !r.cancelled && r.date === date,
  );
  const history = records.filter(row => row.kind === "pos" && (row.posted || row.cancelled) &&
    (!historyDate || row.date === historyDate) &&
    `${row.number || ""} ${row.name || ""}`.toLowerCase().includes(historySearch.trim().toLowerCase()));
  const availableBookStock = stock?.date === date && stock.revision === booksRevision ? stock.byItem : null;
  const totalLabel = preview ? money(preview.amount) : cart.length ? "—" : money(0);
  const tabs = [
    { id: "checkout", label: "Checkout", Icon: ShoppingBag },
    { id: "receipts", label: "Receipts", Icon: ReceiptText },
    { id: "register", label: "Register", Icon: Wallet },
  ];
  return (
    <div className="pos-workspace">
      <header className="pos-heading">
        <div>
          <h1>Point of sale</h1>
        </div>
        <div className="pos-day-total">
          <span>Today’s sales</span>
          <strong>{recordsReady ? money(daySales.reduce((total, r) => total + Number(r.amount), 0)) : "—"}</strong>
          <small>{recordsReady ? `${daySales.length} ${daySales.length === 1 ? "receipt" : "receipts"}` : "Loading sales…"}</small>
        </div>
      </header>
      <div className="pos-tabs" role="group" aria-label="Point of sale views">
        {tabs.map(({ id, label, Icon }) => <button type="button" key={id} aria-pressed={view === id}
          disabled={(busy || pending || !!activeReturn) && view !== id} onClick={() => setView(id)}>
          <Icon size={18} aria-hidden="true" />{label}
        </button>)}
      </div>
      {view === "checkout" && receipt && (
        <div className="pos-receipt pos-success" role="status">
          <div className="pos-success-text"><CircleCheck aria-hidden="true" size={23} />
            <div><strong>{receipt.posted === false ? "Sale was cancelled" : "Sale completed"}</strong><p>{receipt.number} · {money(receipt.amount)}{receipt.posted !== false && Number(receipt.data?.change_amount) > 0 && ` · Change ${money(receipt.data.change_amount)}`}</p></div>
          </div>
          <div className="pos-actions">
            {receipt.posted !== false && features.includes("thermal_receipts") && <details className="row-menu receipt-menu">
              <summary className="button secondary"><Printer size={16} aria-hidden="true" />Print receipt<ChevronDown size={14} aria-hidden="true" /></summary>
              <div className="row-menu-list">{[["thermal_80", "80 mm roll"], ["thermal_58", "58 mm roll"]].map(([format, label]) =>
                <button type="button" key={format} onClick={event => { event.currentTarget.closest("details").open = false; onPdf(receipt, format); }}>{label}</button>
              )}</div>
            </details>}
            <button type="button" className="button secondary" onClick={() => onPdf(receipt)}>
              <Download size={16} aria-hidden="true" />
              Download receipt
            </button>
          </div>
          <button type="button" className="icon-button pos-dismiss-receipt" aria-label="Dismiss receipt" onClick={() => setReceipt(null)}><X size={18} aria-hidden="true" /></button>
        </div>
      )}
      {view === "receipts" && returned && <div className="pos-receipt pos-success" role="status">
        <div className="pos-success-text"><CircleCheck size={23} aria-hidden="true" /><div>
          <strong>{returned.credit_note.posted === false ? "Return was cancelled" : "Return posted"}</strong>
          <p>{returned.credit_note.number}{returned.refund
            ? ` · Refund ${returned.refund.number}${returned.refund.posted === false ? " · Cancelled" : ""}`
            : returned.credit_note.posted !== false ? " · Retained as customer credit" : ""}</p>
        </div></div>
        <div className="pos-actions">
          <button type="button" className="button secondary" onClick={() => onPdf(returned.credit_note)}>Download credit note</button>
          {returned.refund && <button type="button" className="button secondary" onClick={() => onPdf(returned.refund)}>Download refund voucher</button>}
        </div>
      </div>}
      {(error || recovery.error) && (
        <div className="error banner" role="alert">
          {error || recovery.error}
        </div>
      )}
      <div className="pos-grid" hidden={view !== "checkout"}>
        <section className="panel pos-catalogue">
          <div className="pos-panel-heading"><h2>Products</h2><span>{items.length} {items.length === 1 ? "item" : "items"}</span></div>
          <div className="pos-scan">
            <Barcode size={22} aria-hidden="true" />
            <input
              aria-label="Search POS items or scan barcode"
              disabled={locked}
              ref={searchInput}
              placeholder="Scan barcode or search"
              autoComplete="off"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setScanMessage(""); }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  const match = matchCounterProduct(items, search);
                  if (match.item) add(match.item);
                  else { setScanMessage(match.message); e.target.select(); }
                }
              }}
            />
            {search && <button type="button" className="link" disabled={locked} onClick={() => {
              setSearch(""); setScanMessage(""); searchInput.current?.focus();
            }}>Clear</button>}
            {!search && <Search size={17} aria-hidden="true" />}
          </div>
          {scanMessage && <p className="pos-scan-feedback" role="status">{scanMessage}</p>}
          {cart.length > 0 && <button type="button" className="button secondary pos-jump-to-cart" onClick={() => cartHeading.current?.focus()}>
            <ShoppingBag size={17} aria-hidden="true" /> Review sale · {cart.length} {cart.length === 1 ? "item line" : "item lines"}
          </button>}
          <div className="pos-products">
            {shownProducts.map(item => (
              <button
                className="pos-product"
                key={item.id}
                onClick={() => add(item)}
                disabled={locked}
              >
                <span className="pos-product-media">
                  {item.data?.image_thumbnail ? <img src={item.data.image_thumbnail} alt="" loading="lazy" /> : <Package size={19} aria-hidden="true" />}
                </span>
                <span className="pos-product-body">
                  <strong>{item.name}</strong>
                  {item.data?.barcode && <small>{item.data.barcode}</small>}
                  {itemSummary(item, inventory.setup).locations.length > 0 && <small className="pos-location"><MapPin size={11} aria-hidden="true" /> {itemSummary(item, inventory.setup).locations.join(" · ")}</small>}
                  {item.data?.track_stock && <small className={Number(availableBookStock?.get(item.id)) <= 0 ? "pos-out-of-stock" : ""}>
                    Book stock: {availableBookStock?.get(item.id) ?? "Unavailable"}
                  </small>}
                </span>
                <span className="pos-product-add">
                  <strong>{money(item.data?.sale_rate)}</strong>
                  <Plus size={17} aria-hidden="true" />
                </span>
              </button>
            ))}
          </div>
          {!recordsReady && <p>Loading the product catalogue…</p>}
          {recordsReady && !items.length && <p>Add items in Items to start selling.</p>}
          {!!items.length && !filtered.length && <p>No matching items.</p>}
          {filtered.length > shownProducts.length && <p>Showing {shownProducts.length} of {filtered.length} products. Search or scan to find a specific item.</p>}
        </section>
        <section className="panel pos-cart">
          <div className="pos-panel-heading"><h2 ref={cartHeading} tabIndex={-1}>Current sale</h2><span>{cart.length} {cart.length === 1 ? "item line" : "item lines"}</span></div>
          {!writable && <p>You have read-only access to point of sale.</p>}
          {held.length > 0 && <details className="pos-held" open={!cart.length}>
            <summary>Held sales ({held.length})</summary>
            <ul>{held.map(saved => <li key={saved.id}>
              <span>{saved.customer} · {saved.cart.length} item lines</span>
              <button type="button" className="button secondary" disabled={locked || !!cart.length} onClick={() => recallSale(saved)}>Resume</button>
              <button type="button" className="link" disabled={locked} onClick={() => {
                if (window.confirm("Discard this held sale?")) setHeld(current => current.filter(row => row.id !== saved.id));
              }}>Discard</button>
            </li>)}</ul>
            {cart.length > 0 && <p>Hold or finish the current sale before resuming another.</p>}
            <p>Held sales stay in this tab while you work. They do not reserve stock.</p>
          </details>}
          <form className="form-grid pos-cart-form" onSubmit={checkout}>
            <fieldset className="form-grid full submission-fields" disabled={locked}>
            {cart.map((row) => (
              <div className="line-card full" key={row.item.id}>
                <div className="line-heading">
                  <div><strong>{row.item.name}</strong><small>{money(row.rate)} / {row.item.data?.unit || "unit"}{Number(row.discount) > 0 ? ` · ${row.discount}% off` : ""}</small></div>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remove ${row.item.name} from cart`}
                    onClick={() =>
                      setCart(cart.filter((r) => r.item.id !== row.item.id))
                    }
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="pos-line-controls">
                    <div className="pos-quantity">
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Decrease ${row.item.name} quantity`}
                        disabled={Number(row.quantity) <= 1}
                        onClick={() =>
                          update(
                            row.item.id,
                            "quantity",
                            incrementQuantity(row.quantity, -1),
                          )
                        }
                      >
                        <Minus size={14} />
                      </button>
                      <input
                        aria-label={`Quantity for ${row.item.name}`}
                        type="number"
                        min="0.001"
                        step="0.001"
                        required
                        value={row.quantity}
                        onChange={(e) =>
                          update(row.item.id, "quantity", e.target.value)
                        }
                      />
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Increase ${row.item.name} quantity`}
                        onClick={() =>
                          update(
                            row.item.id,
                            "quantity",
                            incrementQuantity(row.quantity, 1),
                          )
                        }
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  <details className="pos-line-options">
                    <summary>Price and discount</summary>
                    <div className="form-grid">
                      <label>Rate (₹)<input type="number" min="0" step="0.01" required value={row.rate}
                        onChange={e => update(row.item.id, "rate", e.target.value)} /></label>
                      <label>Discount (%)<input type="number" min="0" max="100" step="0.01" required value={row.discount}
                        onChange={e => update(row.item.id, "discount", e.target.value)} /></label>
                    </div>
                  </details>
                </div>
              </div>
            ))}
            {!cart.length && (
              <div className="pos-empty-cart full">
                <ShoppingBag size={25} aria-hidden="true" />
                <strong>{pending ? "Checkout awaiting confirmation" : "Your cart is empty"}</strong>
                {!pending && <p>Scan a barcode or choose a product to start.</p>}
              </div>
            )}
            {cart.length > 0 && <div className="pos-actions full">
              <button type="button" className="button secondary" disabled={held.length >= 12} onClick={holdSale}>Hold sale</button>
              <button type="button" className="link" onClick={() => {
                if (window.confirm("Clear the current sale?")) clearSale();
              }}>Clear sale</button>
            </div>}
            {cart.length > 0 && <details className="pos-billing full">
              <summary>Customer and billing <span>{customer || walkIn}</span></summary>
              <div className="form-grid">
                <label className="full">Customer<input list="pos-parties" value={customer} placeholder={walkIn}
                  onChange={e => {
                    const value = e.target.value;
                    const party = records.find(row => row.kind === "party" && isActiveMaster(row) && row.name.toLowerCase() === value.trim().toLowerCase());
                    const gstin = party?.data?.gstin || "";
                    setCustomer(value);
                    setBilling({ address: party?.data?.address || "", gstin, phone: party?.data?.phone || "", place: gstin.slice(0, 2) || company.state_code });
                  }} />
                  <datalist id="pos-parties">{records.filter(row => row.kind === "party" && isActiveMaster(row)).map(row => <option key={row.id} value={row.name} />)}</datalist>
                </label>
                <label className="full">Billing address<input maxLength={500} value={billing.address} onChange={e => setBilling({ ...billing, address: e.target.value })} /></label>
                <label>Customer GSTIN<input maxLength={15} value={billing.gstin} onChange={e => setBilling({ ...billing, gstin: e.target.value.toUpperCase() })} /></label>
                <label>Customer phone<input maxLength={32} value={billing.phone} onChange={e => setBilling({ ...billing, phone: e.target.value })} /></label>
                {company.tax_mode !== "unregistered" && <label>Place of supply (state code)<input required pattern="[0-9]{2}" value={billing.place} onChange={e => setBilling({ ...billing, place: e.target.value })} /></label>}
                {company.tax_mode === "regular" && <label className="checkbox-label full">
              <input
                type="checkbox"
                checked={inclusive}
                onChange={(e) => setInclusive(e.target.checked)}
              />
              Prices include GST
            </label>}
            <label className="checkbox-label full">
              <input
                type="checkbox"
                checked={round}
                onChange={(e) => setRound(e.target.checked)}
              />
              Round total to nearest rupee
            </label>
              </div>
            </details>}
            {cart.length > 0 && <label className={method === "bank" || method === "cash" ? "" : "full"}>
              Payment method
              <select
                className="form-select"
                value={method}
                onChange={(e) => { setMethod(e.target.value); setTender(""); setBankShare(""); setError(""); }}
              >
                <option value="cash">Cash</option>
                <option value="bank">Bank / UPI / card</option>
                {splitSupported && <option value="split">Cash + bank / UPI / card</option>}
              </select>
            </label>}
            {cart.length > 0 && bankRequired && (
              <label className={method === "split" ? "full" : ""}>
                Receiving bank
                <select
                  className="form-select"
                  value={selectedBank?.id || ""}
                  onChange={(e) => setBank(e.target.value)}
                >
                  {!selectedBank && <option value="">Choose a bank account</option>}
                  {banks.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
                {bankError && <small>{bankError}</small>}
                {!bankError && !banks.length && <small>No receiving bank accounts are available.</small>}
              </label>
            )}
            {cart.length > 0 && method === "split" && <label>
              Bank / UPI / card amount (₹)
              <input type="number" min="0.01" step="0.01" required value={bankShare} onChange={e => setBankShare(e.target.value)} />
            </label>}
            {cart.length > 0 && method !== "bank" && (
              <label>
                Cash tendered (₹)
                <input
                  type="number"
                  min={totals ? (totals.cash / 100).toFixed(2) : "0"}
                  step="0.01"
                  value={tender}
                  onChange={(e) => setTender(e.target.value)}
                  placeholder={totals ? (totals.cash / 100).toFixed(2) : "Exact amount"}
                />
              </label>
            )}
            {bankPayment && <label className="checkbox-label full pos-payment-confirm">
              <input type="checkbox" checked={bankConfirmed}
                onChange={e => setConfirmedBankPayment(e.target.checked ? bankPayment : null)} />
              Bank, UPI or card payment received
            </label>}
            <div className="pos-totals full" aria-live="polite">
              <div className="pos-payable"><span>Total payable</span><strong>{totalLabel}</strong></div>
              {preview && <>
                {company.tax_mode === "regular" && <p>GST {money(
                  Number(preview.data.cgst) + Number(preview.data.sgst) + Number(preview.data.igst),
                )}</p>}
                {totals && method !== "bank" && <p className="pos-cash-summary">
                  Cash due {money(totals.cash / 100)}
                  <strong className={totals.change < 0 ? "pos-out-of-stock" : undefined}>{totals.change < 0
                    ? `Still needed ${money(-totals.change / 100)}`
                    : `Change ${money(totals.change / 100)}`}</strong>
                </p>}
                {method === "split" && !totals && <p>Enter a bank amount greater than zero and less than the total.</p>}
              </>}
            </div>
            {!preview && !pending && cart.length > 0 && (quoteError ? <div className="error banner full" role="alert">
              {quoteError} <button type="button" className="link" onClick={() => retryQuote(value => value + 1)}>Refresh total</button>
            </div> : <p className="full" role="status">Checking sale total…</p>)}
            </fieldset>
            {pending && !busy && <p className="info-box full" role="status">
              The previous response was not confirmed. Retry the original sale and verify the result before taking another payment.
            </p>}
            <button
              className="button primary full pos-complete"
              disabled={
                busy ||
                !writable ||
                !!recovery.error ||
                !!activeReturn ||
                (!pending && !canCheckout)
              }
            >
              {busy ? "Posting sale…" : pending ? "Retry sale" : "Complete sale"}
            </button>
          </form>
        </section>
      </div>
      <section className="panel settings-panel pos-history" hidden={view !== "receipts"}>
        <div className="pos-panel-heading"><h2>Receipt history</h2><span>{recordsReady ? `${history.length} ${history.length === 1 ? "receipt" : "receipts"}` : "Loading…"}</span></div>
        <div className="form-grid pos-receipt-filters">
          <label>Receipt number or customer<input placeholder="Search receipts" type="search" value={historySearch} onChange={e => { setHistorySearch(e.target.value); setHistoryLimit(20); }} /></label>
          <label>Sale date<input type="date" value={historyDate} onChange={e => { setHistoryDate(e.target.value); setHistoryLimit(20); }} /></label>
          <button type="button" className="button secondary" onClick={() => { setHistoryDate(historyDate ? "" : businessDate()); setHistoryLimit(20); }}>{historyDate ? "Show all dates" : "Show today"}</button>
        </div>
        <ul className="pos-history-list">{history.slice(0, historyLimit).map(row => (
          <li key={row.id}>
            <div><strong>{row.number}</strong> · {row.name}<br /><small>{row.date} · {money(row.amount)}{row.cancelled ? " · Cancelled" : ""}</small></div>
            <div className="pos-actions">
              {onOpen && <button type="button" className="button secondary" disabled={busy || pending} onClick={() => onOpen(row)}>View receipt</button>}
              {!row.cancelled && features.includes("thermal_receipts") && <button type="button" className="button secondary" onClick={() => onPdf(row, "thermal_80")}>Reprint 80 mm</button>}
              {(returnSupported || onReturn) && writable && row.posted && !row.cancelled && <button type="button" className="button secondary" disabled={busy || pending} onClick={() => {
                if (returnSupported) setReturnSource(row);
                else onReturn(row, "credit_note");
              }}>Start return</button>}
            </div>
          </li>
        ))}</ul>
        {!history.length && <p>{recordsReady ? "No receipts match your filters." : "Loading receipts…"}</p>}
        {history.length > historyLimit && <button type="button" className="button secondary" onClick={() => setHistoryLimit(value => value + 20)}>Show more receipts</button>}
      </section>
      {recordsReady && <div hidden={view !== "register"}>
        <PosRegisterSummary records={records} refresh={refresh} companyName={company.name}
          api={api} companyId={company.id} canWrite={writable} registerEnabled={features.includes("pos_register_sessions")} />
      </div>}
      {activeReturn && <PosReturn key={activeReturn.id} company={company} sale={activeReturn} banks={banks} api={api}
        recoveryStore={recovery.returns} recovered={recoveredReturn}
        onClose={message => {
          setReturnSource(null);
          setRecoveringReturn(false);
          if (message) { setError(message); setView("receipts"); }
        }} onComplete={result => {
          setReturned(result);
          setReturnSource(null);
          setRecoveringReturn(false);
          setView("receipts");
          refresh().catch(failure => setError(failure.message));
        }} />}
    </div>
  );
}
