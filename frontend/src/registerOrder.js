// Keep register chronology aligned with the API, including same-day records.
export function newestRecordFirst(a, b) {
  return String(b.date || "").localeCompare(String(a.date || "")) ||
    String(b.data?.created_at || "").localeCompare(String(a.data?.created_at || "")) ||
    String(b.id || "").localeCompare(String(a.id || ""));
}

export function compareRegisterRecords(a, b, order = "newest") {
  if (order === "oldest") return newestRecordFirst(b, a);
  if (order === "amount") return Number(b.amount) - Number(a.amount) || newestRecordFirst(a, b);
  if (order === "balance") return Number(b.outstanding || 0) - Number(a.outstanding || 0) || newestRecordFirst(a, b);
  return newestRecordFirst(a, b);
}
