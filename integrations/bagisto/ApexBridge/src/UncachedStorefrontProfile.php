<?php
namespace ApexBooks\Bridge;
use Illuminate\Http\Request;
use Spatie\ResponseCache\CacheProfiles\CacheAllSuccessfulGetRequests;
use Symfony\Component\HttpFoundation\Response;

// The 2.4 API profile inherits a core profile with an older response-cache
// interface. On 2.5, disable that full-response layer; Next caches only public
// catalogue data, while carts, customer pages and API responses stay private.
class UncachedStorefrontProfile extends CacheAllSuccessfulGetRequests
{
    public function enabled(Request $request): bool { return false; }
    public function shouldCacheRequest(Request $request): bool { return false; }
    public function shouldCacheResponse(Response $response): bool { return false; }
}
