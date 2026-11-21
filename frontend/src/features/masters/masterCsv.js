const aliases = {'type':'party_type','hsn / sac':'hsn','sale rate':'sale_rate','purchase rate':'purchase_rate','gst rate':'gst_rate','stock tracked':'track_stock','item type':'item_type','tax treatment':'tax_treatment'};
const fields = {
  party: ['gstin','address','phone','email','party_type'],
  item: ['hsn','unit','sale_rate','purchase_rate','gst_rate','track_stock','barcode','item_type','tax_treatment'],
};
export function decodeMasterCsv(bytes) {
  try {
    const text = new TextDecoder('utf-8', {fatal:true}).decode(bytes);
    if (text.includes('\0')) throw Error('NUL');
    return text;
  } catch { throw Error('CSV encoding is invalid. Save the file as UTF-8 and try again.'); }
}
export function parseMasterCsv(input, kind) {
  const source = input.replace(/^\uFEFF/, ''), rows = [];
  let row = [], field = '', quoted = false, closed = false, line = 1, start = 1;
  const finishCell = () => { row.push(field); field = ''; closed = false; };
  const finishRow = () => { finishCell(); if (row.some(value => value.trim())) rows.push({values:row,line:start}); row = []; };
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (quoted) {
      if (char === '"') {
        if (source[i + 1] === '"') { field += '"'; i++; }
        else { quoted = false; closed = true; }
      } else { field += char; if (char === '\n' || (char === '\r' && source[i + 1] !== '\n')) line++; }
      continue;
    }
    if (char === ',') { finishCell(); continue; }
    if (char === '\r' || char === '\n') {
      if (char === '\r' && source[i + 1] === '\n') i++;
      finishRow(); line++; start = line; continue;
    }
    if (closed) { if (char === ' ' || char === '\t') continue; throw Error(`CSV row ${line}: unexpected text after a closing quote.`); }
    if (char === '"') { if (field.length) throw Error(`CSV row ${line}: quote must begin a field.`); quoted = true; }
    else field += char;
  }
  if (quoted) throw Error(`CSV row ${line}: unclosed quoted field.`);
  finishRow();
  const headers = (rows.shift()?.values || []).map(value => value.trim().toLowerCase()).map(value => aliases[value] || value);
  if (!headers.includes('name')) throw Error('CSV needs a name column');
  const duplicate = headers.find((header, index) => header && headers.indexOf(header) !== index);
  if (duplicate) throw Error(`CSV repeats the ${duplicate} column. Keep one column for each field.`);
  const allowed = fields[kind];
  if (!allowed) throw Error('Choose parties or items');
  const supported = new Set(['name', ...allowed]);
  return rows.map(({values,line}) => {
    if (values.length !== headers.length) throw Error(`CSV row ${line}: expected ${headers.length} columns, found ${values.length}. Include empty fields with commas.`);
    values.forEach((value,index) => { if (value.trim() && !supported.has(headers[index])) throw Error(`CSV row ${line}, column ${index + 1}: populated column has no supported header for ${kind === 'party' ? 'parties' : 'items'}.`); });
    const result = {name:values[headers.indexOf('name')]?.trim() || ''};
    for (const key of allowed) if (headers.includes(key)) result[key] = values[headers.indexOf(key)]?.trim() || (key === 'party_type' ? 'both' : key === 'item_type' ? 'goods' : key === 'tax_treatment' ? 'taxable' : key === 'track_stock' ? 'false' : key.endsWith('rate') ? '0' : '');
    if (!result.name) throw Error(`Name is missing on CSV row ${line}`);
    return result;
  });
}
