import React from 'react';
import {ledgerDate} from './ledgerFormat.js';
export default function NegativeCashNotice({data,through}) {
 const cash=data?.closing?.cash;
 if(cash==null||!Number.isFinite(Number(cash))||Number(cash)>=0)return null;
 return <aside className="info-box" role="note"><strong>Review negative cash through {ledgerDate(through)}.</strong> The posted cash ledger is below zero. Check opening balances, missing or misdated receipts, cash payments, transfers and imported entries against your records. This is a review cue, not proof of the cause; do not add a balancing entry without supporting evidence. The recorded balance has not been changed. Same-day row order may affect intermediate balances; the closing balance shown here is for the selected end date.</aside>;
}
