import test from 'node:test';
import assert from 'node:assert/strict';
import { businessDate, businessFinancialYear, businessPeriodDates, businessDashboardRange } from '../src/businessDate.js';
test('business date flips at India midnight regardless of device timezone',()=>{
 const before=new Date('2026-11-02T18:29:59Z'),after=new Date('2026-11-02T18:30:00Z');
 assert.equal(businessDate(before),'2026-11-02');assert.equal(businessDate(after),'2026-11-03');
 assert.equal(businessDate(new Date('2026-11-02T08:30:00-10:00')),'2026-11-03');
});
test('financial year and dashboard switch together at India April first',()=>{
 const before=new Date('2026-03-31T18:29:59Z'),after=new Date('2026-03-31T18:30:00Z');
 assert.equal(businessFinancialYear(before),2025);assert.equal(businessFinancialYear(after),2026);
 assert.deepEqual(businessDashboardRange('year',after),{start:'2026-04-01',end:'2026-04-01'});
 assert.deepEqual(businessPeriodDates('year',before),{from:'2025-04-01',to:'2026-03-31'});
});
test('period arithmetic keeps calendar boundaries and leap days without local timezone conversion',()=>{
 const instant=new Date('2024-02-29T18:30:00Z');
 assert.deepEqual(businessPeriodDates('today',instant),{from:'2024-03-01',to:'2024-03-01'});
 assert.deepEqual(businessPeriodDates('last_month',instant),{from:'2024-02-01',to:'2024-02-29'});
 assert.deepEqual(businessPeriodDates('month',instant),{from:'2024-03-01',to:'2024-03-31'});
 assert.deepEqual(businessDashboardRange('month',instant),{start:'2024-03-01',end:'2024-03-01'});
 assert.deepEqual(businessPeriodDates('30days',instant),{from:'2024-02-01',to:'2024-03-01'});
 assert.deepEqual(businessPeriodDates('all',instant),{from:'',to:''});
});
