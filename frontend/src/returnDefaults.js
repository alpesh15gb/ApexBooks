// A displayed quantity allowance is a snapshot, never a reservation or value cap.
export function remainingReturnDraftLines(lines) {
  return lines.filter(line => !(line.return_capacity_scope === 'additional_returns' && line.remaining_return_quantity != null && Number(line.remaining_return_quantity) === 0)).map(line => ({
    ...line,
    quantity: line.return_capacity_scope === 'additional_returns' && line.remaining_return_quantity != null ? String(line.remaining_return_quantity) : '',
    return_capacity_reason: line.return_capacity_reason || (line.return_capacity_scope !== 'additional_returns' ? 'Remaining quantity is unavailable; review prior returns before entering a quantity.' : null),
  }));
}
