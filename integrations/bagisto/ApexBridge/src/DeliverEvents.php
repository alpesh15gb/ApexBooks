<?php

namespace ApexBooks\Bridge;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class DeliverEvents extends Command
{
    protected $signature = 'apex:deliver {--once} {--limit=100}';
    protected $description = 'Deliver durable company-scoped events and repair abandoned checkouts';
    public function handle(Bridge $bridge): int
    {
        do {
            $processed = 0;
            for ($i = 0; $i < min(1000, max(1, (int) $this->option('limit'))); $i++) {
                $row = DB::transaction(function () {
                    $row = DB::table('apex_bridge_outbox')->where(function ($q) {
                        $q->whereIn('status', ['pending', 'retry'])->where('available_at', '<=', now());
                    })->orWhere(function ($q) { $q->where('status', 'processing')->where('lease_until', '<', now()); })
                        ->orderBy('id')->lock('for update skip locked')->first();
                    if (!$row) return null;
                    $lease = now()->addSeconds(120);
                    DB::table('apex_bridge_outbox')->where('id', $row->id)->update(['status' => 'processing', 'attempts' => $row->attempts + 1, 'lease_until' => $lease]);
                    $row->lease_until = $lease->format('Y-m-d H:i:s'); return $row;
                });
                if (!$row) break;
                $processed++;
                try {
                    $result = $row->event_type === 'storefront.invalidate'
                        ? $bridge->deliverStorefront($row->connection_id, json_decode($row->payload, true, 512, JSON_THROW_ON_ERROR))
                        : $bridge->call($row->connection_id, '/events', ['event_id' => $row->event_id, 'channel' => $row->channel,
                        'event_type' => $row->event_type, 'entity_id' => $row->entity_id, 'version' => $row->version,
                        'payload' => json_decode($row->payload, true, 512, JSON_THROW_ON_ERROR)]);
                    $values = ['status' => 'done', 'result' => json_encode($result, JSON_THROW_ON_ERROR), 'error' => '', 'lease_until' => null];
                } catch (\Throwable $e) {
                    $status = method_exists($e, 'getStatusCode') ? $e->getStatusCode() : 503;
                    $values = ['status' => $status >= 500 && $row->attempts < 11 ? 'retry' : 'review',
                        'available_at' => now()->addSeconds(min(1800, 2 ** min(11, $row->attempts + 1))), 'lease_until' => null,
                        'error' => 'Delivery failed ('.$status.'); review channel, signature, availability and payload.'];
                }
                DB::table('apex_bridge_outbox')->where('id', $row->id)->where('status', 'processing')->where('lease_until', $row->lease_until)->update($values + ['updated_at' => now()]);
            }
            $this->repairCheckouts($bridge);
            if (!$this->option('once') && $processed === 0) sleep(2);
        } while (!$this->option('once'));
        return self::SUCCESS;
    }
    private function repairCheckouts(Bridge $bridge): void
    {
        foreach (DB::table('apex_bridge_checkouts')->whereNull('order_id')->whereIn('status', ['pending', 'held'])->where('updated_at', '<', now()->subMinutes(20))->limit(100)->get() as $row) {
            // No accepted store order can be released by the orphan repair job.
            $cartId = str_starts_with($row->cart_key, 'cart:') ? substr($row->cart_key, 5) : null;
            if ($cartId && \Webkul\Sales\Models\Order::where('cart_id', $cartId)->exists()) continue;
            try {
                if ($row->reservation_id) $bridge->call($row->connection_id, '/reservations/'.$row->reservation_id, ['action' => 'release']);
                DB::table('apex_bridge_checkouts')->where('id', $row->id)->whereNull('order_id')->update(['status' => 'expired', 'updated_at' => now()]);
            } catch (\Throwable) { /* Retry on the next durable worker pass. */ }
        }
    }
}
