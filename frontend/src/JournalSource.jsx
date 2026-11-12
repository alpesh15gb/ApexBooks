import React from 'react';
export default function JournalSource({journal,onOpen}) {
 const source=journal.source_document;
 return <div className="journal-source">{source ? <><button className="link" onClick={()=>onOpen({id:source.id})}>{source.number||'View source document'} · {source.name}</button><div>{source.kind.replaceAll('_',' ')}{source.cancelled?' · Cancelled':''}</div><details><summary>Journal reference</summary>{journal.reference}</details></> : <><strong>{journal.reference}</strong>{journal.source_record_id&&<small>Source details unavailable</small>}</>}</div>;
}
