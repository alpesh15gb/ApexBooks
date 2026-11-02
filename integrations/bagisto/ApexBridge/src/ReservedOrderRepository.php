<?php

namespace ApexBooks\Bridge;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Webkul\Core\Models\Channel;
use Webkul\Sales\Models\Order;
use Webkul\Sales\Repositories\OrderRepository;

class ReservedOrderRepository extends OrderRepository
{
    public function cancel($orderOrId, bool $force = false)
    {
        return DB::transaction(fn () => parent::cancel($orderOrId, $force));
    }
    public function createOrderIfNotThenRetry(array $data, int $attempt = 1, ?int $maxAttempts = null)
    {
        $channel = Channel::find($data['channel_id'] ?? null); $connection = null;
        foreach (config('apex-bridge.connections', []) as $id => $c) if ($channel && $c['channel'] === $channel->code) $connection = $id;
        if (!$connection) return parent::createOrderIfNotThenRetry($data, $attempt, $maxAttempts);
        $bridge = app(Bridge::class); $c = $bridge->configuration($connection);
        abort_unless(($data['base_currency_code'] ?? '') === 'INR' && ($data['order_currency_code'] ?? '') === 'INR', 422, 'Connected orders require INR');
        abort_unless(!empty($data['cart_id']), 422, 'A stable checkout cart identity is required');
        $cartKey = 'cart:'.$data['cart_id']; $lines = [];
        foreach ($data['items'] ?? [] as $line) {
            abort_unless(in_array($line['type'] ?? '', ['simple', 'configurable', 'virtual', 'downloadable'], true), 422, 'This product type is not supported by the accounting connector');
            $productId = $line['product_id'];
            if ($line['type'] === 'configurable') {
                abort_unless(count($line['children'] ?? []) === 1, 422, 'Variant must resolve to one concrete SKU');
                $productId = $line['children'][0]['product_id'];
            }
            $qty = (float) ($line['qty_ordered'] ?? 0);
            abort_unless($qty > 0 && is_finite($qty) && floor($qty) === $qty, 422, 'Store checkout requires whole-unit quantities');
            $lines[] = ['external_product_id' => (string) $productId, 'quantity' => (string) $qty];
        }
        abort_unless(count($lines) > 0, 422, 'Order has no mapped sale items');
        $hash = hash('sha256', json_encode($lines, JSON_THROW_ON_ERROR));
        // This short transaction is committed before network I/O. A retry after
        // a lost HTTP response reuses the same reservation reference.
        $checkout = DB::transaction(function () use ($bridge, $connection, $cartKey, $hash, $lines) {
            $bridge->lock($connection);
            $old = DB::table('apex_bridge_checkouts')->where('connection_id', $connection)->where('cart_key', $cartKey)->first();
            if ($old && $old->order_id) return $old;
            if ($old && !in_array($old->status, ['released', 'expired'], true)) {
                abort_unless(hash_equals($old->request_hash, $hash), 409, 'Release the previous checkout reservation before changing its items'); return $old;
            }
            if ($old) DB::table('apex_bridge_checkouts')->where('id', $old->id)->delete();
            $id = (string) Str::uuid();
            DB::table('apex_bridge_checkouts')->insert(['id' => $id, 'connection_id' => $connection, 'cart_key' => $cartKey,
                'request_hash' => $hash, 'lines' => json_encode($lines, JSON_THROW_ON_ERROR), 'created_at' => now(), 'updated_at' => now()]);
            return DB::table('apex_bridge_checkouts')->where('id', $id)->first();
        });
        if ($checkout->order_id) return Order::findOrFail($checkout->order_id);
        $hold = $bridge->call($connection, '/reservations', ['reference' => $checkout->id, 'channel' => $c['channel'], 'lines' => $lines, 'expires_seconds' => 900]);
        DB::table('apex_bridge_checkouts')->where('id', $checkout->id)->update(['reservation_id' => $hold['id'], 'status' => 'held', 'updated_at' => now()]);
        $bridge->checkoutContext[$connection] = ['reservation_id' => $hold['id']];
        try {
            return DB::transaction(function () use ($bridge, $connection, $checkout, $hold, $lines, $c, $data) {
                $bridge->lock($connection);
                $row = DB::table('apex_bridge_checkouts')->where('id', $checkout->id)->lockForUpdate()->first();
                if ($row->order_id) return Order::findOrFail($row->order_id);
                // Credit this checkout's own central hold while Bagisto creates
                // its local ordered inventory. Other checkouts remain deducted.
                foreach ($lines as $line) {
                    $own = (float) $line['quantity']; $product = \Webkul\Product\Models\Product::findOrFail($line['external_product_id']);
                    if (!$product->manage_stock) continue;
                    $inventory = $product->inventories()->where('inventory_source_id', $c['inventory_source_id'])->lockForUpdate()->first();
                    abort_unless($inventory, 409, 'Product inventory source is not configured');
                    $ordered = (float) $product->ordered_inventories()->where('channel_id', $c['channel_id'])->value('qty');
                    // Central availability is authoritative. Preserve the
                    // snapshot returned by this reservation, including own hold.
                    $available = (float) ($hold['availability'][$line['external_product_id']] ?? 0);
                    $inventory->update(['qty' => $available + $ordered + $own]);
                }
                $order = parent::createOrderIfNotThenRetry($data, 1, 1);
                $bridge->call($connection, '/reservations/'.$hold['id'], ['action' => 'confirm', 'order_id' => (string) $order->id]);
                DB::table('apex_bridge_checkouts')->where('id', $checkout->id)->update(['order_id' => $order->id, 'status' => 'confirmed', 'updated_at' => now()]);
                return $order;
            });
        } catch (\Throwable $e) {
            try {
                $bridge->call($connection, '/reservations/'.$hold['id'], ['action' => 'release']);
                DB::table('apex_bridge_checkouts')->where('id', $checkout->id)->update(['status' => 'released', 'updated_at' => now()]);
            } catch (\Throwable) { /* A durable checkout row remains for repair. */ }
            throw $e;
        } finally { unset($bridge->checkoutContext[$connection]); }
    }
}
