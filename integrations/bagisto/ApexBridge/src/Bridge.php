<?php

namespace ApexBooks\Bridge;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use Webkul\Core\Models\Channel;
use Webkul\Product\Models\Product;
use Webkul\Product\Repositories\ProductRepository;
use Webkul\Sales\Models\Order;
use Webkul\Sales\Repositories\InvoiceRepository;
use Webkul\Sales\Repositories\OrderRepository;
use Webkul\Sales\Repositories\RefundRepository;
use Webkul\Sales\Repositories\ShipmentRepository;

class Bridge
{
    public const OPERATIONS = ['stock.project', 'catalogue.publish', 'catalogue.scan', 'history.scan', 'reconcile.snapshot',
        'order.invoice', 'order.ship', 'order.cancel', 'order.refund', 'payment.capture', 'payment.refund', 'settlement.record', 'return.receive'];
    public array $checkoutContext = [];

    public function configuration(string $id): array
    {
        $c = config('apex-bridge.connections.'.$id);
        abort_unless(is_array($c), 401, 'Unknown integration identity');
        $channel = Channel::where('code', $c['channel'] ?? '')->first();
        abort_unless($channel, 409, 'Configured store channel does not exist');
        $sources = $channel->inventory_sources->where('status', 1)->pluck('id')->all();
        $source = (int) ($c['inventory_source_id'] ?? 0);
        abort_unless(count($sources) === 1 && (int) $sources[0] === $source, 409, 'A connected channel needs one exclusive active inventory source');
        // Shared stock sources between different company connections would leak
        // availability. Explicitly reject them, including unconnected channels.
        abort_if(DB::table('channel_inventory_sources')->where('inventory_source_id', $source)->where('channel_id', '!=', $channel->id)->exists(), 409, 'Inventory source is shared with another channel');
        foreach (config('apex-bridge.connections', []) as $otherId => $other) {
            abort_if($otherId !== $id && (($other['channel'] ?? '') === $channel->code || (int) ($other['inventory_source_id'] ?? 0) === $source), 409, 'Connection channel and inventory source must be exclusive');
        }
        abort_unless($channel->base_currency->code === 'INR', 409, 'This adapter requires INR base currency');
        abort_unless(config('app.currency') === 'INR', 409, 'Configure Bagisto APP_CURRENCY=INR before connecting accounting');
        // Apex item master rates and bridge delivery lines are GST-exclusive.
        // Refuse an incompatible shop before publishing prices or accepting orders.
        foreach (['product_prices' => 'product', 'shipping_prices' => 'shipping'] as $field => $label) {
            abort_unless(core()->getConfigData('sales.taxes.calculation.'.$field, $channel->code) === 'excluding_tax',
                409, 'Configure GST-exclusive '.$label.' prices in Bagisto tax calculation before connecting accounting');
        }
        abort_unless(preg_match('/^\d{2}$/', $c['company_state_code'] ?? ''), 409, 'Configure the company GST state code');
        return $c + ['channel_id' => $channel->id, 'currency' => 'INR'];
    }
    public function forOrder($order): ?string
    {
        foreach (config('apex-bridge.connections', []) as $id => $c) {
            if (($c['channel'] ?? '') === $order->channel->code) return $id;
        }
        return null;
    }
    public function lock(string $id): void
    {
        DB::table('apex_bridge_locks')->insertOrIgnore(['connection_id' => $id]);
        DB::table('apex_bridge_locks')->where('connection_id', $id)->lockForUpdate()->first();
    }
    public function call(string $id, string $suffix, array $payload): array
    {
        $c = $this->configuration($id); $base = rtrim($c['apex_api_url'] ?? '', '/');
        $host = parse_url($base, PHP_URL_HOST);
        $local = app()->environment('local', 'testing') && in_array($host, ['host.docker.internal', 'localhost', '127.0.0.1'], true);
        abort_unless(str_starts_with($base, 'https://') || $local, 409, 'Apex API needs HTTPS outside local tests');
        $path = '/api/integrations/bagisto/'.$id.$suffix;
        $body = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        $stamp = (string) time(); $message = $stamp."\nPOST\n".$path."\n".hash('sha256', $body);
        $response = Http::timeout(20)->withOptions(['allow_redirects' => false])->withHeaders([
            'X-Apex-Timestamp' => $stamp, 'X-Apex-Signature' => hash_hmac('sha256', $message, $c['secret']), 'Accept' => 'application/json',
        ])->withBody($body, 'application/json')->post($base.$path);
        abort_unless($response->successful(), $response->status() >= 500 ? 503 : 409, 'Apex rejected the source operation ('.$response->status().')');
        return $response->json();
    }
    public function emit(string $id, string $type, string $entity, array $payload): void
    {
        $c = $this->configuration($id);
        DB::transaction(function () use ($id, $type, $entity, $payload, $c) {
        $this->lock($id);
        $version = (int) DB::table('apex_bridge_locks')->where('connection_id', $id)->value('event_version') + 1;
        abort_if($version > 9007199254740991, 409, 'Event version capacity exceeded');
        DB::table('apex_bridge_locks')->where('connection_id', $id)->update(['event_version' => $version]);
        DB::table('apex_bridge_outbox')->insert(['event_id' => (string) Str::uuid(), 'connection_id' => $id,
            'channel' => $c['channel'], 'event_type' => $type, 'entity_id' => $entity,
            'version' => $version, 'payload' => json_encode($payload, JSON_THROW_ON_ERROR),
            'available_at' => now(), 'created_at' => now(), 'updated_at' => now()]);
        });
    }

