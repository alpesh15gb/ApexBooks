import { WEB_VERSION, WEB_BUILD_REVISION, normalizedBuildRevision } from "./buildInfo.js";
import React, { useRef, useState } from "react";
import {
  Building2,
  Database,
  FileText,
  LockKeyhole,
  Settings2,
  UsersRound,
  Search,
  ShoppingBag,
} from "lucide-react";

const tabs = [
  ["commerce", "Ecommerce", ShoppingBag, "Bagisto channels, stock, orders and reconciliation"],
  ["company", "Company", Building2, "Your business identity and tax profile"],
  [
    "documents",
    "Documents & branding",
    FileText,
    "Consistent documents, made yours",
  ],
  [
    "accounting",
    "Accounting",
    Settings2,
    "Opening balances and accounting periods",
  ],
  [
    "data",
    "Data & migration",
    Database,
    "Import, export and protect your books",
  ],
  [
    "access",
    "People & access",
    UsersRound,
    "Manage company roles and permissions",
  ],
  [
    "security",
    "Account security",
    LockKeyhole,
    "Protect your account and review changes",
  ],
];
export default function SettingsWorkspace({ company, sections, onAddCompany, apiBuild }) {
  const [active, setActive] = useState("company"),
    [visited, setVisited] = useState(() => new Set(["company"]));
  const [search, setSearch] = useState("");
  const keywords = {
    company: "business address gst gstin tax phone email",
    documents:
      "logo signature branding pdf templates format prefix invoice bank upi notes terms",
    accounting: "opening balances stock period lock financial year",
    data: "vyapar import export csv xlsx backup restore migration",
    access: "team users roles permissions members",
    security: "password recovery sessions revoke audit history",
  };
  const visibleTabs = tabs.filter(([key, title, , description]) =>
    `${title} ${description} ${keywords[key]}`
      .toLowerCase()
      .includes(search.trim().toLowerCase()),
  );
  const buttons = useRef({});
  const workspace = useRef(null);
  function select(key) {
    setActive(key);
    requestAnimationFrame(() =>
      workspace.current?.scrollIntoView({ block: "start", behavior: "auto" }),
    );
    setVisited((current) => new Set([...current, key]));
  }
  return (
    <div className="settings-workspace" ref={workspace}>
      <div className="page-heading">
        <div>
          <div className="workspace-kicker">
            <span />
            YOUR WORKSPACE
          </div>
          <h1>Settings</h1>
          <p>Set up your company, documents and the way you work.</p>
        </div>
        <button className="button secondary" onClick={onAddCompany}>
          <Building2 size={16} />
          Add company
        </button>
      </div>
      <details className="info-box"><summary>Build information</summary><p>Web {WEB_VERSION} · Source <code style={{ overflowWrap: 'anywhere' }}>{WEB_BUILD_REVISION}</code></p><p>API {apiBuild?.version || 'unknown'} · Source <code style={{ overflowWrap: 'anywhere' }}>{normalizedBuildRevision(apiBuild?.revision)}</code></p><small>Unknown means no verified source revision was supplied by the build or deployment. Version labels alone do not identify a tested revision.</small></details>
      <div className="settings-layout">
        <aside className="settings-rail">
          <div className="settings-company">
            <span>{company?.name?.[0] || "A"}</span>
            <strong>
              {company?.name || "Your company"}
              <small>
                {company?.tax_mode === "regular"
                  ? "GST registered"
                  : company?.tax_mode === "composition"
                    ? "Composition"
                    : "Non-GST business"}
              </small>
            </strong>
          </div>
          <label className="settings-search">
            <Search size={16} />
            <input
              aria-label="Find a setting"
              placeholder="Find a setting…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div
            role="tablist"
            aria-label="Settings categories"
            aria-orientation="vertical"
          >
            {visibleTabs.map(([key, title, Icon], index) => (
              <button
                key={key}
                ref={(node) => {
                  buttons.current[key] = node;
                }}
                id={`settings-tab-${key}`}
                role="tab"
                aria-selected={active === key}
                aria-controls={`settings-panel-${key}`}
                tabIndex={
                  active === key ||
                  (!visibleTabs.some((tab) => tab[0] === active) && index === 0)
                    ? 0
                    : -1
                }
                onClick={() => {
                  select(key);
                  setSearch("");
                }}
                onKeyDown={(e) => {
                  let next;
                  if (["ArrowDown", "ArrowRight"].includes(e.key))
                    next = visibleTabs[(index + 1) % visibleTabs.length][0];
                  if (["ArrowUp", "ArrowLeft"].includes(e.key))
                    next =
                      visibleTabs[
                        (index - 1 + visibleTabs.length) % visibleTabs.length
                      ][0];
                  if (e.key === "Home") next = visibleTabs[0][0];
                  if (e.key === "End") next = visibleTabs.at(-1)[0];
                  if (next) {
                    e.preventDefault();
                    select(next);
                    buttons.current[next]?.focus();
                  }
                }}
              >
                <Icon size={17} />
                {title}
              </button>
            ))}
          </div>
          {!visibleTabs.length && (
            <p className="settings-no-match">
              No matching settings. Try logo, prefix, backup or GST.
            </p>
          )}
          <p className="settings-scope-note">
            Changes apply to this company. Account security applies to your
            sign-in.
          </p>
        </aside>
        <div className="settings-content">
          {tabs.map(
            ([key, title, , description]) =>
              visited.has(key) && (
                <section
                  key={key}
                  role="tabpanel"
                  id={`settings-panel-${key}`}
                  aria-labelledby={`settings-heading-${key}`}
                  hidden={active !== key}
                >
                  <div className="settings-section-heading">
                    <h2 id={`settings-heading-${key}`}>{title}</h2>
                    <p>{description}</p>
                  </div>
                  <div className="settings-jump-links">
                    {(
                      {
                        documents: [
                          ["branding", "Logo & signature"],
                          ["prefixes", "Transaction prefixes"],
                          ["formats", "Document layouts"],
                        ],
                        data: [
                          ["vyapar", "Vyapar import"],
                          ["masters", "CSV import"],
                          ["export", "Export data"],
                          ["backup", "Backup & restore"],
                        ],
                        accounting: [
                          ["openings", "Opening balances"],
                          ["period", "Period lock"],
                        ],
                        security: [
                          ["account", "Account security"],
                          ["recovery", "Recovery codes"],
                          ["audit", "Audit history"],
                        ],
                      }[key] || []
                    ).map(([id, label]) => (
                      <button
                        key={id}
                        onClick={() =>
                          document
                            .getElementById(`setting-${id}`)
                            ?.scrollIntoView({
                              behavior: "smooth",
                              block: "start",
                            })
                        }
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="panel settings-panel">{sections[key]}</div>
                </section>
              ),
          )}
        </div>
      </div>
    </div>
  );
}
