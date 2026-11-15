// Journal memos may carry internal record ids; people see the date and a readable note only.
const RECORD_ID = /\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;

export function tidyJournalMemo(journal) {
  const text = (journal.memo || "").replace(RECORD_ID, "").trim();
  const kind = (journal.source_document?.kind || "").replaceAll("_", " ");
  return text && text !== kind ? text : "";
}