    public function invalidateStorefront(string $id): void
    {
        $c = $this->configuration($id);
        if (!empty($c['storefront_url'])) $this->emit($id, 'storefront.invalidate', $id,
            ['connection_id' => $id, 'channel' => $c['channel'], 'resource' => 'catalogue']);
    }

    public function deliverStorefront(string $id, array $payload): array
    {
        $c = $this->configuration($id); $base = rtrim($c['storefront_url'] ?? '', '/');
        $url = parse_url($base);
        $local = app()->environment('local', 'testing') && in_array($url['host'] ?? '', ['host.docker.internal', 'localhost', '127.0.0.1'], true);
        abort_unless(!empty($url['host']) && empty($url['user']) && empty($url['pass']) && empty($url['query']) && empty($url['fragment']) && empty($url['path']) && (($url['scheme'] ?? '') === 'https' || $local), 409, 'Configure an HTTPS storefront origin');
        $path = '/api/apex/revalidate'; $stamp = (string) time();
        $body = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        $secret = hash_hmac('sha256', 'apex-storefront-invalidation:'.$id, $c['secret']);
        $message = $stamp."\nPOST\n".$path."\n".hash('sha256', $body);
        $response = Http::timeout(20)->withOptions(['allow_redirects'=>false])->withHeaders([
            'X-Apex-Timestamp'=>$stamp, 'X-Apex-Signature'=>hash_hmac('sha256',$message,$secret), 'Accept'=>'application/json',
        ])->withBody($body, 'application/json')->post($base.$path);
        abort_unless($response->successful(), $response->status() >= 500 ? 503 : 409, 'Storefront cache invalidation failed');
        return $response->json();
    }
    private function taxCategory(string $id, $input): int
    {
        $rate = (string) $input;
        abort_unless(preg_match('/^\d{1,3}(\.\d{1,4})?$/', $rate) && bccomp($rate, '100', 4) <= 0, 422, 'Invalid mapped GST rate');
        $rate = bcmul($rate, '1', 4); $code = 'APEX-'.$id.'-GST-'.$rate;
        $category = \Webkul\Tax\Models\TaxCategory::firstOrCreate(['code'=>$code],
            ['name'=>'Apex GST '.self::money($rate).'%', 'description'=>'Accounting-owned GST rate for this company channel']);
        if ($category->wasRecentlyCreated) {
            $tax = \Webkul\Tax\Models\TaxRate::firstOrCreate(['identifier'=>$code],
                ['country'=>'IN','state'=>'*','is_zip'=>false,'zip_code'=>'*','tax_rate'=>$rate]);
            $category->tax_rates()->sync([$tax->id]);
        }
        $rates = $category->tax_rates;
        abort_unless($rates->count() === 1 && $rates[0]->country === 'IN' && $rates[0]->state === '*'
            && !$rates[0]->is_zip && bccomp((string)$rates[0]->tax_rate, $rate, 4) === 0,
            409, 'The managed GST category was changed in the store; review its rate and jurisdiction');
        return (int) $category->id;
    }
    public static function money($value): string { return number_format((float) $value, 2, '.', ''); }
    public function customerId($order): string
    {
        if(!$order->customer_id)return 'guest:'.$order->id;
        $gstin=strtoupper(trim((string)($order->billing_address->vat_id??'')));
        // One shop account may buy for different registered businesses.
        return 'customer:'.$order->customer_id.($gstin!==''?':gst:'.$gstin:'');
    }
    public function orderPayload(string $id, $order): array
    {
        $checkout = DB::table('apex_bridge_checkouts')->where('connection_id', $id)->where('order_id', $order->id)->first();
        return ['number' => $order->increment_id, 'status' => $order->status, 'amount' => self::money($order->base_grand_total),
            'currency' => $order->base_currency_code, 'customer_id' => $this->customerId($order),
            'reservation_id' => $checkout?->reservation_id ?? ($this->checkoutContext[$id]['reservation_id'] ?? null),
            'items' => $order->items->whereNull('parent_id')->map(fn ($line) => ['id' => (string) $line->id, 'product_id' => (string) $line->product_id,
                'name' => $line->name, 'sku' => $line->sku, 'quantity' => (string) $line->qty_ordered, 'invoiced' => (string) $line->qty_invoiced,
                'shipped' => (string) $line->qty_shipped, 'refunded' => (string) $line->qty_refunded, 'cancelled' => (string) $line->qty_canceled])->values()->all(),
            'shipments' => $order->shipments->map(fn ($s) => ['id' => (string) $s->id, 'carrier' => $s->carrier_title, 'tracking' => $s->track_number])->all()];
    }
    public function orderChanged($order, string $type = 'order.upsert'): void
    {
        $id = $this->forOrder($order); if (!$id) return;
        $c = $this->configuration($id); $address = $order->billing_address;
        $person = trim(($order->customer_first_name ?: ($address?->first_name ?? '')).' '.($order->customer_last_name ?: ($address?->last_name ?? '')));
        $buyerName = trim($address?->company_name ?? '') ?: $person;
        $this->emit($id, 'customer.upsert', $this->customerId($order), [
            'name' => $buyerName, 'email' => $order->customer_email ?: ($address?->email ?? ''),
            'phone' => $address?->phone ?? '', 'address' => $address ? implode(', ', array_filter([$address->address, $address->city, $address->state, $address->postcode])) : '',
            'gstin' => strtoupper(trim($address?->vat_id ?? '')), 'currency' => $c['currency'], 'source_order_id' => (string) $order->id,
        ]);
        $this->emit($id, $type, (string) $order->id, $this->orderPayload($id, $order));
    }
    public function taxState(string $id, $order, ?string $issued = null): string
    {
        $c = $this->configuration($id); $address = $order->shipping_address ?? $order->billing_address;
        abort_unless($address && $address->country === 'IN', 422, 'International orders require a reviewed export adapter');
        $gstin=strtoupper(trim((string)($order->billing_address->vat_id ?? '')));
        if($gstin!==''){
            abort_unless(IndiaGstin::valid($gstin),422,'Review the customer GSTIN before posting this invoice');
            $billing=$order->billing_address;
            abort_unless($billing->country==='IN' && IndiaGstState::resolve((string)$billing->state,$c['state_codes']??[], $issued)===substr($gstin,0,2),422,'Review the GSTIN and billing state before posting this invoice');
            return substr($gstin,0,2);
        }
        $state = IndiaGstState::resolve((string)$address->state, $c['state_codes'] ?? [], $issued);
        abort_unless(is_string($state) && preg_match('/^\d{2}$/', $state), 422, 'Map the delivery state to an Indian GST state code');
        return $state;
    }
    public function financialPayload(string $id, $document): array
    {
        $order = $document->order; $c = $this->configuration($id); $state = $this->taxState($id, $order, $document->created_at->timezone('Asia/Kolkata')->format('Y-m-d')); $lines = [];
        foreach ($document->items->whereNull('parent_id') as $item) {
            $source = $item->order_item; $productId = $source->product_id;
            if ($source->type === 'configurable') {
                abort_unless($source->children->count() === 1, 422, 'Variant must resolve to one stock SKU');
                $productId = $source->children->first()->product_id;
            } else abort_unless(in_array($source->type, ['simple', 'virtual', 'downloadable'], true), 422, 'Unsupported product type needs reviewed mapping');
            $lines[] = ['product_id' => (string) $productId, 'quantity' => (string) $item->qty, 'rate' => self::money($item->base_price),
                'gst_rate' => self::money($source->tax_percent), 'discount_amount' => self::money($item->base_discount_amount), 'price_includes_tax' => false];
        }
        $tax = (float) $document->base_tax_amount; $local = $state === $c['company_state_code'];
        $central = $local ? round($tax / 2, 2, PHP_ROUND_HALF_UP) : 0;
        $payload = ['order_id' => (string) $order->id, 'date' => $document->created_at->timezone('Asia/Kolkata')->format('Y-m-d'),
            'party_gstin'=>strtoupper(trim((string)($order->billing_address->vat_id??''))),
            'billing_address'=>$order->billing_address?implode(', ',array_filter([$order->billing_address->address,$order->billing_address->city,$order->billing_address->state,$order->billing_address->postcode])):'',
            'currency' => $document->base_currency_code, 'amount' => self::money($document->base_grand_total), 'place_of_supply' => $state,
            'lines' => $lines, 'taxes' => ['cgst' => self::money($central), 'sgst' => self::money($local ? $tax - $central : 0), 'igst' => self::money($local ? 0 : $tax)],
            'shipping_amount' => self::money($document->base_shipping_amount), 'shipping_line' => $c['shipping_line'] ?? null];
        return $payload;
    }
    public function invoiceCreated($invoice): void
    {
        $id = $this->forOrder($invoice->order); if (!$id) return;
        try { $payload = $this->financialPayload($id, $invoice); }
        catch (\Symfony\Component\HttpKernel\Exception\HttpException $e) { $payload = ['_review' => $e->getMessage(), 'order_id' => (string) $invoice->order_id]; }
        $this->emit($id, 'invoice.created', (string) $invoice->id, $payload);
    }
    public function refundCreated($refund): void
    {
        $id = $this->forOrder($refund->order); if (!$id) return;
        try {
            // A single-source invoice is unambiguous. Multi-invoice refunds need
            // an explicit allocation; never guess a legal invoice reference.
            $invoices = $refund->order->invoices;
            abort_unless($invoices->count() === 1, 422, 'Allocate this refund to its source invoices before posting');
            abort_unless((float) $refund->adjustment_refund === 0.0 && (float) $refund->adjustment_fee === 0.0, 422, 'Refund adjustments require reviewed accounting');
            $payload = $this->financialPayload($id, $refund) + ['invoice_id' => (string) $invoices->first()->id, 'return_received' => false];
        } catch (\Symfony\Component\HttpKernel\Exception\HttpException $e) { $payload = ['_review' => $e->getMessage(), 'order_id' => (string) $refund->order_id]; }
        $this->emit($id, 'refund.created', (string) $refund->id, $payload);
    }
    public function financialSource(string $id, string $kind, string $source, array $payload): array
    {
        return DB::transaction(function () use ($id, $kind, $source, $payload) {
            $this->lock($id); return $this->saveFinancialSource($id, $kind, $source, $payload);
        });
    }
    private function saveFinancialSource(string $id, string $kind, string $source, array $payload): array
    {
        $this->configuration($id); abort_unless(strlen($source) > 0 && strlen($source) <= 160, 422, 'Source identity required');
        if (isset($payload['order_id'])) $this->ownedOrder($id, $payload['order_id']);
        $hash = hash('sha256', json_encode($payload, JSON_THROW_ON_ERROR));
        $old = DB::table('apex_bridge_financial_sources')->where('connection_id', $id)->where('kind', $kind)->where('source_id', $source)->first();
        if ($old) { abort_unless(hash_equals($old->request_hash, $hash), 409, 'Financial source identity changed'); return ['duplicate_source' => true]; }
        DB::table('apex_bridge_financial_sources')->insert(['connection_id' => $id, 'kind' => $kind, 'source_id' => $source,
            'request_hash' => $hash, 'payload' => json_encode($payload, JSON_THROW_ON_ERROR), 'created_at' => now(), 'updated_at' => now()]);
        $this->emit($id, $kind, $source, $payload); return ['source_id' => $source, 'queued' => true];
    }
    public function ownedOrder(string $id, $orderId)
    {
        $c = $this->configuration($id);
        $order = Order::where('id', $orderId)->where('channel_id', $c['channel_id'])->first();
        abort_unless($order, 404, 'Order does not belong to this channel'); return $order;
    }
    public function execute(string $id, string $operation, array $payload): array
    {
        $c = $this->configuration($id);
        if ($operation === 'stock.project' || $operation === 'catalogue.publish') {
            $version = (int) ($payload['projection_version'] ?? 0);
            $currentVersion = (int) DB::table('apex_bridge_locks')->where('connection_id', $id)->value('projection_version');
            abort_unless($version > 0, 422, 'Stock projection requires a positive source version');
            if ($version < $currentVersion) return ['status' => 'done', 'ignored' => 'stale_projection'];
            $products = $payload['products'] ?? $payload['stock'] ?? []; $mapped = [];
            foreach ($products as $input) {
                $product = Product::where('id', $input['external_id'] ?? '')->whereHas('channels', fn ($q) => $q->where('channels.id', $c['channel_id']))->first();
                abort_unless($product, 422, 'Map the product in this store channel before publication');
                abort_unless(in_array($product->type, ['simple', 'virtual', 'downloadable'], true), 422, 'Publish variants through their concrete stock SKU');
                abort_unless((string) $product->sku === (string) $input['sku'], 409, 'Mapped product SKU differs');
                abort_unless((bool) $product->manage_stock === (bool) ($input['track_stock'] ?? false), 409, 'Product stock tracking differs between the two systems');
                $available = (float) ($input['available_quantity'] ?? 0);
                abort_unless(is_finite($available) && $available >= 0 && floor($available) === $available, 422, 'Bagisto requires whole-unit sellable stock');
                $ordered = (float) DB::table('product_ordered_inventories')->where('product_id', $product->id)->where('channel_id', $c['channel_id'])->value('qty');
                DB::table('product_inventories')->updateOrInsert(['product_id' => $product->id, 'inventory_source_id' => $c['inventory_source_id'], 'vendor_id' => 0], ['qty' => $available + $ordered]);
                if ($operation === 'catalogue.publish') {
                    // Keep website copy, slugs, category assignments and media.
                    abort_if($product->channels->count() > 1, 409, 'Use a dedicated product per company channel before publishing global price or GST attributes');
                    $updated = app(ProductRepository::class)->update(['channel' => $c['channel'], 'locale' => core()->getDefaultLocaleCodeFromDefaultChannel(),
                        'price' => $input['sale_rate'], 'tax_category_id' => $this->taxCategory($id, $input['gst_rate'] ?? '0')], $product->id, ['price', 'tax_category_id']);
                    \Illuminate\Support\Facades\Event::dispatch('catalog.product.update.after', $updated);
                }
                $mapped[] = ['external_id' => (string) $product->id, 'sku' => $product->sku];
            }
            DB::table('apex_bridge_locks')->where('connection_id', $id)->update(['projection_version' => $version]);
            $this->invalidateStorefront($id);
            return ['status' => 'done', 'products' => $mapped];
        }
        if ($operation === 'catalogue.scan') {
            $after = max(0, (int) ($payload['after_id'] ?? 0));
            $rows = Product::whereHas('channels', fn ($q) => $q->where('channels.id', $c['channel_id']))->where('id', '>', $after)->orderBy('id')->limit(101)->get();
            return ['status' => 'done', 'products' => $rows->take(100)->map(fn ($p) => ['external_id' => (string) $p->id, 'sku' => $p->sku, 'name' => $p->name, 'type' => $p->type])->values()->all(),
                'next_after_id' => $rows->count() > 100 ? $rows[99]->id : null];
        }
        if ($operation === 'reconcile.snapshot') {
            $stock = [];
            foreach (Product::whereHas('channels', fn ($q) => $q->where('channels.id', $c['channel_id']))->get() as $p) {
                $raw = (float) $p->inventories()->where('inventory_source_id', $c['inventory_source_id'])->sum('qty');
                $ordered = (float) $p->ordered_inventories()->where('channel_id', $c['channel_id'])->sum('qty');
                $stock[] = ['external_id' => (string) $p->id, 'available_quantity' => number_format(max(0, $raw - $ordered), 3, '.', '')];
            }
            $orders = Order::where('channel_id', $c['channel_id'])->get();
            $totals = ['captured_total' => '0.00', 'refunded_total' => '0.00', 'settled_gross_total' => '0.00', 'settled_net_total' => '0.00', 'fee_total' => '0.00'];
            foreach (DB::table('apex_bridge_financial_sources')->where('connection_id', $id)->cursor() as $row) {
                $source = json_decode($row->payload, true, 512, JSON_THROW_ON_ERROR);
                if ($row->kind === 'payment.captured') $totals['captured_total'] = bcadd($totals['captured_total'], (string) $source['amount'], 2);
                if ($row->kind === 'payment.refunded') $totals['refunded_total'] = bcadd($totals['refunded_total'], (string) $source['amount'], 2);
                if ($row->kind === 'settlement.created') foreach (['settled_gross_total' => 'gross', 'settled_net_total' => 'net', 'fee_total' => 'fee'] as $dest => $key) $totals[$dest] = bcadd($totals[$dest], (string) $source[$key], 2);
            }
            return ['status' => 'done', 'stock' => $stock, 'summary' => ['order_count' => $orders->count(),
                'invoice_total' => self::money($orders->sum('base_grand_total_invoiced')), 'credit_total' => self::money($orders->sum('base_grand_total_refunded'))] + $totals];
        }
        if ($operation === 'history.scan') {
            $rows = Order::where('channel_id', $c['channel_id'])->where('id', '>', max(0, (int) ($payload['after_id'] ?? 0)))->orderBy('id')->limit(51)->get();
            foreach ($rows->take(50) as $order) { $this->orderChanged($order); foreach ($order->invoices as $invoice) $this->invoiceCreated($invoice); foreach ($order->refunds as $refund) $this->refundCreated($refund); }
            return ['status' => 'done', 'scanned' => min(50, $rows->count()), 'next_after_id' => $rows->count() > 50 ? $rows[49]->id : null];
        }
        if (in_array($operation, ['payment.capture', 'payment.refund', 'settlement.record', 'return.receive'], true)) {
            abort_unless(($payload['confirmed'] ?? false) === true && !empty($payload['source_id']), 422, 'Confirm the bank/provider source reference');
            return ['status' => 'done'] + $this->financialSource($id, ['payment.capture' => 'payment.captured', 'payment.refund' => 'payment.refunded', 'settlement.record' => 'settlement.created', 'return.receive' => 'return.received'][$operation], $payload['source_id'], $payload['data'] ?? []);
        }
        $order = $this->ownedOrder($id, $payload['order_id'] ?? '');
        if ($operation === 'order.cancel') {
            abort_unless(app(OrderRepository::class)->cancel($order, false), 409, 'Order can no longer be cancelled');
            return ['status' => 'done', 'order_id' => (string) $order->id];
        }
        $items = $payload['items'] ?? [];
        abort_unless(is_array($items) && count($items) > 0, 422, 'Choose order item quantities');
        foreach ($items as $itemId => $quantity) {
            $line = $order->items->firstWhere('id', $itemId);
            abort_unless($line && $line->parent_id === null && is_numeric($quantity) && (float) $quantity > 0 && floor((float) $quantity) === (float) $quantity, 422, 'Invalid order item quantity');
            $limit = $operation === 'order.invoice' ? $line->qty_to_invoice : ($operation === 'order.ship' ? $line->qty_to_ship : $line->qty_to_refund);
            abort_if((float) $quantity > (float) $limit, 409, 'Quantity exceeds remaining order quantity');
        }
        if ($operation === 'order.invoice') {
            abort_unless($order->canInvoice(), 409, 'Order cannot be invoiced');
            $doc = app(InvoiceRepository::class)->create(['order_id' => $order->id, 'invoice' => ['items' => $items]]);
        } elseif ($operation === 'order.ship') {
            abort_unless($order->canShip(), 409, 'Order cannot be shipped');
            $shipmentItems = []; foreach ($items as $key => $quantity) $shipmentItems[$key] = [$c['inventory_source_id'] => $quantity];
            $doc = app(ShipmentRepository::class)->create(['order_id' => $order->id, 'shipment' => ['items' => $shipmentItems,
                'source' => $c['inventory_source_id'], 'carrier_title' => mb_substr($payload['carrier'] ?? '', 0, 120), 'track_number' => mb_substr($payload['tracking'] ?? '', 0, 120)]]);
        } else {
            abort_unless($order->canRefund(), 409, 'Order cannot be refunded');
            $doc = app(RefundRepository::class)->create(['order_id' => $order->id, 'refund' => ['items' => $items, 'shipping' => $payload['shipping'] ?? 0, 'adjustment_refund' => 0, 'adjustment_fee' => 0]]);
        }
        return ['status' => 'done', 'document_id' => (string) $doc->id, 'order_id' => (string) $order->id];
    }
}
