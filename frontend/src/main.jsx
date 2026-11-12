import { businessDate, businessFinancialYear } from "./businessDate.js";
import { CORE_ENHANCEMENTS, capabilityFeatures, supportsFeature, routeFeature, companyDisplayName } from "./capabilities.js";
import { hasPendingPostings, postingNavigationMessage, registerPostingRequest } from "./postingRegistry.js";
import { apiErrorMessage } from "./apiErrors.js";
import { fetchCompanyRecords } from "./companyRecords.js";
import TransactionDetail from "./TransactionDetail.jsx";
import { relatedRecordActions, settlementLabel } from "./recordLifecycle.js";
import { createRequestScope } from "./requestScope.js";
import RegisterControls from "./RegisterControls.jsx";
import { compareRegisterRecords } from "./registerOrder.js";
import { deferWorkspace } from "./DeferredWorkspace.jsx";
const SettingsWorkspace = deferWorkspace(() => import("./SettingsWorkspace.jsx"), "Settings");
const CommerceWorkspace = deferWorkspace(() => import("./CommerceWorkspace.jsx"), "Ecommerce");
import RegisterOverview from "./RegisterOverview.jsx";
import BusinessOverview from "./BusinessOverview.jsx";
import WorkspaceHeader from "./WorkspaceHeader.jsx";
import PartyStatement from "./PartyStatement.jsx";
import { WorkspaceBoundary, DialogFocus } from "./WorkspaceBoundary.jsx";
import { RecoveryCodes, RecoverAccount } from "./RecoveryAccess.jsx";
const PosWorkspace = deferWorkspace(() => import("./PosWorkspace.jsx"), "Point of sale");
import { OpeningBalances, CreditSettlements } from "./AccountingWorkflows.jsx";
import { isActiveMaster } from "./masterLifecycle.js";
import { reorderDraft } from "./reorderDraft.js";
const RecurringWorkspace = deferWorkspace(() => import("./RecurringWorkspace.jsx"), "Recurring drafts");
const ReorderWorkspace = deferWorkspace(() => import("./ReorderWorkspace.jsx"), "Low stock & reorder");
import RecordEditor from "./RecordEditor.jsx";
const BackupRestore = deferWorkspace(() => import("./BackupRestore.jsx"), "Backup and restore");
import ActionMenu from "./ActionMenu.jsx";
import WorkspaceSidebar from "./WorkspaceSidebar.jsx";

import React, { useEffect, useMemo, useRef, useState } from "react";
const CompleteBackup = deferWorkspace(() => import("./CompleteBackup.jsx"), "Complete backup tools");
import { createRoot } from "react-dom/client";
import {
  CalendarDays,
  LayoutDashboard,
  UsersRound,
  ShoppingCart,
  ShoppingBag,
  Wallet,
  BarChart3,
  Settings,
  ChevronDown,
  ChevronRight,
  Plus,
  Search,
  Bell,
  ArrowUpRight,
  ArrowDownLeft,
  FileText,
  Package,
  Download,
  Menu,
  X,
  LogOut,
  CircleHelp,
  Eye,
  EyeOff,
  Building2,
  ReceiptIndianRupee,
  BookOpen,
} from "lucide-react";
// Keep the shared theme after commerce's base rules even when its JS loads later.
import "./commerce.css";
import "./style.css";
import "./capabilities.css";
import "./workspace.css";
import "./flows.css";
import "./ledger.css";
import "./rich-workspace.css";
import "./clarity.css";
import "./quickbooks-workflows.css";
const ReportsV2 = deferWorkspace(() => import("./Reports.jsx"), "Reports");
const DayBook = deferWorkspace(() => import("./DayBook.jsx"), "Day book");
import OverdueReminders, { overdueCount } from "./OverdueReminders.jsx";
const MasterImport = deferWorkspace(() => import("./MasterImport.jsx"), "CSV import");
const VyaparImport = deferWorkspace(() => import("./VyaparImport.jsx"), "Vyapar import");
const DocumentBranding = deferWorkspace(() => import("./DocumentBranding.jsx"), "Document branding");
import MasterForm from "./MasterForm.jsx";
import OpeningStock from "./OpeningStock.jsx";
import StockAdjustment from "./StockAdjustment.jsx";
const CompanyDataExport = deferWorkspace(() => import("./CompanyDataExport.jsx"), "Company export");
import CompanyDetailsEditor from "./CompanyDetailsEditor.jsx";
const AuditLog = deferWorkspace(() => import("./AuditLog.jsx"), "Activity log");
const PeriodLock = deferWorkspace(() => import("./PeriodLock.jsx"), "Accounting period lock");
const AccountSecurity = deferWorkspace(() => import("./AccountSecurity.jsx"), "Account security");
const BankWorkspace = deferWorkspace(() => import("./BankWorkspace.jsx"), "Cash & bank");
import PaymentAllocations from "./PaymentAllocations.jsx";
import Advances from "./Advances.jsx";
import { downloadBlob } from "./downloadBlob.js";

const sections = [
  { label: "Dashboard", icon: LayoutDashboard, key: "dashboard" },
  { label: "Parties", icon: UsersRound, key: "party" },
  { label: "Items", icon: Package, key: "item" },
  {
    label: "Sales",
    icon: ShoppingCart,
    children: [
      ["sales_invoice", "Sales invoices"],
      ["estimate", "Estimates"],
      ["sales_order", "Sales orders"],
      ["proforma", "Proforma invoices"],
      ["payment_in", "Payment in"],
      ["credit_note", "Credit notes"],
      ["pos", "POS"],
    ],
  },
  {
    label: "Purchases",
    icon: ShoppingBag,
    children: [
      ["purchase_bill", "Purchase bills"],
      ["payment_out", "Payment out"],
      ["expense", "Expenses"],
      ["purchase_order", "Purchase orders"],
      ["debit_note", "Debit notes"],
    ],
  },
  { label: "Cash & bank", icon: Wallet, key: "bank_account" },
  { label: "Day book", icon: BookOpen, key: "day_book" },
  { label: "Ledger", icon: FileText, key: "ledger" },
  { label: "Reports", icon: BarChart3, key: "reports" },
  { label: "Recurring drafts", icon: CalendarDays, key: "recurring" },
  { label: "Ecommerce", icon: ShoppingBag, key: "commerce" },
  { label: "Settings", icon: Settings, key: "settings" },
];
const labels = Object.fromEntries(
  sections.flatMap((s) => s.children || (s.key ? [[s.key, s.label]] : [])),
);
labels.reorder = "Low stock & reorder";
labels.bank_transfer = "Cash/bank transfer";
labels.balance_adjustment = "Balance adjustment";
labels.stock_opening = "Opening stock";
labels.stock_adjustment = "Stock adjustment";
const EMPTY_RECORDS = [];
const documentKinds = [
  "sales_order",
  "sales_invoice",
  "estimate",
  "proforma",
  "credit_note",
  "pos",
  "purchase_bill",
  "purchase_order",
  "debit_note",
  "expense",
];
const money = (value) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
const today = () => businessDate();
const api = async (path, options = {}) => {
  const { rawResponse = false, ...fetchOptions } = options;
  const mutation = options.method && !["GET", "HEAD"].includes(options.method);
  let response;
  try { response = await fetch("/api" + path, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.token
        ? { Authorization: `Bearer ${localStorage.token}` }
        : {}),
      ...options.headers,
    },
  }); } catch (failure) {
    if (failure.name === "AbortError") throw failure;
    const error = new Error(apiErrorMessage(0, {}, mutation));
    error.status = 0;
    throw error;
  }
  if (!response.ok) {
    let e = await response.json().catch(() => ({}));
    const error = new Error(apiErrorMessage(response.status, e, mutation));
    error.status = response.status;
    throw error;
  }
  return rawResponse ? response : response.json();
};

