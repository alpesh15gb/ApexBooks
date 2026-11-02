<?php

// Portable replacement for bagisto/bagisto-api 2.4.4's MySQL-only corrective
// migration. The upstream package is MIT licensed; see THIRD_PARTY_NOTICES.md.
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    private array $columns = ['admin_id' => false, 'revoked_by_admin_id' => true, 'regenerated_by_admin_id' => true, 'created_by_admin_id' => true];
    public function up(): void
    {
        if (!Schema::hasTable('admin_personal_access_tokens')) return;
        foreach ($this->columns as $column => $nullable) {
            $orphans = DB::table('admin_personal_access_tokens')->whereNotNull($column)->whereNotIn($column, DB::table('admins')->select('id'))->exists();
            if ($orphans) throw new RuntimeException('Admin integration token references need explicit repair before API migration; no credentials were deleted.');
            if (DB::getDriverName() === 'mysql') {
                $type = strtolower(Schema::getColumnType('admin_personal_access_tokens', $column, true));
                if ($type !== 'int unsigned') Schema::table('admin_personal_access_tokens', fn (Blueprint $t) => $t->unsignedInteger($column)->nullable($nullable)->change());
            }
        }
        $names = array_column(Schema::getForeignKeys('admin_personal_access_tokens'), 'name');
        Schema::table('admin_personal_access_tokens', function (Blueprint $t) use ($names) {
            foreach ($this->columns as $column => $nullable) {
                $name = 'admin_personal_access_tokens_'.$column.'_foreign';
                if (in_array($name, $names, true)) continue;
                $key = $t->foreign($column, $name)->references('id')->on('admins');
                if ($nullable) $key->nullOnDelete(); else $key->cascadeOnDelete();
            }
            $name = 'admin_personal_access_tokens_regenerated_to_id_foreign';
            if (!in_array($name, $names, true)) $t->foreign('regenerated_to_id', $name)->references('id')->on('admin_personal_access_tokens')->nullOnDelete();
        });
    }
    public function down(): void
    {
        // Existing valid FKs are preserved. The table-creation migration owns
        // table teardown; reverting this portability fix must not weaken access.
    }
};
