<?php

namespace ApexBooks\Bridge;

use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\ServiceProvider;
use Webkul\Sales\Repositories\OrderRepository;

class BridgeServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        $this->mergeConfigFrom(__DIR__.'/../config/apex-bridge.php', 'apex-bridge');
        $this->app->singleton(Bridge::class);
        $this->app->bind(OrderRepository::class, ReservedOrderRepository::class);
        if (class_exists(\Webkul\BagistoApi\State\ProductGraphQLProvider::class)) {
            $this->app->extend(\ApiPlatform\Metadata\Resource\Factory\ResourceMetadataCollectionFactoryInterface::class,
                fn ($factory) => new Compatibility\GstCheckoutMetadata($factory));
            $this->app->extend(\Webkul\BagistoApi\State\CheckoutProcessor::class,
                fn ($processor,$app) => new Compatibility\GstCheckoutProcessor($app->make(\Webkul\Customer\Repositories\CustomerRepository::class),$app->make(\Webkul\Sales\Repositories\OrderRepository::class),$app->make(\Webkul\Checkout\Repositories\CartRepository::class)));
            if (config('database.connections.'.config('database.default').'.driver') === 'pgsql') {
                $this->app->extend(\ApiPlatform\Metadata\Resource\Factory\ResourceMetadataCollectionFactoryInterface::class,
                    fn ($factory) => new Compatibility\PostgresProductMetadata($factory));
            }
            // Register before API Platform materializes its tagged provider
            // locator; rebinding at boot time leaves that locator unchanged.
            $this->app->extend(\Webkul\BagistoApi\State\ProductGraphQLProvider::class, function ($provider, $app) {
                return config('database.connections.'.config('database.default').'.driver') === 'pgsql'
                    ? new Compatibility\PostgresProductProvider($app->make(\ApiPlatform\State\Pagination\Pagination::class)) : $provider;
            });
        }
    }
    public function boot(): void
    {
        $this->loadMigrationsFrom(__DIR__.'/../database/migrations');
        $this->app->booted(function () {
            if (class_exists(\Webkul\BagistoApi\Providers\BagistoApiServiceProvider::class)) {
                $this->loadMigrationsFrom(__DIR__.'/../database/compat-migrations');
                config(['responsecache.cache_profile' => UncachedStorefrontProfile::class]);
            }
        });
        Route::middleware(SignedConnection::class)->prefix('apex-bridge/v1')->group(function () {
            Route::get('capabilities', [BridgeController::class, 'capabilities']);
            Route::post('commands', [BridgeController::class, 'command']);
        });
        Event::listen('checkout.order.save.after', fn ($order) => app(Bridge::class)->orderChanged($order));
        // The pinned headless API omits legacy currency fields when it creates
        // carts. Initialize only missing fields, for connected channels only.
        Event::listen('eloquent.creating: *', function ($event, $models) {
            $cart = $models[0] ?? null;
            if (!$cart instanceof \Webkul\Checkout\Models\Cart) return;
            $channel = \Webkul\Core\Models\Channel::find($cart->channel_id);
            foreach (config('apex-bridge.connections', []) as $id => $configuration) {
                if (!$channel || ($configuration['channel'] ?? '') !== $channel->code) continue;
                app(Bridge::class)->configuration($id);
                $cart->base_currency_code ??= core()->getBaseCurrencyCode();
                $cart->global_currency_code ??= $cart->base_currency_code;
                $cart->channel_currency_code ??= $channel->base_currency->code;
                $cart->cart_currency_code ??= $cart->channel_currency_code;
            }
        });
        Event::listen('sales.order.cancel.after', fn ($order) => app(Bridge::class)->orderChanged($order, 'order.cancelled'));
        Event::listen('sales.order.update-status.after', fn ($order) => app(Bridge::class)->orderChanged($order));
        Event::listen('sales.shipment.save.after', fn ($shipment) => app(Bridge::class)->orderChanged($shipment->order, 'shipment.updated'));
        Event::listen('sales.invoice.save.after', fn ($invoice) => app(Bridge::class)->invoiceCreated($invoice));
        Event::listen('sales.refund.save.after', fn ($refund) => app(Bridge::class)->refundCreated($refund));
        // Payment plugins must explicitly dispatch verified capture/refund source
        // events. A Bagisto invoice's default "paid" state is NOT payment evidence.
        Event::listen('apex.payment.captured', fn ($source) => app(Bridge::class)->financialSource($source['connection_id'], 'payment.captured', $source['source_id'], $source['payload']));
        Event::listen('apex.payment.refunded', fn ($source) => app(Bridge::class)->financialSource($source['connection_id'], 'payment.refunded', $source['source_id'], $source['payload']));
        if ($this->app->runningInConsole()) $this->commands([DeliverEvents::class]);
    }
}
