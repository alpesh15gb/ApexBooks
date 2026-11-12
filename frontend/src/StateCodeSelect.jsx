import React from 'react';
import {stateCodes} from './stateCodes.js';
export default function StateCodeSelect({value='',...props}) {
 const known=stateCodes.some(([code])=>code===value);
 return <select {...props} value={value}><option value="">Choose state / territory</option>{value&&!known&&<option value={value}>Saved code {value} · review required</option>}{stateCodes.map(([code,name])=><option key={code} value={code}>{name} ({code})</option>)}</select>;
}
