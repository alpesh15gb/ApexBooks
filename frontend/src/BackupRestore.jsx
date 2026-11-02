import React, { useState } from "react";
import { Download, Upload } from "lucide-react";
const b64 = (bytes) => {
  let s = "";
  for (let i = 0; i < bytes.length; i += 8192)
    s += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(s);
};
const bytes = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
async function keyFor(password, salt) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 250000, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}
export default function BackupRestore({ companyId, role, onRestored }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [password, setPassword] = useState(""),
    [file, setFile] = useState(null),
    [name, setName] = useState(""),
    [preview, setPreview] = useState(null),
    [encoded, setEncoded] = useState(""),
    [success, setSuccess] = useState("");
  if (role !== "owner") return null;
  async function request(path, body) {
    const response = await fetch("/api" + path, {
      method: body ? "POST" : "GET",
      headers: {
        Authorization: `Bearer ${localStorage.token}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw Error(
        typeof detail.detail === "string"
          ? detail.detail
          : "The backup operation failed",
      );
    }
    return response;
  }
  async function download() {
    setBusy(true);
    setError("");
    try {
      let content = new Uint8Array(
          await (await request(`/companies/${companyId}/backup`)).arrayBuffer(),
        ),
        suffix = "json.gz",
        mime = "application/gzip";
      if (password) {
        if (password.length < 12)
          throw Error("Use a backup password of at least 12 characters");
        const salt = crypto.getRandomValues(new Uint8Array(16)),
          iv = crypto.getRandomValues(new Uint8Array(12)),
          key = await keyFor(password, salt);
        content = JSON.stringify({
          format: "apex-encrypted-backup",
          version: 1,
          salt: b64(salt),
          iv: b64(iv),
          ciphertext: b64(
            new Uint8Array(
              await crypto.subtle.encrypt(
                { name: "AES-GCM", iv },
                key,
                content,
              ),
            ),
          ),
        });
        suffix = "apexbackup";
        mime = "application/json";
      }
      const url = URL.createObjectURL(new Blob([content], { type: mime })),
        link = document.createElement("a");
      link.href = url;
      link.download = `apex-${companyId.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}.${suffix}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess(
        "Backup downloaded. Keep your file and any backup password securely.",
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function inspect(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      if (!file) throw Error("Choose an Apex Books backup");
      if (file.size > 50_000_000)
        throw Error("Backup exceeds the 50 MB uncompressed file limit");
      let content = new Uint8Array(await file.arrayBuffer());
      if (content[0] !== 31) {
        const text = new TextDecoder().decode(content);
        let envelope;
        try {
          envelope = JSON.parse(text);
        } catch {
          throw Error("Invalid backup file");
        }
        if (envelope.format === "apex-encrypted-backup") {
          if (envelope.version !== 1)
            throw Error("Unsupported encrypted backup version");
          if (!password)
            throw Error("Enter the password used to encrypt this backup");
          try {
            const key = await keyFor(password, bytes(envelope.salt));
            content = new Uint8Array(
              await crypto.subtle.decrypt(
                { name: "AES-GCM", iv: bytes(envelope.iv) },
                key,
                bytes(envelope.ciphertext),
              ),
            );
          } catch {
            throw Error(
              "The password is incorrect or the encrypted backup is damaged",
            );
          }
        } else if ("CompressionStream" in window) {
          content = new Uint8Array(
            await new Response(
              new Blob([content])
                .stream()
                .pipeThrough(new CompressionStream("gzip")),
            ).arrayBuffer(),
          );
        }
      }
      const value = b64(content),
        report = await (
          await request("/backups/restore/preview", {
            company_name: name,
            backup_base64: value,
          })
        ).json();
      setEncoded(value);
      setPreview(report);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function restore() {
    setBusy(true);
    setError("");
    try {
      const result = await (
        await request("/backups/restore/commit", {
          company_name: name,
          backup_base64: encoded,
          digest: preview.digest,
        })
      ).json();
      setSuccess("Backup restored into a separate company.");
      setPreview(null);
      await onRestored?.(result.company_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="member-settings">
      <h2>Backup and restore</h2>
      <p>
        Back up documents, ledger, stock, bank reconciliation and settings.
        Restore creates a separate company.
      </p>
      <label>
        Backup password
        <input
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setPreview(null);
          }}
          placeholder="Optional; at least 12 characters to encrypt a download"
        />
      </label>
      <button className="button secondary" onClick={download} disabled={busy}>
        <Download size={16} />
        Download backup
      </button>
      <h3>Restore a company</h3>
      <form className="form-grid" onSubmit={inspect}>
        <label>
          Company name after restore
          <input
            required
            maxLength={120}
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setPreview(null);
            }}
          />
        </label>
        <label>
          Backup file
          <input
            type="file"
            required
            accept=".json,.gz,.apexbackup"
            onChange={(e) => {
              setFile(e.target.files?.[0]);
              setPreview(null);
            }}
          />
        </label>
        <p className="full">
          For encrypted backups, enter the password above. Team access and login
          credentials are excluded; invite team members after restoring.
        </p>
        <button className="button secondary" disabled={busy || !file}>
          <Upload size={16} />
          Validate backup
        </button>
      </form>
      {preview && (
        <div className="info-box">
          <strong>
            {preview.company_name} → {name}
          </strong>
          <p>
            {preview.counts.records} records · {preview.counts.journals}{" "}
            balanced journals · {preview.counts.stock_movements} stock
            movements.
          </p>
          <button className="button primary" onClick={restore} disabled={busy}>
            Restore as separate company
          </button>
        </div>
      )}
      {busy && <p role="status">Processing backup…</p>}
      {error && (
        <div className="error banner" role="alert">
          {error}
        </div>
      )}
      {success && <p role="status">{success}</p>}
    </section>
  );
}
