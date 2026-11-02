<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('apex_bridge_locks', function (Blueprint $t) {
            $t->string('connection_id', 36)->primary();
        });
        Schema::create('apex_bridge_outbox', function (Blueprint $t) {
            $t->bigIncrements('id');
            $t->uuid('event_id')->unique();
            $t->string('connection_id', 36);
            $t->string('channel');
            $t->string('event_type', 50);
            $t->string('entity_id', 160);
            $t->unsignedBigInteger('version');
            $t->json('payload');
            $t->string('status', 20)->default('pending');
            $t->unsignedInteger('attempts')->default(0);
            $t->timestamp('available_at');
            $t->timestamp('lease_until')->nullable();
            $t->string('error', 500)->default('');
            $t->json('result')->nullable();
            $t->timestamps();
            $t->index(['status', 'available_at']);
            $t->index(['connection_id', 'id']);
        });
        Schema::create('apex_bridge_commands', function (Blueprint $t) {
            $t->id(); $t->string('connection_id', 36); $t->string('command_id', 160);
            $t->string('request_hash', 64); $t->string('operation', 50); $t->json('result');
            $t->timestamps(); $t->unique(['connection_id', 'command_id']);
        });
        Schema::create('apex_bridge_checkouts', function (Blueprint $t) {
            $t->uuid('id')->primary(); $t->string('connection_id', 36); $t->string('cart_key', 160);
            $t->string('request_hash', 64); $t->uuid('reservation_id')->nullable();
            $t->unsignedBigInteger('order_id')->nullable(); $t->string('status', 20)->default('pending');
            $t->json('lines'); $t->timestamps(); $t->unique(['connection_id', 'cart_key']);
        });
        Schema::create('apex_bridge_financial_sources', function (Blueprint $t) {
            $t->id(); $t->string('connection_id', 36); $t->string('kind', 30);
            $t->string('source_id', 160); $t->string('request_hash', 64); $t->json('payload');
            $t->timestamps(); $t->unique(['connection_id', 'kind', 'source_id']);
        });
    }
    public function down(): void
    {
        foreach (['financial_sources', 'checkouts', 'commands', 'outbox', 'locks'] as $name) Schema::dropIfExists('apex_bridge_'.$name);
    }
};
