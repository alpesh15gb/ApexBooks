// Current India business calendar; never reinterpret an explicit YYYY-MM-DD.
export const BUSINESS_TIME_ZONE = 'Asia/Kolkata';
const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: BUSINESS_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' });
export function businessDate(now = new Date()) {
  const parts = Object.fromEntries(formatter.formatToParts(now).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}
export function businessFinancialYear(now = new Date()) {
  const [year, month] = businessDate(now).split('-').map(Number);
  return year - (month < 4 ? 1 : 0);
}
// Calendar arithmetic uses UTC solely as a date container, not as a conversion
// of user-selected dates or a substitute for India's current business date.
const dateOnly = (year, zeroBasedMonth, day) => new Date(Date.UTC(year, zeroBasedMonth, day)).toISOString().slice(0, 10);
export function businessPeriodDates(period, now = new Date()) {
  const today = businessDate(now), [year, month, day] = today.split('-').map(Number);
  if (period === 'all') return { from: '', to: '' };
  if (period === 'today') return { from: today, to: today };
  if (period === 'month') return { from: dateOnly(year, month - 1, 1), to: dateOnly(year, month, 0) };
  if (period === 'last_month') return { from: dateOnly(year, month - 2, 1), to: dateOnly(year, month - 1, 0) };
  if (period === '30days') return { from: dateOnly(year, month - 1, day - 29), to: today };
  return { from: `${businessFinancialYear(now)}-04-01`, to: today };
}
export function businessDashboardRange(period, now = new Date()) {
  return { start: businessPeriodDates(period, now).from, end: businessDate(now) };
}
