<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
return new class extends Migration {
    public function up(): void { Schema::table('apex_bridge_locks', fn (Blueprint $t) => $t->unsignedBigInteger('projection_version')->default(0)); }
    public function down(): void { Schema::table('apex_bridge_locks', fn (Blueprint $t) => $t->dropColumn('projection_version')); }
};
