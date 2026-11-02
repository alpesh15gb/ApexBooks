<?php

// Server-only configuration. One independent secret, channel and inventory pool
// per Apex company. Never put this JSON in storefront assets or mobile clients.
return ['connections' => json_decode(env('APEX_BRIDGE_CONNECTIONS', '{}'), true, 512, JSON_THROW_ON_ERROR)];
