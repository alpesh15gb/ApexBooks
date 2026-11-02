# India business-date defaults

ApexBooks' current Indian accounting workflows use **Asia/Kolkata** for the current business date, independent of the server or user's device timezone.

- `backend/business_calendar.py` derives the day from an aware instant. `frontend/src/businessDate.js` uses an explicit India timezone. A naive backend instant is rejected, rather than interpreted in the machine's timezone.
- New records that omit a date, optional reorder/credit report dates, recurring eligibility, web form defaults, dashboard ranges, ageing/report filters and current financial-year choices share this calendar.
- Financial years begin on April 1 in India. At 18:30 UTC on March 31, the current India date and financial year advance together.
- Explicit `YYYY-MM-DD` dates from users, source documents, imports or saved records remain unchanged. Month/rolling-period arithmetic uses date-only containers, not a conversion of historical dates.
- Audit, session, export and other event timestamps remain aware UTC. Unrelated archival/restore metadata dates were not mass-rewritten.
- No operating-system, database or production timezone setting is changed. Minimal Windows Python installations without an IANA timezone database use the current Indian UTC+05:30 offset for default-date calculation; historical explicit dates are not converted.

Deterministic tests cover India midnight, March 31/April 1, leap-month ranges, explicit report dates, and generated document numbering on either side of the financial-year boundary. Native-client parity is tracked by its own build and acceptance checks.
