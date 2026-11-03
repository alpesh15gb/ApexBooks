import { useMemo } from "react";
import { compareRegisterRecords } from "./registerOrder.js";
import { isActiveMaster } from "./masterLifecycle.js";

export function selectRegisterRecords({ records, page, query, search, activeRegisterFilter, asOf }) {
  const transactionRegister = !["party", "item"].includes(page);
  const normalizedSearch = search.toLowerCase();
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
          .includes(normalizedSearch) &&
        (activeRegisterFilter === "all" ||
          (activeRegisterFilter === "active" && isActiveMaster(r)) ||
          (activeRegisterFilter === "inactive" && !isActiveMaster(r)) ||
          (activeRegisterFilter === "unpaid" &&
            r.posted &&
            Number(r.outstanding) > 0) ||
          (activeRegisterFilter === "paid" &&
            r.posted &&
            Number(r.outstanding) === 0) ||
          (activeRegisterFilter === "overdue" &&
            r.posted &&
            Number(r.outstanding) > 0 &&
            r.data?.due_date &&
            r.data.due_date < asOf) ||
          (activeRegisterFilter === "draft" && !r.converted_to) ||
          (activeRegisterFilter === "converted" && !!r.converted_to) ||
          (activeRegisterFilter === "posted" && r.posted) ||
          (activeRegisterFilter === "unposted" && r.posted === false)),
    )
    .sort((a, b) => compareRegisterRecords(a, b, query.sort));
  return { scopedRecords, filtered };
}

// A component-local memo, never a cross-company or persistent data cache.
export function useRegisterRecords({ companyId, records, page, query, search, activeRegisterFilter, asOf }) {
  const { from, to, party, sort } = query;
  return useMemo(() => selectRegisterRecords({ records, page, query: { from, to, party, sort }, search, activeRegisterFilter, asOf }),
    [companyId, records, page, from, to, party, sort, search, activeRegisterFilter, asOf]);
}
