# Billing below zero stock

Sales invoices and POS may post tracked items with no quantity on hand. Selling
3 units from zero leaves -3; selling another 2 leaves -5. The same API behavior
applies to web, Windows and Android. No client override or purchase entry is
required before billing. Chronology, period locks, tenant permissions, payment
limits and linked-return quantity checks still apply.

Stock already reserved for accepted online-store orders stays protected. Online
checkout continues to require available stock, and published sellable quantities
remain clamped to zero. A manual write-off or supplier return does not gain
permission to remove nonexistent stock merely because billing allows negatives.

## Valuation

Negative-stock billing uses the current carrying unit cost, or the last recorded
incoming cost when quantity is zero. With no recorded cost, it uses zero and
marks the sale line `stock_cost_provisional`; it does not invent a purchase price.
This means profit for an uncosted sale is provisional.

Later purchase bills retire the negative quantity's carrying value first. The
difference between actual purchase cost and the carrying cost of covered units
is recognized in the purchase-cost expense account on the receipt date. Only
the remaining units retain inventory value. Existing sale journals and locked
periods are not silently rewritten. For example, 2 units at 50 followed by a
sale of 5 leaves -3 units / -150. Buying 3 at 70 brings stock to 0 / 0 and
recognizes the 60 price difference in purchase costs.

Linked customer returns keep their original recorded cost basis. Returns that
cover a negative balance use its carrying value for the covered portion;
separate `return_cost_basis` metadata prevents partial returns from allocating
the same original cost more than once. An originally uncosted sale's return
continues to use its zero recorded basis; it is not retrospectively repriced.

Cancellation may remove the latest negative sale. Removing a movement that has
later valuation dependencies is refused; reverse the dependent documents first
or use the linked correction flow. Allowing negative quantities does not allow
zero-quantity inventory to retain unexplained value.
