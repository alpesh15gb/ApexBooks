<?php
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
return new class extends Migration {
    public function up(): void {
        Schema::table('apex_bridge_locks', fn (Blueprint $t) => $t->unsignedBigInteger('event_version')->default(0));
        foreach (DB::table('apex_bridge_outbox')->select('connection_id')->distinct()->get() as $row) {
            DB::table('apex_bridge_locks')->insertOrIgnore(['connection_id'=>$row->connection_id]);
            DB::table('apex_bridge_locks')->where('connection_id',$row->connection_id)->update(['event_version'=>DB::table('apex_bridge_outbox')->where('connection_id',$row->connection_id)->max('version') ?? 0]);
        }
    }
    public function down(): void { Schema::table('apex_bridge_locks', fn (Blueprint $t) => $t->dropColumn('event_version')); }
};