function Auth({ onLogin }) {
  const [recovery, setRecovery] = useState(false);
  const [register, setRegister] = useState(false),
    [passwordVisible, setPasswordVisible] = useState(false),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (register)
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
      const result = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      localStorage.token = result.token;
      onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <div className="auth-story">
        <div className="brand light">
          <img className="brand-wordmark" src="/apexbooks-wordmark.png" alt="Apex Books — Your books in balance" width="1569" height="230" />
        </div>
        <div className="auth-copy">
          <div className="eyebrow">MADE FOR INDIAN BUSINESSES</div>
          <h1>
            Clarity for every
            <br />
            <em>business decision.</em>
          </h1>
          <p>
            Keep your books organised, your transactions in view, and your
            business moving forward.
          </p>
        </div>
        <div className="auth-foot">
          Thoughtful accounting, made simple. <span>✳</span>
        </div>
      </div>
      <div className="auth-form">
        <div className="auth-box">
          <div className="eyebrow green">WELCOME TO APEX BOOKS</div>
          {recovery ? (
            <RecoverAccount api={api} onBack={() => setRecovery(false)} />
          ) : (
            <>
              <h2>
                {register ? "Create your account" : "Good to see you again."}
              </h2>
              <p>
                {register
                  ? "Start with the essentials. You can add your company next."
                  : "Sign in to continue to your workspace."}
              </p>
              <form onSubmit={submit}>
                <label>
                  Email address
                  <input
                    type="email"
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    disabled={busy}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.com"
                    required
                  />
                </label>
                <div>
                  <label htmlFor="auth-password">Password</label>
                  <span className="password-field">
                  <input
                    id="auth-password"
                    type={passwordVisible ? "text" : "password"}
                    autoComplete={register ? "new-password" : "current-password"}
                    disabled={busy}
                    minLength="8"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={register ? "At least 8 characters" : "Enter your password"}
                    required
                  />
                  <button type="button" className="icon-button" disabled={busy} aria-label={passwordVisible ? "Hide password" : "Show password"} aria-pressed={passwordVisible} onClick={() => setPasswordVisible(value => !value)}>{passwordVisible ? <EyeOff size={18} /> : <Eye size={18} />}</button>
                  </span>
                </div>
                {error && <div className="error" role="alert">{error}</div>}
                <button className="button primary wide" disabled={busy}>
                  {busy
                    ? "Please wait…"
                    : register
                      ? "Create account"
                      : "Sign in"}{" "}
                  <ChevronRight size={16} />
                </button>
              </form>
              <div className="auth-switch">
                {register ? "Already have an account?" : "New to Apex Books?"}{" "}
                <button
                  className="link"
                  disabled={busy}
                  onClick={() => {
                    setRegister(!register);
                    setPasswordVisible(false);
                    setError("");
                  }}
                >
                  {register ? "Sign in" : "Create an account"}
                </button>
              </div>
              {!register && (
                <button
                  className="link recovery-link"
                  onClick={() => {
                    setRecovery(true);
                    setError("");
                  }}
                >
                  Forgot password? Use a recovery code
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
function CompanyModal({ close, save, features = [] }) {
  const [form, setForm] = useState({
      name: "",
      book_label: "",
      gstin: "",
      state_code: "",
      address: "",
      tax_mode: "unregistered",
    }),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const requestClose = () => { if (!submitting.current) close(); };
  async function submit(e) {
    e.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const { book_label, ...legal } = form;
      await save({ ...legal, ...(supportsFeature(features,"company_book_labels") ? { book_label: book_label.trim() } : {}) });
    } catch (err) {
      setError(err.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Add a company"
      subtitle="Set up a separate workspace for your business."
      close={requestClose}
    >
      <form onSubmit={submit} className="form-grid">
        <label className="full">
          Company name
          <input
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Apex Trading Co."
          />
        </label>
        {supportsFeature(features,"company_book_labels") && <label className="full">Book label (optional)<input maxLength={80} value={form.book_label} onChange={event => setForm({ ...form, book_label: event.target.value })} placeholder="A label you choose for these separate books" /><small>Used only to distinguish workspaces. The legal company name and printed invoices stay unchanged.</small></label>}
        <label className="full">
          Tax registration
          <select
            className="form-select"
            value={form.tax_mode}
            onChange={(e) =>
              setForm({ ...form, tax_mode: e.target.value, gstin: "" })
            }
          >
            <option value="unregistered">Not GST registered</option>
            <option value="regular">GST registered (regular)</option>
            <option value="composition">GST registered (composition)</option>
          </select>
        </label>
        {form.tax_mode !== "unregistered" && (
          <label>
            GSTIN <span className="muted">(required)</span>
            <input
              required={form.tax_mode !== "unregistered"}
              value={form.gstin}
              onChange={(e) =>
                setForm({ ...form, gstin: e.target.value.toUpperCase() })
              }
              placeholder="15-character GSTIN"
            />
          </label>
        )}
        <label>
          State code
          <input
            required={form.tax_mode !== "unregistered"}
            pattern="[0-9]{2}"
            value={form.state_code}
            onChange={(e) => setForm({ ...form, state_code: e.target.value })}
            placeholder="e.g. 27"
          />
        </label>
        <label className="full">
          Address
          <input
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
            placeholder="Business address"
          />
        </label>
        {error && <div className="error full">{error}</div>}
        <div className="modal-actions full">
          <button type="button" className="button secondary" onClick={requestClose} disabled={busy}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>{busy ? "Creating…" : "Create company"}</button>
        </div>
      </form>
    </Modal>
  );
}
function Modal({ title, subtitle, close, children, variant }) {
  return (
    <div
      className={`overlay ${variant === "document" ? "document-overlay" : ""}`}
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <div
        className={`modal ${variant === "document" ? "document-modal" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={(e) => e.key === "Escape" && close()}
      >
        <div className="modal-heading">
          <div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button className="icon-button" onClick={close} aria-label="Close">
            <X size={19} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
function App() {
  const [capabilities, setCapabilities] = useState(null), [capabilityRevision, setCapabilityRevision] = useState(0);
  const features = capabilities?.features || [];
  const supported = feature => supportsFeature(features, feature);
  const [signed, setSigned] = useState(!!localStorage.token),
    [companies, setCompanies] = useState([]),
    [companyId, setCompanyId] = useState(localStorage.companyId || ""),
    [rawRecords, setRecords] = useState([]),
    [recordsCompanyId, setRecordsCompanyId] = useState(""),
    [recordsLoadError, setRecordsLoadError] = useState(""),
    [page, setPage] = useState(() => labels[window.location.hash.slice(2)] ? window.location.hash.slice(2) : "dashboard"),
    [settingsTab, setSettingsTab] = useState("company"),
    [expanded, setExpanded] = useState(() => sections.find(section => section.children?.some(([key]) => key === window.location.hash.slice(2)))?.label || ""),
    [modal, setModal] = useState(""),
    [editorCycle, setEditorCycle] = useState(0),
    [registerFilter, setRegisterFilter] = useState({ page: "", value: "all" }),
    [registerQuery, setRegisterQuery] = useState({
      page: "",
      period: "all",
      from: "",
      to: "",
      party: "",
      sort: "newest",
    }),
    [registerPage, setRegisterPage] = useState(1),
    [search, setSearch] = useState(""),
    [menu, setMenu] = useState(false),
    [createOpen, setCreateOpen] = useState(false),
    [error, setError] = useState(""),
    [docTemplate, setDocTemplate] = useState("classic"),
    [conversionSource, setConversionSource] = useState(null),
    [relatedSource, setRelatedSource] = useState(null),
    [draftSeed, setDraftSeed] = useState(null),
    [detail, setDetail] = useState(null),
    [detailLoading, setDetailLoading] = useState(false),
    [detailError, setDetailError] = useState(""),
    [recordsLoading, setRecordsLoading] = useState(false),
    [recordsProgress, setRecordsProgress] = useState(0),
    [booksRevision, setBooksRevision] = useState(0),
    [partyBalances, setPartyBalances] = useState(null),
    [remindOverdue, setRemindOverdue] = useState(false),
    [editorReturn, setEditorReturn] = useState(null),
    [editingMaster, setEditingMaster] = useState(null),
    [editingDraft, setEditingDraft] = useState(null),
    [activeParty, setActiveParty] = useState(null);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [page, companyId]);
  useEffect(() => {
    let active = true; const token = localStorage.token; setCapabilities(null);
    if (signed) api("/capabilities").then(result => {
      if (active && localStorage.token === token) setCapabilities({ features: capabilityFeatures(result), version: result.api_version, revision: result.build_revision });
    }).catch(reason => {
      if (active && localStorage.token === token) setCapabilities({ features: [], reason: reason.status === 404 ? "The connected API does not yet advertise these features." : "API feature support could not be verified." });
    });
    return () => { active = false; };
  }, [signed, capabilityRevision]);
  const company = companies.find((c) => c.id === companyId);
  const activeCompany = useRef(companyId);
  activeCompany.current = companyId;
  const workspaceScope = useRef(createRequestScope(companyId));
  workspaceScope.current.setContext(companyId);
  const editorRequests = useRef(createRequestScope(companyId));
  editorRequests.current.setContext(companyId);
  const recordsAbort = useRef(null);
  const recordsReady = recordsCompanyId === companyId;
  const records = recordsReady ? rawRecords : EMPTY_RECORDS;
  async function loadCompanies() {
    const requestToken = localStorage.token;
    try {
      const data = await api("/companies");
      if (localStorage.token !== requestToken) return;
      setCompanies(data);
      if (!data.some((c) => c.id === companyId)) {
        setCompanyId(data[0]?.id || "");
        if (!data.length) setModal("company");
      }
    } catch (e) {
      if (localStorage.token !== requestToken) return;
      if (e.status === 401) {
        localStorage.removeItem("token");
        localStorage.removeItem("companyId");
        setRecords([]);
        setCompanies([]);
        setCompanyId("");
        setSigned(false);
      } else setError(e.message);
    }
  }
  useEffect(() => {
    if (page !== "party" || !companyId || !features.includes("party_balances")) return;
    let active = true;
    api(`/companies/${companyId}/parties/balances`)
      .then((result) => { if (active) setPartyBalances({ companyId, ...result, byId: Object.fromEntries(result.rows.map((row) => [row.party_id, row])) }); })
      .catch(() => { if (active) setPartyBalances(null); });
    return () => { active = false; };
  }, [page, companyId, booksRevision, features.join(",")]);
  async function loadRecords(id = companyId, { refreshReports = true } = {}) {
    if (!id || activeCompany.current !== id) return;
    recordsAbort.current?.abort();
    const controller = new AbortController();
    recordsAbort.current = controller;
    const isCurrent = workspaceScope.current.latest();
    setRecordsLoadError("");
    setRecordsLoading(true);
    setRecordsProgress(0);
    if (refreshReports) setBooksRevision(value => value + 1);
    try {
      const rows = await fetchCompanyRecords(api, id, {
        isCurrent, signal: controller.signal,
        onProgress: count => { if (isCurrent()) setRecordsProgress(count); },
      });
      if (rows && isCurrent()) {
        setRecords(rows);
        setRecordsCompanyId(id);
        setError(current => current === recordsLoadError ? "" : current);
        return rows;
      }
    } catch (e) {
      if (isCurrent() && !controller.signal.aborted) {
        if ([401, 403, 404].includes(e.status)) { setRecords([]); setRecordsCompanyId(""); }
        if (e.status === 401) {
          localStorage.removeItem("token"); localStorage.removeItem("companyId");
          setCompanies([]); setCompanyId(""); setSigned(false);
        }
        setError(e.message);
        setRecordsLoadError(e.message);
      }
    } finally {
      if (isCurrent()) setRecordsLoading(false);
    }
  }
  useEffect(() => {
    if (signed) loadCompanies();
  }, [signed]);
  useEffect(() => {
    activeCompany.current = companyId;
    setError("");
    setRecords([]);
    setRecordsCompanyId("");
    setRecordsLoadError("");
    setConversionSource(null);
    setRelatedSource(null);
    setDraftSeed(null);
    setActiveParty(null);
    setDetail(null);
    setEditorReturn(null);
    setSearch("");
    setRegisterFilter({ page: "", value: "all" });
    setRegisterQuery({
      page: "",
      period: "all",
      from: "",
      to: "",
      party: "",
      sort: "newest",
    });
    setRegisterPage(1);
    setEditingMaster(null);
    setEditingDraft(null);
    if (companyId) setModal("");
    if (companyId) {
      localStorage.companyId = companyId;
      loadRecords(companyId, { refreshReports: false });
      const preferencesCurrent = workspaceScope.current.capture();
      api(`/companies/${companyId}/preferences`)
        .then((p) => {
          if (preferencesCurrent())
            setDocTemplate(p.document_template);
        })
        .catch((e) => {
          if (preferencesCurrent()) setError(e.message);
        });
    }
    return () => recordsAbort.current?.abort();
  }, [companyId]);
  useEffect(() => {
    let lastRefresh = 0;
    const refresh = () => {
      if (!signed || !companyId || document.visibilityState === "hidden" || document.querySelector(".overlay .modal") || Date.now() - lastRefresh < 1500) return;
      lastRefresh = Date.now();
      loadRecords(companyId);
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [signed, companyId]);
  const activeRegisterFilter =
    ["party", "item"].includes(page) && !supported("master_lifecycle") ? "all" : registerFilter.page === page ? registerFilter.value : "all";
  const transactionRegister = !["party", "item"].includes(page);
  const query =
    registerQuery.page === page
      ? registerQuery
      : { period: "all", from: "", to: "", party: "", sort: "newest" };
  const scopedRecords = records.filter(
    (r) =>
      r.kind === page &&
      (!transactionRegister ||
        ((!query.from || r.date >= query.from) &&
          (!query.to || r.date <= query.to) &&
          (!query.party || r.name === query.party))),
  );
  const filtered = scopedRecords
    .filter(
      (r) =>
        `${r.name} ${r.number} ${r.date}`
          .toLowerCase()
          .includes(search.toLowerCase()) &&
        (activeRegisterFilter === "all" ||
          (activeRegisterFilter === "active" && isActiveMaster(r)) ||
          (activeRegisterFilter === "inactive" && !isActiveMaster(r)) ||
          (activeRegisterFilter === "unpaid" &&
            r.posted && !r.cancelled &&
            Number(r.outstanding) > 0) ||
          (activeRegisterFilter === "paid" &&
            r.posted && !r.cancelled &&
            Number(r.outstanding) === 0) ||
          (activeRegisterFilter === "overdue" &&
            r.posted && !r.cancelled &&
            Number(r.outstanding) > 0 &&
            r.data?.due_date &&
            r.data.due_date < today()) ||
          (activeRegisterFilter === "draft" && !r.converted_to && !r.cancelled) ||
          (activeRegisterFilter === "converted" && !!r.converted_to) ||
          (activeRegisterFilter === "posted" && r.posted && !r.cancelled) ||
          (activeRegisterFilter === "unposted" && r.posted === false && !r.cancelled) ||
          (activeRegisterFilter === "cancelled" && !!r.cancelled)),
    )
    .sort((a, b) => compareRegisterRecords(a, b, query.sort));
  useEffect(
    () => setRegisterPage(1),
    [page, companyId, search, activeRegisterFilter, registerQuery],
  );
  const totalRegisterPages = Math.max(1, Math.ceil(filtered.length / 50));
  const currentRegisterPage = Math.min(registerPage, totalRegisterPages);
  const visibleRegisterRows = filtered.slice(
    (currentRegisterPage - 1) * 50,
    currentRegisterPage * 50,
  );
  async function saveCompany(body) {
    let c = await api("/companies", {
      method: "POST",
      body: JSON.stringify(body),
    });
    setCompanies([...companies, c]);
    setCompanyId(c.id);
    setModal("");
  }
  const [openAfterSave, setOpenAfterSave] = useState(null);
  useEffect(() => {
    if (!openAfterSave) return;
    setOpenAfterSave(null);
    beginDetail(openAfterSave);
  }, [openAfterSave]);
  async function saveRecord(body, key, { keepOpen = false } = {}) {
    const isCurrent = workspaceScope.current.capture();
    let saved;
    if (body.pay_now && !editingDraft) {
      const { pay_now, ...document } = body;
      saved = await api(`/companies/${companyId}/records/with-payment`, {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({ document, payment: pay_now }),
      });
    } else saved = await api(
      editingDraft
        ? ["estimate", "proforma", "sales_order", "purchase_order"].includes(editingDraft.kind)
          ? `/companies/${companyId}/drafts/${editingDraft.id}`
          : `/companies/${companyId}/documents/${editingDraft.id}`
        : `/companies/${companyId}/records`,
      {
        method: editingDraft ? "PUT" : "POST",
        headers: key ? { "Idempotency-Key": key } : {},
        body: JSON.stringify(body),
      },
    );
    if (!isCurrent()) return;
    const refreshed = await loadRecords();
    if (!isCurrent()) return;
    if (keepOpen && !editingDraft && !conversionSource && !relatedSource) {
      setEditorCycle((n) => n + 1);
      return;
    }
    closeRecord(refreshed);
    // Like Vyapar / Swipe: a newly saved customer document opens ready to share, print or collect.
    const savedId = saved?.document?.id || saved?.id;
    if (!editingDraft && !editorReturn && savedId && ["sales_invoice", "estimate", "proforma", "sales_order", "credit_note"].includes(body.kind)) {
      const fresh = Array.isArray(refreshed) && refreshed.find((row) => row.id === savedId);
      // Opened after the editor unmounts: its save is still "in flight" until this function returns.
      if (fresh) setOpenAfterSave(fresh);
    }
  }
  async function saveMaster(body) {
    const isCurrent = workspaceScope.current.capture();
    if (editingMaster) {
      await api(`/companies/${companyId}/masters/${editingMaster.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: body.name, ...body.data }),
      });
      if (!isCurrent()) return;
      const refreshed = await loadRecords();
      if (!isCurrent()) return;
      setEditingMaster(null);
      closeRecord(refreshed);
    } else await saveRecord(body);
  }
  async function saveOpening(body, key) {
    const isCurrent = workspaceScope.current.capture();
    await api(`/companies/${companyId}/stock/opening`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    });
    if (!isCurrent()) return;
    await loadRecords();
    if (!isCurrent()) return;
    setModal("");
  }
  async function saveStockAdjustment(body, key) {
    const isCurrent = workspaceScope.current.capture();
    await api(`/companies/${companyId}/stock/adjustments`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    });
    if (!isCurrent()) return;
    await loadRecords();
    if (!isCurrent()) return;
    setModal("");
  }
  function closeRecord(refreshed) {
    setConversionSource(null);
    setRelatedSource(null);
    setDraftSeed(null);
    setEditingDraft(null);
    setModal("");
    if (editorReturn) {
      setPage(editorReturn.page);
      setSearch(editorReturn.search);
      setRegisterFilter(editorReturn.filter);
      setRegisterQuery(editorReturn.query);
      // The originating editor still owns its posting lock while saveRecord is
      // completing. Reopen details after that editor unmounts, as for new sales.
      if (editorReturn.detail) setOpenAfterSave((Array.isArray(refreshed) && refreshed.find(row => row.id === editorReturn.detail.id)) || editorReturn.detail);
    }
    setEditorReturn(null);
  }
  function rememberEditorContext() {
    setEditorReturn({ page, search, filter: registerFilter, query: registerQuery, detail });
    setDetail(null);
    setSearch("");
  }
  function startReorder(rows) {
    if (postingNavigationBlocked()) return;
    if (!["owner", "editor"].includes(company?.role)) return;
    let seed;
    try { seed = reorderDraft(rows, records); } catch (reason) { setError(reason.message); return; }
    rememberEditorContext();
    setEditingDraft(null); setConversionSource(null); setRelatedSource(null);
    setDraftSeed(seed);
    setPage("purchase_order"); setEditorCycle(n => n + 1); setModal("record");
  }
  async function beginDetail(record) {
    if (postingNavigationBlocked()) return;
    const isCurrent = editorRequests.current.latest();
    setDetail(record);
    setDetailLoading(true);
    setDetailError("");
    try {
      const full = await api(`/companies/${companyId}/records/${record.id}`);
      if (isCurrent()) setDetail({ ...record, ...full });
    } catch (reason) {
      if (isCurrent()) setDetailError(reason.message);
    } finally {
      if (isCurrent()) setDetailLoading(false);
    }
  }
  async function cancelDocument(record, reason) {
    if (hasPendingPostings()) return;
    const release = registerPostingRequest({ busy: true });
    try {
      await api(`/companies/${companyId}/records/${record.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
      await loadRecords();
    } finally { release(); }
    await beginDetail(record);
  }
  function closeDetail() { if (postingNavigationBlocked()) return; editorRequests.current.latest(); setDetail(null); }
  async function beginEdit(record) {
    if (postingNavigationBlocked()) return;
    if (!["owner", "editor"].includes(company?.role)) return;
    const isCurrent = editorRequests.current.latest();
    try {
      const full = await api(`/companies/${companyId}/records/${record.id}`);
      if (!isCurrent() || postingNavigationBlocked()) return;
      rememberEditorContext();
      if (["party", "item"].includes(record.kind)) setEditingMaster(full);
      else {
        setEditingDraft(full);
        setConversionSource(null);
        setRelatedSource(null);
    setDraftSeed(null);
        setPage(record.kind);
      }
      setEditorCycle(n => n + 1);
      setModal("record");
    } catch (reason) {
      if (isCurrent()) setError(reason.message);
    }
  }
  async function beginConversion(record, targetKind) {
    if (postingNavigationBlocked()) return;
    if (!["owner", "editor"].includes(company?.role)) return;
    const isCurrent = editorRequests.current.latest();
    try {
      const full = await api(`/companies/${companyId}/records/${record.id}`);
      if (!isCurrent() || postingNavigationBlocked()) return;
      rememberEditorContext();
      setEditingDraft(null);
      setConversionSource(full);
      setRelatedSource(null);
    setDraftSeed(null);
      setPage(targetKind || (record.kind === "purchase_order" ? "purchase_bill" : "sales_invoice"));
      setEditorCycle(n => n + 1);
      setModal("record");
    } catch (reason) {
      if (isCurrent()) setError(reason.message);
    }
  }
  async function beginRelated(record, kind) {
    if (postingNavigationBlocked()) return;
    if (!["owner", "editor"].includes(company?.role)) return;
    const isCurrent = editorRequests.current.latest();
    try {
      const full = await api(`/companies/${companyId}/records/${record.id}`);
      if (!isCurrent() || postingNavigationBlocked()) return;
      rememberEditorContext();
      setRelatedSource({ ...record, ...full });
      setEditingDraft(null);
      setConversionSource(null);
      setPage(kind);
      setEditorCycle(n => n + 1);
      setModal("record");
    } catch (reason) {
      if (isCurrent()) setError(reason.message);
    }
  }
  async function downloadDocument(record, layout = "") {
    // A thermal receipt opens in the browser's PDF viewer, ready for the roll printer.
    const template = typeof layout === "string" ? layout : "";
    const tab = template.startsWith("thermal") ? window.open("about:blank", "_blank") : null;
    try {
      const res = await fetch(
        `/api/companies/${companyId}/documents/${record.id}.pdf${template ? `?template=${encodeURIComponent(template)}` : ""}`,
        { headers: { Authorization: `Bearer ${localStorage.token}` } },
      );
      if (!res.ok) throw Error("Document export failed");
      if (tab) { tab.location.href = URL.createObjectURL(await res.blob()); return; }
      downloadBlob(
        await res.blob(),
        `${record.kind}-${record.number || record.id.slice(0, 8)}.pdf`,
      );
    } catch (e) {
      tab?.close();
      setError(e.message);
    }
  }
  async function download(fmt) {
    try {
      let res = await fetch(`/api/companies/${companyId}/export.${fmt}`, {
        headers: { Authorization: `Bearer ${localStorage.token}` },
      });
      if (!res.ok) throw Error("Export failed");
      downloadBlob(await res.blob(), `apex-register.${fmt}`);
    } catch (e) {
      setError(e.message);
    }
  }
  function postingNavigationBlocked() {
    if (!hasPendingPostings()) return false;
    setError(postingNavigationMessage);
    return true;
  }
  useEffect(() => {
    const beforeUnload = event => {
      if (hasPendingPostings()) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, []);
  async function signOut() {
    if (postingNavigationBlocked()) return;
    if (document.querySelector(".overlay .modal")) return;
    const token = localStorage.token;
    if (token) {
      try {
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(3000),
        });
      } catch {}
    }
    localStorage.removeItem("token");
    localStorage.removeItem("companyId");
    activeCompany.current = "";
    setRecords([]);
    setCompanies([]);
    setCompanyId("");
    setPage("dashboard");
    setSigned(false);
  }
  function navigateWorkspace(kind, reference = "", filter = "all", resetFilters = false) {
    if (postingNavigationBlocked()) return;
    if (modal === "record") { window.dispatchEvent(new window.Event("apex-close-editor")); return; }
    if (document.querySelector(".overlay .modal")) return;
    editorRequests.current.latest();
    setDetail(null);
    const routes = {
      bank_transfer: "bank_account",
      opening_cash: "bank_account",
      opening_bank: "bank_account",
      opening_receivable: "party",
      opening_payable: "party",
      stock_opening: "item",
      stock_adjustment: "item",
      customer_refund: "payment_in",
      supplier_refund: "payment_out",
      advance_refund: "payment_in",
    };
    const destination = routes[kind] || kind;
    if (destination === "settings") setSettingsTab(["company", "documents", "accounting", "data", "access", "security", "commerce"].includes(reference) ? reference : "company");
    if (routeFeature[destination] && !supported(routeFeature[destination])) { setError("This workflow needs an updated connected API. Core workspaces remain available."); return; }
    setRegisterFilter({ page: destination, value: filter });
    if (resetFilters) setRegisterQuery({ page: destination, period: "all", from: "", to: "", party: "", sort: "newest" });
    setPage(labels[destination] ? destination : "reports");
    setSearch(routes[kind] ? "" : reference);
    setMenu(false);
    const group = sections.find((section) =>
      section.children?.some(([key]) => key === destination),
    );
    setExpanded(group?.label || "");
  }
  function createWorkspace(kind) {
    if (postingNavigationBlocked()) return;
    if (!["owner", "editor"].includes(company?.role)) return;
    setEditorReturn(null);
    setEditingDraft(null);
    setEditingMaster(null);
    setConversionSource(null);
    setRelatedSource(null);
    setDraftSeed(null);
    navigateWorkspace(kind);
    if (kind !== "pos") setModal("record");
  }
  const historyStarted = useRef(false);
  const fromHistory = useRef(false);
  useEffect(() => {
    const target = `#/${page}`;
    if (!historyStarted.current) {
      window.history.replaceState({ apexPage: page }, "", target);
      historyStarted.current = true;
    } else if (fromHistory.current) fromHistory.current = false;
    else if (window.location.hash !== target) window.history.pushState({ apexPage: page }, "", target);
  }, [page]);
  useEffect(() => {
    const back = () => {
      if (postingNavigationBlocked()) {
        window.history.pushState({ apexPage: page }, "", `#/${page}`);
        return;
      }
      if (modal === "record" || detail) {
        window.history.pushState({ apexPage: page }, "", `#/${page}`);
        if (modal === "record") window.dispatchEvent(new window.Event("apex-close-editor"));
        else closeDetail();
        return;
      }
      if (document.querySelector(".overlay .modal")) {
        window.history.pushState({ apexPage: page }, "", `#/${page}`);
        window.dispatchEvent(new window.Event("apex-close-workflow"));
        return;
      }
      const requested = window.location.hash.slice(2);
      fromHistory.current = true;
      editorRequests.current.latest();
      setPage(labels[requested] ? requested : "dashboard");
      setExpanded(sections.find(section => section.children?.some(([key]) => key === requested))?.label || "");
      setSearch("");
      setMenu(false);
    };
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, [page, modal, detail]);
  if (!signed) return <Auth onLogin={() => setSigned(true)} />;
  return (
    <div className="app">
      <a className="skip-link" href="#workspace-content" onClick={event => { event.preventDefault(); document.getElementById('workspace-content')?.focus(); }}>Skip to content</a>
      <WorkspaceSidebar open={menu} onClose={() => setMenu(false)}>
        <div className="brand workspace-brand"><span className="workspace-brand-symbol"><BookOpen size={23} /></span><span>Apex<span className="workspace-brand-light">Books</span><small>BUSINESS ACCOUNTING</small></span></div>
        <div className="company-switch">
          <span className="company-icon">
            <Building2 size={18} />
          </span>
          <span className="company-text">
            <small>WORKSPACE</small>
            <select
              title={companyDisplayName(company, companies)}
              aria-label="Choose company"
              value={companyId}
              onChange={(e) => {
                if (postingNavigationBlocked() || document.querySelector(".overlay .modal")) { e.currentTarget.value = companyId; return; }
                setCompanyId(e.target.value);
              }}
            >
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {companyDisplayName(c, companies)}
                </option>
              ))}
            </select>
            {company?.book_label?.trim() && <small className="company-book-label">Book: {company.book_label.trim()}</small>}
          </span>
          <ChevronDown size={14} />
        </div>
        <button className="sidebar-create button primary" aria-label="Create" aria-haspopup="menu" aria-expanded={createOpen} onKeyDown={event => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); if (!createOpen) window.dispatchEvent(new window.Event("apex-open-create")); } }} disabled={!["owner", "editor"].includes(company?.role)} onClick={() => window.dispatchEvent(new window.Event('apex-open-create'))}><Plus size={19} />New transaction</button>
        <nav aria-label="Main navigation">
          {sections.map((s) => (
            <React.Fragment key={s.label}>
              {(s.key === 'dashboard' || s.key === 'party' || s.label === 'Sales' || s.key === 'bank_account' || s.key === 'recurring') && <div className="nav-label">{{ dashboard: 'OVERVIEW', party: 'DIRECTORY', bank_account: 'ACCOUNTING', recurring: 'BUSINESS TOOLS' }[s.key] || 'TRANSACTIONS'}</div>}
              <button
                disabled={!!routeFeature[s.key] && !supported(routeFeature[s.key])}
                title={routeFeature[s.key] && !supported(routeFeature[s.key]) ? "Connected API upgrade required" : undefined}
                className={`nav-item ${page === s.key || s.children?.some(([key]) => key === page) ? "active" : ""}`}
                aria-current={!s.children && page === s.key ? "page" : undefined}
                aria-expanded={s.children ? expanded === s.label : undefined}
                onClick={() => {
                  editorRequests.current.latest();
                  if (s.children)
                    setExpanded(expanded === s.label ? "" : s.label);
                  else {
                    navigateWorkspace(s.key);
                  }
                }}
              >
                <s.icon size={18} />
                <span>{s.label}</span>
                {s.children && (
                  <ChevronDown
                    className={expanded === s.label ? "rotated" : ""}
                    size={14}
                  />
                )}
              </button>
              {s.children && expanded === s.label && (
                <div className="subnav">
                  {s.children.map(([k, l]) => (
                    <button
                      key={k}
                      className={page === k ? "active" : ""}
                      aria-current={page === k ? "page" : undefined}
                      onClick={() => {
                        navigateWorkspace(k);
                      }}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              )}
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-workspace-status">
            <span /> Your books, connected
          </div>
          <button onClick={() => { if (!postingNavigationBlocked()) setModal("company"); }}>
            <Plus size={16} /> Add company
          </button>
          <button onClick={signOut}>
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </WorkspaceSidebar>
      {menu && (
        <div className="mobile-backdrop" onClick={() => setMenu(false)} />
      )}
      <main className="main">
        <WorkspaceHeader
          company={company}
          page={page}
          labels={labels}
          records={records}
          onNavigate={navigateWorkspace}
          onOpenRecord={record => {
            if (record.kind === "party") { if (!postingNavigationBlocked()) setActiveParty(record); }
            else if (record.kind === "item") navigateWorkspace("item", record.name);
            else beginDetail(record);
          }}
          onCreate={createWorkspace}
          onMenu={() => setMenu(true)}
          menuOpen={menu}
          onCreateMenuChange={setCreateOpen}
        />
        <div className="content" id="workspace-content" tabIndex={-1}>
          {companyId && <div className="workspace-sync-line" role="status">{company?.book_label?.trim() && <strong className="workspace-book-label" title={`Book label: ${company.book_label}`}>{company.book_label}</strong>}<span className={recordsLoading ? "sync-active" : "sync-idle"} /><span>{recordsLoading ? recordsReady ? "Refreshing company data…" : `Loading company data${recordsProgress ? ` · ${recordsProgress.toLocaleString()} records` : "…"}` : recordsLoadError ? "Refresh needed" : recordsReady ? "Company data loaded" : "Connecting to your company…"}</span><button className="link" disabled={recordsLoading} onClick={() => loadRecords()}>Refresh</button></div>}
          {capabilities && CORE_ENHANCEMENTS.some(feature => !supported(feature)) && <details className="info-box"><summary>Some newer tools are unavailable on the connected API</summary><p>{capabilities.reason || "Update the API to enable all supported workflows."} Existing core workspaces remain available. Unsupported settings are not submitted.</p><button className="button secondary" onClick={() => setCapabilityRevision(value => value + 1)}>Check API support again</button></details>}
          {error && (
            <div className="error banner" role="alert">
              <span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError("")}><X size={18} /></button>
            </div>
          )}
          {!companyId ? (
            <section className="panel settings-panel">
              <div className="eyebrow green">WELCOME TO APEX BOOKS</div>
              <h1>Set up your first company</h1>
              <p>Create a separate workspace for your business, choose its tax profile, then add parties, items and opening balances.</p>
              <button className="button primary" onClick={() => setModal("company")}>
                <Plus size={17} /> Create company
              </button>
              <p>If you were invited to an existing company, ask its owner to add this registered email, then refresh.</p>
              <button className="button secondary" onClick={loadCompanies}>Refresh company access</button>
            </section>
          ) : routeFeature[page] && !supported(routeFeature[page]) ? (
            <section className="panel settings-panel"><h1>{labels[page]}</h1><p>{capabilities ? "This workflow needs an updated connected API." : "Checking connected API support…"} Core records and existing transactions remain available.</p><button className="button secondary" onClick={() => setCapabilityRevision(value => value + 1)}>Check API support again</button></section>
          ) : page === "recurring" ? (
            <RecurringWorkspace key={companyId} companyId={companyId} role={company.role} records={records} api={api} Modal={Modal} onReview={beginEdit} onRefresh={loadRecords} />
          ) : page === "reorder" ? (
            <ReorderWorkspace key={companyId} companyId={companyId} role={company.role} api={api} onReview={startReorder} onBack={() => navigateWorkspace("item")} />
          ) : page === "ledger" ? (
            <Ledger key={companyId} companyId={companyId} role={company?.role} />
          ) : page === "bank_account" ? (
            <BankWorkspace
              key={companyId}
              companyId={companyId}
              records={records}
              onParty={setActiveParty}
              role={company?.role}
              onSaved={() => loadRecords()}
            />
          ) : page === "day_book" ? (
            <DayBook key={companyId} companyId={companyId} records={records} api={api} labels={labels} onOpen={beginDetail} />
          ) : page === "reports" ? (
            <ReportsV2 companyId={companyId} records={records} />
          ) : page === "dashboard" ? (
            <BusinessOverview
              features={features}
              key={companyId}
              company={company}
              records={records}
              refreshKey={booksRevision}
              recordsReady={recordsReady}
              api={api}
              onNavigate={navigateWorkspace}
              onCreate={createWorkspace}
              onOpenRecord={beginDetail}
            />
          ) : page === "pos" ? (
            <PosWorkspace
              key={companyId}
              company={company}
              records={records}
              onParty={setActiveParty}
              api={api}
              refresh={loadRecords}
              onPdf={downloadDocument}
            />
          ) : page === "commerce" ? (
            <CommerceWorkspace key={companyId} company={company} records={records} api={api} onPdf={downloadDocument}/>
          ) : page === "settings" ? (
            <SettingsWorkspace
              apiBuild={capabilities}
              key={`${companyId}:${settingsTab}`}
              initialTab={settingsTab}
              company={company}
              onAddCompany={() => setModal("company")}
              sections={{
                commerce: <><h3>Bagisto integration</h3><p>Connect independent store channels and stock pools to this company. Review orders, deliveries and accounting reconciliation.</p><button type="button" className="primary" onClick={() => navigateWorkspace("commerce")}>Open ecommerce workspace</button></>,
                company: (
                  <>
                    <h3>Business profile</h3>
                    <div className="details">
                      <div>
                        <small>COMPANY NAME</small>
                        <strong>{company?.name || "—"}</strong>
                      </div>
                      <div>
                        <small>TAX PROFILE</small>
                        <strong>
                          {company?.tax_mode === "regular"
                            ? "GST regular"
                            : company?.tax_mode === "composition"
                              ? "Composition"
                              : "Not GST registered"}
                        </strong>
                      </div>
                      <div>
                        <small>GSTIN</small>
                        <strong>{company?.gstin || "Not registered"}</strong>
                      </div>
                      <div>
                        <small>STATE CODE</small>
                        <strong>{company?.state_code || "—"}</strong>
                      </div>
                      <div>
                        <small>ADDRESS</small>
                        <strong>{company?.address || "Not provided"}</strong>
                      </div>
                    </div>
                    {supported("company_book_labels") && <p><strong>Book label:</strong> {company?.book_label || "Not set"} <small>· workspace label only, not printed on invoices</small></p>}
                    <CompanyDetailsEditor
                      features={features}
                      company={company}
                      onSaved={(updated) =>
                        setCompanies((current) =>
                          current.map((c) =>
                            c.id === updated.id ? updated : c,
                          ),
                        )
                      }
                    />
                  </>
                ),
                documents: (
                  <>
                    <div className="settings-block" id="setting-branding">
                      <DocumentBranding
                        key={companyId + "branding"}
                        companyId={companyId}
                        role={company?.role}
                      />
                    </div>
                    <div className="settings-block" id="setting-prefixes">
                      <Prefixes companyId={companyId} role={company?.role} />
                    </div>
                    <div className="settings-block" id="setting-formats">
                      <label>
                        Document PDF layout
                        <select
                          className="form-select"
                          value={docTemplate}
                          disabled={company?.role !== "owner"}
                          onChange={async (e) => {
                            try {
                              const value = e.target.value;
                              await api(`/companies/${companyId}/preferences`, {
                                method: "PUT",
                                body: JSON.stringify({
                                  document_template: value,
                                }),
                              });
                              setDocTemplate(value);
                            } catch (err) {
                              setError(err.message);
                            }
                          }}
                        >
                          {[
                            "modern",
                            "vintage",
                            "mrp_discount",
                            "elegant",
                            "evergreen",
                            "classic",
                            "compact",
                            "bold",
                            "minimal",
                          ].map((t) => (
                            <option key={t} value={t}>
                              {t === "mrp_discount"
                                ? "MRP + Discount"
                                : t[0].toUpperCase() + t.slice(1)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="document-template-gallery">
                        {[
                          "modern",
                          "vintage",
                          "mrp_discount",
                          "elegant",
                          "evergreen",
                        ].map((t) => (
                          <a
                            key={t}
                            href={`/document-templates/${t}.png`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <img
                              loading="lazy"
                              src={`/document-templates/${t}.png`}
                              alt={`${t.replace("_", " ")} synthetic layout preview`}
                            />
                            <strong>
                              {t === "mrp_discount"
                                ? "MRP + Discount"
                                : t[0].toUpperCase() + t.slice(1)}
                            </strong>
                            <small>Open sample preview</small>
                          </a>
                        ))}
                      </div>
                      <p>
                        Previews use synthetic sample details. Logos, signature
                        images and bank details come from Document branding.
                      </p>
                    </div>
                  </>
                ),
                accounting: (
                  <>
                    <div className="settings-block" id="setting-openings">
                      <OpeningBalances
                        companyId={companyId}
                        records={records}
                        onParty={setActiveParty}
                        api={api}
                        refresh={loadRecords}
                        role={company?.role}
                      />
                    </div>
                    <div className="settings-block" id="setting-period">
                      <PeriodLock companyId={companyId} role={company?.role} />
                    </div>
                  </>
                ),
                data: (
                  <>
                    <div className="settings-block" id="setting-vyapar">
                      <VyaparImport
                        companyId={companyId}
                        role={company?.role}
                        onImported={async () => {
                          await Promise.all([loadCompanies(), loadRecords()]);
                        }}
                      />
                    </div>
                    <div className="settings-block" id="setting-masters">
                      <MasterImport
                        companyId={companyId}
                        role={company?.role}
                        onImported={() => loadRecords()}
                      />
                    </div>
                    <div className="settings-block" id="setting-export">
                      <CompanyDataExport
                        companyId={companyId}
                        role={company?.role}
                      />
                    </div>
                    <div className="settings-block" id="setting-backup">
                      {supportsFeature(features, 'chunked_backups') && company?.role === 'owner' ? <React.Suspense fallback={<p role="status">Loading complete backup tools…</p>}><CompleteBackup key={companyId} companyId={companyId} api={api} onRestored={async id => { await loadCompanies(); setCompanyId(id); }} /></React.Suspense> : <BackupRestore
                        companyId={companyId}
                        role={company?.role}
                        onRestored={async (id) => {
                          await loadCompanies();
                          setCompanyId(id);
                        }}
                      />}
                    </div>
                  </>
                ),
                access: <Members companyId={companyId} role={company?.role} />,
                security: (
                  <>
                    <div className="settings-block" id="setting-account">
                      <AccountSecurity onChanged={signOut} />
                    </div>
                    <div className="settings-block" id="setting-recovery">
                      <RecoveryCodes api={api} />
                    </div>
                    <div className="settings-block" id="setting-audit">
                      <AuditLog companyId={companyId} role={company?.role} />
                    </div>
                  </>
                ),
              }}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow green">
                    {page === "reports"
                      ? "BUSINESS INSIGHTS"
                      : "YOUR WORKSPACE"}
                  </div>
                  <h1>{labels[page]}</h1>
                  <p>
                    {page === "reports"
                      ? "Explore and export your transaction register."
                      : {
                          payment_in:
                            "Record receipts and apply them to customer invoices.",
                          payment_out:
                            "Pay suppliers and track allocated payments.",
                          sales_invoice:
                            "Create invoices, follow collections and review balances.",
                          purchase_bill:
                            "Record supplier bills and keep track of what you owe.",
                          estimate:
                            "Prepare quotations and convert accepted work to invoices.",
                          expense:
                            "Record business spending and review expense categories.",
                        }[page] ||
                        `Manage your ${labels[page]?.toLowerCase()} in one place.`}
                  </p>
                </div>
                <div className="heading-actions">
                  {page === "reports" ? (
                    <>
                      <button
                        className="button secondary"
                        onClick={() => download("xlsx")}
                      >
                        <Download size={16} /> Export XLSX
                      </button>
                      <button
                        className="button secondary"
                        onClick={() => download("pdf")}
                      >
                        <Download size={16} /> Export PDF
                      </button>
                    </>
                  ) : (
                    <>
                      {page === "item" && <button className="button secondary" disabled={!supported("low_stock_reorder")} title={!supported("low_stock_reorder") ? "Connected API upgrade required" : undefined} onClick={() => navigateWorkspace("reorder")}>Low stock & reorder</button>}
                      {page === "item" && (
                        <button
                          disabled={
                            !["owner", "editor"].includes(company?.role) || !records.some(
                              (r) => r.kind === "item" && r.data?.track_stock,
                            )
                          }
                          className="button secondary"
                          onClick={() => setModal("stock_opening")}
                        >
                          <Plus size={17} /> Opening stock
                        </button>
                      )}
                      {page === "item" && (
                        <button
                          disabled={
                            !["owner", "editor"].includes(company?.role) || !records.some(
                              (r) => r.kind === "item" && r.data?.track_stock,
                            )
                          }
                          className="button secondary"
                          onClick={() => setModal("stock_adjustment")}
                        >
                          <Plus size={17} /> Adjust stock
                        </button>
                      )}
                      <button
                        disabled={
                          !company ||
                          !recordsReady ||
                          !["owner", "editor"].includes(company?.role)
                        }
                        className="button primary"
                        onClick={() => createWorkspace(page)}
                      >
                        <Plus size={17} /> Add{" "}
                        {page === "party"
                          ? "party"
                          : labels[page]?.replace(/s$/, "").toLowerCase()}
                      </button>
                    </>
                  )}
                </div>
              </div>
              {!recordsReady ? (
                <section
                  className="panel report-loading"
                  role="status"
                  aria-live="polite"
                >
                  <h2>
                    {recordsLoadError
                      ? "Records could not be loaded"
                      : "Loading company records…"}
                  </h2>
                  <p>
                    {recordsLoadError ||
                      "Balances and transactions will appear when the records are ready."}
                  </p>
                  {recordsLoadError && (
                    <button
                      className="button secondary"
                      onClick={() => loadRecords()}
                    >
                      Try again
                    </button>
                  )}
                </section>
              ) : (
                <>
                  {["payment_in", "payment_out"].includes(page) && (
                    <React.Fragment>
                      <CreditSettlements
                        key={companyId + page + "credit"}
                        companyId={companyId}
                        kind={page}
                        records={records}
                        onParty={setActiveParty}
                        api={api}
                        refresh={loadRecords}
                        canWrite={["owner", "editor"].includes(company?.role)}
                      />
                      <Advances
                        key={companyId + page}
                        companyId={companyId}
                        kind={page}
                        records={records}
                        onParty={setActiveParty}
                        api={api}
                        refresh={loadRecords}
                        canWrite={["owner", "editor"].includes(company?.role)}
                      />
                    </React.Fragment>
                  )}
                  {transactionRegister && (
                    <RegisterControls
                      value={query}
                      records={records.filter((r) => r.kind === page)}
                      onChange={(value) => setRegisterQuery({ ...value, page })}
                      onReset={() => {
                        setRegisterQuery({
                          page,
                          period: "all",
                          from: "",
                          to: "",
                          party: "",
                          sort: "newest",
                        });
                        setSearch("");
                        setRegisterFilter({ page, value: "all" });
                      }}
                    />
                  )}
                  {!transactionRegister && supported("master_lifecycle") && <div className="register-controls expanded-controls"><label>Master status<select aria-label="Master status" value={activeRegisterFilter} onChange={event => setRegisterFilter({ page, value: event.target.value })}><option value="all">All · history retained</option><option value="active">Active</option><option value="inactive">Archived</option></select></label><p>Archived entries stay in history. Edit an entry to archive or reactivate it.</p></div>}
                  <RegisterOverview
                    page={page}
                    records={scopedRecords}
                    filter={activeRegisterFilter}
                    onFilter={(value) => setRegisterFilter({ page, value })}
                  />
                  <section
                    className={`panel register ${transactionRegister ? "transaction-register" : ""}`}
                  >
                    <div className="panel-header">
                      <div>
                        <h2>
                          {page === "reports" ? "All records" : labels[page]}
                        </h2>
                        <p>
                          {filtered.length}{" "}
                          {filtered.length === 1 ? "record" : "records"} in this
                          view
                        </p>
                      </div>
                      <div className="search">
                        <Search size={17} />
                        <input
                          aria-label="Search this register"
                          placeholder="Search party or reference"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>
                    </div>
                    {page === "party" && partyBalances?.companyId === companyId && (
                      <div className="party-balance-strip">
                        <div className="receive"><small>You'll get</small><strong>{money(partyBalances.totals.to_receive)}</strong></div>
                        <div className="pay"><small>You'll pay</small><strong>{money(partyBalances.totals.to_pay)}</strong></div>
                        <span>Closing balances as of {partyBalances.as_of}</span>
                        {overdueCount(records) > 0 && <button type="button" className="button secondary whatsapp" onClick={() => setRemindOverdue(true)}>Remind overdue ({overdueCount(records)})</button>}
                      </div>
                    )}
                    <div className="table-wrap" tabIndex={0}>
                      <table>
                        <thead>
                          <tr>
                            {transactionRegister ? (
                              <>
                                <th>DATE</th>
                                <th>DOCUMENT / PARTY</th>
                                <th>STATUS</th>
                                <th className="right">AMOUNT</th>
                                <th className="right">BALANCE</th>
                                <th className="right">ACTIONS</th>
                              </>
                            ) : (
                              <>
                                <th>NAME</th>
                                <th>DETAILS</th>
                                <th>TYPE</th>
                                {page === "party" && partyBalances?.companyId === companyId && <th className="right">BALANCE</th>}
                                <th className="right">ACTIONS</th>
                              </>
                            )}
                          </tr>
                        </thead>
                        <tbody>
                          {visibleRegisterRows.map((r) => (
                            <RecordRow
                              key={r.id}
                              r={r}
                              records={records}
                              onParty={setActiveParty}
                              balance={page === "party" && partyBalances?.companyId === companyId ? partyBalances.byId[r.id] || { net: "0" } : undefined}
                              onPdf={downloadDocument}
                              onOpen={beginDetail}
                              onConvert={["owner", "editor"].includes(company?.role) ? beginConversion : null}
                              onRelated={beginRelated}
                              onEdit={
                                ["owner", "editor"].includes(company?.role)
                                  ? beginEdit
                                  : null
                              }
                            />
                          ))}
                        </tbody>
                      </table>
                      {!filtered.length && (
                        <div className="empty">
                          <span>
                            <FileText size={22} />
                          </span>
                          <strong>
                            {scopedRecords.length ||
                            search ||
                            activeRegisterFilter !== "all"
                              ? "No matching records"
                              : page === "party" ? "Your party list starts here" : page === "item" ? "Build your item catalogue" : "No transactions in this view"}
                          </strong>
                          <p>{scopedRecords.length || search || activeRegisterFilter !== "all"
                            ? "No records match these filters. Clear them to see your existing transactions."
                            : ["owner", "editor"].includes(company?.role)
                              ? page === "party" ? "Add a customer or supplier so you can reuse their details on every document." : page === "item" ? "Add products or services with prices, tax defaults and optional stock tracking." : "Create your first document to start this register."
                              : "There are no records here yet. Your company owner can add them."}</p>
                          <button
                            className="button secondary"
                            onClick={() => {
                              setSearch("");
                              setRegisterFilter({ page, value: "all" });
                              setRegisterQuery({
                                page,
                                period: "all",
                                from: "",
                                to: "",
                                party: "",
                                sort: "newest",
                              });
                            }}
                          >
                            Clear filters
                          </button>
                          {["owner", "editor"].includes(company?.role) && (
                            <button
                              className="button primary"
                              onClick={() => createWorkspace(page)}
                            >
                              <Plus size={15} />
                              Add{" "}
                              {page === "party" ? "party" : labels[page]?.replace(/s$/, "").toLowerCase()}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="register-pagination">
                      <span>
                        {filtered.length
                          ? `${(currentRegisterPage - 1) * 50 + 1}–${Math.min(currentRegisterPage * 50, filtered.length)} of ${filtered.length}`
                          : "0 records"}
                      </span>
                      <div>
                        <button
                          className="button secondary"
                          disabled={currentRegisterPage === 1}
                          onClick={() => setRegisterPage((n) => n - 1)}
                        >
                          Previous
                        </button>
                        <span>
                          Page {currentRegisterPage} of {totalRegisterPages}
                        </span>
                        <button
                          className="button secondary"
                          disabled={currentRegisterPage >= totalRegisterPages}
                          onClick={() => setRegisterPage((n) => n + 1)}
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </section>
                  {page === "bank_account" && (
                    <div className="info-box">
                      Bank reconciliation and transaction matching are not
                      available yet.
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </main>
      {detail && <TransactionDetail api={api} features={features} record={detail} records={records} company={company} labels={labels}
        loading={detailLoading} error={detailError} onClose={closeDetail} onRetry={() => beginDetail(detail)}
        onEdit={beginEdit} onRelated={beginRelated} onConvert={beginConversion} onPdf={downloadDocument} onOpen={beginDetail} onCancelDocument={cancelDocument} />}
      {remindOverdue && company && <OverdueReminders records={records} company={company} onClose={() => setRemindOverdue(false)} />}
      {activeParty && (
        <PartyStatement
          features={features}
          key={companyId + activeParty.id}
          party={activeParty}
          companyId={companyId}
          api={api}
          Modal={Modal}
          close={() => setActiveParty(null)}
          onPdf={downloadDocument}
          onEdit={
            ["owner", "editor"].includes(company?.role)
              ? (row) => {
                  const full = records.find((r) => r.id === row.id);
                  if (full) {
                    setActiveParty(null);
                    beginEdit(full);
                  }
                }
              : undefined
          }
        />
      )}
      {modal === "company" && (
        <CompanyModal features={features} close={() => setModal("")} save={saveCompany} />
      )}{" "}
      {modal === "record" &&
        company &&
        (["party", "item"].includes(page) ? (
          <MasterForm
            features={features}
            kind={page}
            record={editingMaster}
            close={() => {
              setEditingMaster(null);
              closeRecord();
            }}
            save={saveMaster}
          />
        ) : (
          <RecordEditor
            features={features}
            key={`${companyId}-${page}-${editorCycle}`}
            api={api}
            Modal={Modal}
            labels={labels}
            documentKinds={documentKinds}
            money={money}
            today={today}
            kind={page}
            company={company}
            companyId={companyId}
            records={records}
            onParty={setActiveParty}
            source={editingDraft || conversionSource}
            relatedSource={relatedSource}
            draftSeed={draftSeed}
            edit={!!editingDraft}
            close={closeRecord}
            save={saveRecord}
          />
        ))}
      {modal === "stock_opening" && (
        <OpeningStock
          items={records.filter(
            (r) => r.kind === "item" && r.data?.track_stock,
          )}
          close={() => setModal("")}
          save={saveOpening}
        />
      )}
      {modal === "stock_adjustment" && (
        <StockAdjustment
          items={records.filter(
            (r) => r.kind === "item" && r.data?.track_stock,
          )}
          close={() => setModal("")}
          save={saveStockAdjustment}
        />
      )}
    </div>
  );
}
function Prefixes({ companyId, role }) {
  const year = businessFinancialYear(),
    defaults = {
      sales_invoice: "INV",
      estimate: "EST",
      sales_order: "SO",
      proforma: "PF",
      payment_in: "PIN",
      credit_note: "CN",
      pos: "POS",
      purchase_bill: "BILL",
      payment_out: "POUT",
      expense: "EXP",
      purchase_order: "PO",
      debit_note: "DN",
      bank_transfer: "TRF",
    };
  const [series, setSeries] = useState([]),
    [kind, setKind] = useState("sales_invoice"),
    [prefix, setPrefix] = useState("INV"),
    [error, setError] = useState(""),
    [saved, setSaved] = useState("");
  const activeCompany = useRef(companyId);
  activeCompany.current = companyId;
  const workspaceScope = useRef(createRequestScope(companyId));
  workspaceScope.current.setContext(companyId);
  async function load() {
    if (!companyId) return;
    const id = companyId;
    const isCurrent = workspaceScope.current.latest();
    try {
      const rows = await api(`/companies/${id}/number-series`);
      if (isCurrent()) {
        setSeries(rows);
        setError("");
      }
    } catch (e) {
      if (isCurrent()) setError(e.message);
    }
  }
  useEffect(() => {
    activeCompany.current = companyId;
    setSeries([]);
    setSaved("");
    load();
  }, [companyId]);
  useEffect(() => {
    setPrefix(
      series.find((s) => s.kind === kind && s.financial_year === year)
        ?.prefix || defaults[kind],
    );
  }, [kind, series, year]);
  async function save(e) {
    e.preventDefault();
    try {
      await api(`/companies/${companyId}/number-series`, {
        method: "PUT",
        body: JSON.stringify({ kind, financial_year: year, prefix }),
      });
      setSaved("Prefix saved");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <section className="member-settings">
      <h2>Transaction prefixes</h2>
      <p>
        Numbers are assigned automatically within the April–March financial
        year. Year {year}–{year + 1}.
      </p>
      {error && <div className="error banner">{error}</div>}
      {role === "owner" && (
        <form className="member-form" onSubmit={save}>
          <label>
            Document type
            <select
              className="form-select"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {Object.keys(defaults).map((k) => (
                <option value={k} key={k}>
                  {labels[k] || k}
                </option>
              ))}
            </select>
          </label>
          <label>
            Prefix
            <input
              required
              maxLength="6"
              pattern="[A-Z0-9-]+"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value.toUpperCase())}
            />
          </label>
          <button className="button primary">Save prefix</button>
        </form>
      )}
      {saved && <p>{saved}</p>}
    </section>
  );
}

function Members({ companyId, role }) {
  const [members, setMembers] = useState([]),
    [email, setEmail] = useState(""),
    [newRole, setNewRole] = useState("viewer"),
    [error, setError] = useState("");
  const activeCompany = useRef(companyId);
  activeCompany.current = companyId;
  const workspaceScope = useRef(createRequestScope(companyId));
  workspaceScope.current.setContext(companyId);
  async function load() {
    if (!companyId) return;
    const id = companyId;
    const isCurrent = workspaceScope.current.latest();
    try {
      const rows = await api(`/companies/${id}/members`);
      if (isCurrent()) {
        setMembers(rows);
        setError("");
      }
    } catch (e) {
      if (isCurrent()) setError(e.message);
    }
  }
  useEffect(() => {
    activeCompany.current = companyId;
    setMembers([]);
    setEmail("");
    load();
  }, [companyId]);
  async function add(e) {
    e.preventDefault();
    try {
      await api(`/companies/${companyId}/members`, {
        method: "POST",
        body: JSON.stringify({ email, role: newRole }),
      });
      setEmail("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }
  async function remove(member) {
    try {
      await api(
        `/companies/${companyId}/members/${encodeURIComponent(member.email)}`,
        { method: "DELETE" },
      );
      await load();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <section className="member-settings">
      <h2>Team access</h2>
      <p>
        Registered users can be given editor or view-only access to this
        company.
      </p>
      {error && <div className="error banner">{error}</div>}
      <div className="ledger-list">
        {members.map((m) => (
          <div key={m.email}>
            <strong>{m.email}</strong>
            <span>
              {m.role}{" "}
              {role === "owner" && m.role !== "owner" && (
                <button className="link" onClick={() => remove(m)}>
                  Remove
                </button>
              )}
            </span>
          </div>
        ))}
      </div>
      {role === "owner" && (
        <form className="member-form" onSubmit={add}>
          <label>
            User email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Registered user's email"
            />
          </label>
          <label>
            Role
            <select
              className="form-select"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
            </select>
          </label>
          <button className="button primary">Add member</button>
        </form>
      )}
    </section>
  );
}

function Ledger({ companyId, role }) {
  const canWrite = ["owner", "editor"].includes(role);
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [accounts, setAccounts] = useState([]),
    [journals, setJournals] = useState([]),
    [account, setAccount] = useState({ code: "", name: "", category: "asset" }),
    [entry, setEntry] = useState({
      date: today(),
      reference: "",
      memo: "",
      debit_account: "",
      credit_account: "",
      amount: "",
    }),
    [error, setError] = useState(""),
    [through, setThrough] = useState(today()),
    [balance, setBalance] = useState(null),
    [reversing, setReversing] = useState(null),
    [reversal, setReversal] = useState({
      date: today(),
      reference: "",
      reason: "",
    });
  const activeCompany = useRef(companyId);
  activeCompany.current = companyId;
  const workspaceScope = useRef(createRequestScope(companyId));
  workspaceScope.current.setContext(companyId);
  async function load() {
    if (!companyId) return;
    const id = companyId;
    const isCurrent = workspaceScope.current.latest();
    try {
      const [a, j, b] = await Promise.all([
        api(`/companies/${id}/accounts`),
        api(`/companies/${id}/journals`),
        api(`/companies/${id}/trial-balance?through=${through}`),
      ]);
      if (isCurrent()) {
        setAccounts(a);
        setJournals(j);
        setBalance(b);
      }
    } catch (e) {
      if (isCurrent()) setError(e.message);
    }
  }
  useEffect(() => {
    activeCompany.current = companyId;
    setAccounts([]);
    setJournals([]);
    setBalance(null);
    setError("");
    load();
  }, [companyId, through]);
  async function addAccount(e) {
    e.preventDefault();
    if (!canWrite || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`/companies/${companyId}/accounts`, {
        method: "POST",
        body: JSON.stringify(account),
      });
      setAccount({ code: "", name: "", category: "asset" });
      await load();
    } catch (err) {
      setError(err.message + (err instanceof TypeError || err.status === 0 || err.status === 408 || err.status >= 500 ? " Check journal history before changing the reference or posting again; the previous request may have completed." : ""));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function postJournal(e) {
    e.preventDefault();
    if (!canWrite || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      if (entry.debit_account === entry.credit_account)
        throw new Error("Choose different accounts for debit and credit");
      await api(`/companies/${companyId}/journals`, {
        method: "POST",
        body: JSON.stringify({
          date: entry.date,
          reference: entry.reference,
          memo: entry.memo,
          lines: [
            { account_id: entry.debit_account, debit: entry.amount },
            { account_id: entry.credit_account, credit: entry.amount },
          ],
        }),
      });
      setEntry({
        date: today(),
        reference: "",
        memo: "",
        debit_account: "",
        credit_account: "",
        amount: "",
      });
      await load();
    } catch (err) {
      setError(err.message + (err instanceof TypeError || err.status === 0 || err.status === 408 || err.status >= 500 ? " Check journal history before changing the reference or posting again; the previous request may have completed." : ""));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function reverseEntry(e) {
    e.preventDefault();
    if (!canWrite || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`/companies/${companyId}/journals/${reversing.id}/reverse`, {
        method: "POST",
        body: JSON.stringify(reversal),
      });
      setReversing(null);
      setReversal({ date: today(), reference: "", reason: "" });
      await load();
    } catch (err) {
      setError(err.message + (err instanceof TypeError || err.status === 0 || err.status === 408 || err.status >= 500 ? " Check journal history before changing the reference or posting again; the previous request may have completed." : ""));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  const accountName = (id) =>
    accounts.find((a) => a.id === id)?.name || "Account";
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow green">ACCOUNTING FOUNDATION</div>
          <h1>Ledger</h1>
          <p>{canWrite ? "Create accounts and record balanced manual journal entries." : "Read-only access: review accounts, journals and trial balance."}</p>
          <button className="button secondary" disabled={busy} onClick={load}>Refresh journal history</button>
        </div>
      </div>
      {error && <div className="error banner">{error}</div>}
      <div className="info-box ledger-note">
        New invoices, bills, payments, notes, POS sales and expenses post to the
        ledger automatically. Older prototype records remain unposted.
      </div>
      <div className="ledger-grid">
        <section className="panel settings-panel">
          <h2>Chart of accounts</h2>
          <p>{canWrite ? "Add the accounts you need for manual entries." : "Accounts used by your company’s posted transactions."}</p>
          {canWrite && <form className="form-grid ledger-form" onSubmit={addAccount}>
            <fieldset className="form-grid full submission-fields" disabled={!canWrite || busy}>
            <label>
              Account code
              <input
                required
                maxLength="32"
                value={account.code}
                onChange={(e) =>
                  setAccount({ ...account, code: e.target.value })
                }
                placeholder="e.g. 100"
              />
            </label>
            <label>
              Account name
              <input
                required
                maxLength="120"
                value={account.name}
                onChange={(e) =>
                  setAccount({ ...account, name: e.target.value })
                }
                placeholder="e.g. Cash"
              />
            </label>
            <label className="full">
              Category
              <select
                className="form-select"
                value={account.category}
                onChange={(e) =>
                  setAccount({ ...account, category: e.target.value })
                }
              >
                {["asset", "liability", "equity", "income", "expense"].map(
                  (c) => (
                    <option value={c} key={c}>
                      {c[0].toUpperCase() + c.slice(1)}
                    </option>
                  ),
                )}
              </select>
            </label>
            <button className="button primary full" disabled={!companyId}>
              Add account
            </button>
          </fieldset>
          </form>}
          <div className="ledger-list">
            {accounts.map((a) => (
              <div key={a.id}>
                <strong>
                  {a.code} · {a.name}
                </strong>
                <span>{a.category}</span>
              </div>
            ))}
            {!accounts.length && <p>No accounts added yet.</p>}
          </div>
        </section>
        {canWrite && <section className="panel settings-panel">
          <h2>New journal entry</h2>
          <p>Each entry has an equal debit and credit.</p>
          <form className="form-grid ledger-form" onSubmit={postJournal}>
            <fieldset className="form-grid full submission-fields" disabled={!canWrite || busy}>
            <label>
              Date
              <input
                type="date"
                required
                value={entry.date}
                onChange={(e) => setEntry({ ...entry, date: e.target.value })}
              />
            </label>
            <label>
              Reference
              <input
                required
                maxLength="80"
                value={entry.reference}
                onChange={(e) =>
                  setEntry({ ...entry, reference: e.target.value })
                }
              />
            </label>
            <label className="full">
              Memo
              <input
                maxLength="500"
                value={entry.memo}
                onChange={(e) => setEntry({ ...entry, memo: e.target.value })}
              />
            </label>
            {[
              ["debit_account", "Debit account"],
              ["credit_account", "Credit account"],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <select
                  className="form-select"
                  required
                  value={entry[key]}
                  onChange={(e) =>
                    setEntry({ ...entry, [key]: e.target.value })
                  }
                >
                  <option value="">Choose account</option>
                  {accounts.map((a) => (
                    <option value={a.id} key={a.id}>
                      {a.code} · {a.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label className="full">
              Amount (₹)
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={entry.amount}
                onChange={(e) => setEntry({ ...entry, amount: e.target.value })}
              />
            </label>
            <button
              className="button primary full"
              disabled={accounts.length < 2}
            >
              Post journal
            </button>
          </fieldset>
          </form>
        </section>}
      </div>
      <section className="panel settings-panel journal-history">
        <h2>Journal history</h2>
        <p>Posted entries are retained as an accounting record.</p>
        {journals.length ? (
          journals.map((j) => (
            <div className="journal-entry" key={j.id}>
              <strong>{j.reference}</strong>
              <span>
                {j.date} {j.memo && ` · ${j.memo}`}
                {j.reversed_by
                  ? " · Reversed"
                  : j.reversal_of
                    ? " · Reversal"
                    : ""}
              </span>
              {canWrite && !j.reversed_by && !j.reversal_of && !j.source_record_id && (
                <button className="link" onClick={() => setReversing(j)}>
                  Reverse entry
                </button>
              )}
              {j.lines.map((line, i) => (
                <div key={i}>
                  {accountName(line.account_id)}{" "}
                  <span>
                    Dr {money(line.debit)} · Cr {money(line.credit)}
                  </span>
                </div>
              ))}
            </div>
          ))
        ) : (
          <Empty
            title="No journal entries"
            text="Your posted manual entries will appear here."
          />
        )}
      </section>
      <section className="panel settings-panel journal-history">
        <div className="panel-header balance-heading">
          <div>
            <h2>Trial balance</h2>
            <p>All posted journal balances through the selected date.</p>
          </div>
          <label>
            Through
            <input
              type="date"
              value={through}
              onChange={(e) => setThrough(e.target.value)}
              required
            />
          </label>
        </div>
        {balance && (
          <div className="table-wrap" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>ACCOUNT</th>
                  <th className="right">DEBIT</th>
                  <th className="right">CREDIT</th>
                </tr>
              </thead>
              <tbody>
                {balance.accounts.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {a.code} · {a.name}
                    </td>
                    <td className="right">{money(a.debit)}</td>
                    <td className="right">{money(a.credit)}</td>
                  </tr>
                ))}
                <tr>
                  <td>
                    <strong>Total</strong>
                  </td>
                  <td className="right">
                    <strong>{money(balance.total_debit)}</strong>
                  </td>
                  <td className="right">
                    <strong>{money(balance.total_credit)}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>
      {reversing && (
        <Modal
          title="Reverse journal"
          subtitle={`Create an opposite entry for ${reversing.reference}. The original stays in history.`}
          close={() => { if (!busy) setReversing(null); }}
        >
          <form className="form-grid" onSubmit={reverseEntry}>
            <fieldset className="form-grid full submission-fields" disabled={!canWrite || busy}>
            <label>
              Date
              <input
                type="date"
                required
                value={reversal.date}
                onChange={(e) =>
                  setReversal({ ...reversal, date: e.target.value })
                }
              />
            </label>
            <label>
              New reference
              <input
                required
                maxLength="80"
                value={reversal.reference}
                onChange={(e) =>
                  setReversal({ ...reversal, reference: e.target.value })
                }
              />
            </label>
            <label className="full">
              Reason
              <input
                required
                maxLength="500"
                value={reversal.reason}
                onChange={(e) =>
                  setReversal({ ...reversal, reason: e.target.value })
                }
              />
            </label>
            {error && <div className="error full">{error}</div>}
            <div className="modal-actions full">
              <button
                type="button"
                className="button secondary"
                onClick={() => setReversing(null)}
              >
                Cancel
              </button>
              <button className="button primary">Create reversal</button>
            </div>
          </fieldset>
          </form>
        </Modal>
      )}
    </>
  );
}

function PaymentAllocationSummary({ record, records }) {
  if (!["payment_in", "payment_out"].includes(record.kind)) return null;
  const allocations = Array.isArray(record.data?.allocations)
    ? record.data.allocations
    : record.data?.applied_to
      ? [{ document_id: record.data.applied_to, amount: record.amount }]
      : [];
  if (!allocations.length) return null;
  return (
    <details className="payment-allocation-summary">
      <summary>
        {allocations.length} allocated document
        {allocations.length === 1 ? "" : "s"}
      </summary>
      {allocations.map((item, index) => {
        const target = records.find((row) => row.id === item.document_id);
        return (
          <div key={item.document_id || index}>
            {target?.number || "Document unavailable"} · {money(item.amount)}
          </div>
        );
      })}
    </details>
  );
}
function RecordActions({ r, onEdit, onPdf, onConvert, onRelated }) {
  const editable =
    onEdit &&
    (["party", "item"].includes(r.kind) ||
      ([
        "estimate",
        "sales_order",
        "proforma",
        "purchase_order",
        "sales_invoice",
        "purchase_bill",
        "expense",
        "pos",
        "credit_note",
        "debit_note",
        "payment_in",
        "payment_out",
        "bank_transfer",
      ].includes(r.kind) &&
        !r.converted_to));
  const downloadable =
    [
      ...documentKinds,
      "payment_in",
      "payment_out",
      "customer_refund",
      "supplier_refund",
      "advance_refund",
    ].includes(r.kind) && onPdf;
  const convertible =
    onConvert &&
    ["estimate", "proforma", "sales_order", "purchase_order"].includes(r.kind);
  // QuickBooks pattern: one primary action in the row, everything else in a menu.
  const actions = [
    ...(onRelated ? relatedRecordActions(r, !!onEdit) : []).map((action) => ({
      key: action.kind,
      label: action.label,
      run: () => onRelated(r, action.kind),
    })),
    ...(convertible
      ? [{ key: "convert", label: r.converted_to ? "Converted" : "Convert", disabled: !!r.converted_to, run: () => onConvert(r) }]
      : []),
    ...(editable ? [{ key: "edit", label: "Edit", run: () => onEdit(r) }] : []),
  ];
  const [primary, ...rest] = actions;
  return (
    <div className="record-actions">
      {primary && (
        <button
          className={"link" + (primary.key === "convert" ? " convert-link" : "")}
          disabled={primary.disabled}
          onClick={primary.run}
        >
          {primary.label}
        </button>
      )}
      {downloadable && (
        <button
          className="row-pdf"
          onClick={() => onPdf(r)}
          title="Download PDF"
          aria-label={`Download ${r.number || r.name} PDF`}
        >
          <Download size={14} />
        </button>
      )}
      {rest.length > 0 && (
        <ActionMenu label={`More actions for ${r.number || r.name}`} actions={rest} />
      )}
    </div>
  );
}
function RecordRow({ r, onPdf, onConvert, onEdit, onRelated, onOpen, records, onParty, balance }) {
  if (!["party", "item"].includes(r.kind)) {
    const invoice = ["sales_invoice", "purchase_bill", "pos"].includes(r.kind);
    const balance = Number(r.outstanding || 0);
    const status = r.cancelled ? "Cancelled" : r.converted_to
      ? "Converted"
      : ["estimate", "proforma", "sales_order", "purchase_order"].includes(r.kind)
        ? "Open draft"
        : r.posted === false ? "Legacy · unposted" : "Posted";
    const settlement = settlementLabel(r);
    const destination = records?.find(row => row.id === r.converted_to);
    const party = records?.find(
      (p) =>
        p.kind === "party" &&
        (p.id === r.data?.party_id ||
          p.name.trim().toLowerCase() === r.name?.trim().toLowerCase()),
    );
    return (
      <tr>
        <td data-label="Date">
          {new Date(r.date + "T00:00:00").toLocaleDateString("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </td>
        <td data-label="Document / party">
          <div className="transaction-reference">
            {onOpen ? (
              <button className="link" onClick={() => onOpen(r)}>
                {r.number || "No reference"}
              </button>
            ) : (
              <strong>{r.number || "No reference"}</strong>
            )}
            {party && onParty ? (
              <button
                className="link transaction-party"
                onClick={() => onParty(party)}
              >
                {r.name}
              </button>
            ) : (
              <span>{r.name}</span>
            )}
            {r.data?.due_date && <small>Due {r.data.due_date}</small>}
          </div>
          <PaymentAllocationSummary record={r} records={records} />
          {destination && <small>Converted to {destination.number || destination.name}</small>}
        </td>
        <td data-label="Status">
          <span
            className={`status-badge ${status === "Cancelled" ? "cancelled" : status === "Posted" || status === "Settled" || status === "Converted" ? "posted" : "draft"}`}
          >
            {status}
          </span>
          {settlement && <small className="settlement-state">{settlement}</small>}
        </td>
        <td data-label="Amount" className="right amount">
          {money(r.amount)}
        </td>
        <td
          data-label="Balance"
          className={`right ${balance > 0 ? "outstanding-amount" : ""}`}
        >
          {invoice && r.posted ? money(balance) : "—"}
        </td>
        <td data-label="Actions" className="right">
          <RecordActions
            r={r}
            onEdit={onEdit}
            onPdf={onPdf}
            onConvert={onConvert}
            onRelated={onRelated}
          />
        </td>
      </tr>
    );
  }
  return (
    <tr>
      <td>
        <div className="row-name">
          <span className="row-icon">
            {r.kind === "item" && r.data?.image_thumbnail ? (
              <img
                className="item-thumb"
                src={r.data.image_thumbnail}
                alt={r.name}
              />
            ) : (
              <FileText size={16} />
            )}
          </span>
          <span>
            <strong>
              {r.kind === "party" && onParty ? (
                <button className="link party-open" onClick={() => onParty(r)}>
                  {r.name}
                </button>
              ) : (
                r.name || "Untitled"
              )}
            </strong>
            {["party", "item"].includes(r.kind) && !isActiveMaster(r) && <span className="status-pill">Archived · history retained</span>}
            <small>
              {r.number ||
                (r.kind === "party"
                  ? r.data?.gstin || "Party"
                  : r.kind === "item"
                    ? r.data?.hsn
                      ? `HSN / SAC ${r.data.hsn}`
                      : "Item"
                    : "No reference")}
            </small>
          </span>
        </div>
        <PaymentAllocationSummary record={r} records={records} />
        {r.kind === "party" && (r.data?.phone || r.data?.email) && (
          <small className="master-contact">
            {[r.data.phone, r.data.email].filter(Boolean).join(" · ")}
          </small>
        )}
      </td>
      <td className="master-details">
        {r.kind === "party"
          ? [r.data?.gstin, r.data?.phone, r.data?.email].filter(Boolean).join(" · ") || "—"
          : r.kind === "item"
            ? [
                r.data?.hsn ? `HSN ${r.data.hsn}` : "",
                r.data?.sale_rate ? `${money(r.data.sale_rate)}${r.data?.unit ? ` / ${r.data.unit}` : ""}` : "",
                r.data?.gst_rate !== undefined && r.data?.gst_rate !== "" ? `GST ${r.data.gst_rate}%` : "",
              ].filter(Boolean).join(" · ") || "—"
            : new Date(r.date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
      </td>
      <td>
        <span className="pill">
          {r.kind === "sales_invoice" && r.data?.tax_mode === "composition"
            ? "Bill of supply"
            : r.kind === "party" && r.data?.party_type
              ? String(r.data.party_type).replace(/^./, (c) => c.toUpperCase())
              : r.kind === "item"
                ? String(r.data?.item_type || "item").replace(/^./, (c) => c.toUpperCase())
                : labels[r.kind] || r.kind}
        </span>
        {r.posted && ["sales_invoice", "purchase_bill"].includes(r.kind) && (
          <div className="document-row-status">
            <span
              className={`status-badge ${Number(r.outstanding) > 0 ? "draft" : "posted"}`}
            >
              {Number(r.outstanding) > 0
                ? Number(r.outstanding) < Number(r.amount)
                  ? "Part settled"
                  : "Unpaid"
                : "Settled"}
            </span>
            {Number(r.outstanding) > 0 && (
              <small>Balance {money(r.outstanding)}</small>
            )}
            {r.data?.due_date && (
              <small>
                Due{" "}
                {new Date(r.data.due_date + "T00:00:00").toLocaleDateString(
                  "en-IN",
                  { day: "numeric", month: "short" },
                )}
              </small>
            )}
          </div>
        )}
        {r.cancelled && <span className="pill cancelled-pill">Cancelled</span>}
        {r.posted === false && !r.cancelled &&
          [
            "sales_invoice",
            "pos",
            "purchase_bill",
            "payment_in",
            "payment_out",
            "expense",
            "credit_note",
            "debit_note",
          ].includes(r.kind) && (
            <span className="pill legacy-pill">Legacy · unposted</span>
          )}
      </td>
      {balance && (
        <td className={`right party-balance ${Number(balance.net) > 0 ? "receive" : Number(balance.net) < 0 ? "pay" : ""}`}>
          <strong>{money(Math.abs(Number(balance.net)))}</strong>
          <small>{Number(balance.net) > 0 ? "You'll get" : Number(balance.net) < 0 ? "You'll pay" : "Settled"}</small>
        </td>
      )}
      <td className="right amount">
        {!["party", "item"].includes(r.kind) && money(r.amount)}
        <RecordActions
          r={r}
          onEdit={onEdit}
          onPdf={onPdf}
          onConvert={onConvert}
        />
      </td>
    </tr>
  );
}
function Empty({ title, text }) {
  return (
    <div className="empty">
      <span>
        <ReceiptIndianRupee size={22} />
      </span>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}
createRoot(document.getElementById("root")).render(
  <WorkspaceBoundary>
    <DialogFocus />
    <App />
  </WorkspaceBoundary>,
);
