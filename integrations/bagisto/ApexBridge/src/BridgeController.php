<?php

namespace ApexBooks\Bridge;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class BridgeController
{
    public function capabilities(Request $request, Bridge $bridge)
    {
        $id = $request->attributes->get('apex_connection'); $c = $bridge->configuration($id);
        return response()->json(['protocol' => 1, 'bridge_version' => '1.0.0', 'bagisto_version' => '2.5.0',
            'channel' => $c['channel'], 'currency' => $c['currency'], 'company_state_code' => $c['company_state_code'], 'inventory_source_id' => $c['inventory_source_id'],
            'product_types' => ['simple', 'configurable', 'virtual', 'downloadable'], 'reservation_required' => true,
            'operations' => Bridge::OPERATIONS, 'invoice_authority' => 'apex', 'capture_requires_verified_source' => true]);
    }
    public function command(Request $request, Bridge $bridge)
    {
        try { return $this->applyCommand($request, $bridge); }
        catch (\Illuminate\Validation\ValidationException $e) { return response()->json(['error' => 'Invalid command inputs', 'errors' => $e->errors()], 422); }
        catch (\Symfony\Component\HttpKernel\Exception\HttpException $e) { return response()->json(['error' => $e->getMessage()], $e->getStatusCode()); }
        catch (\Throwable $e) {
            $trace = (string) \Illuminate\Support\Str::uuid();
            \Illuminate\Support\Facades\Log::error('ApexBridge command failed', ['trace' => $trace, 'exception' => $e]);
            return response()->json(['error' => 'Bridge command failed', 'trace' => $trace], 500);
        }
    }
    private function applyCommand(Request $request, Bridge $bridge)
    {
        $input = $request->validate(['command_id' => 'required|string|max:160', 'channel' => 'required|string|max:160',
            'operation' => 'required|string|max:50', 'payload' => 'present|array']);
        $id = $request->attributes->get('apex_connection'); $c = $bridge->configuration($id);
        abort_unless($input['channel'] === $c['channel'], 403, 'Channel does not belong to connection');
        abort_unless(in_array($input['operation'], Bridge::OPERATIONS, true), 422, 'Unsupported operation');
        $hash = hash('sha256', $request->getContent());
        return DB::transaction(function () use ($bridge, $input, $id, $hash) {
            $bridge->lock($id);
            $old = DB::table('apex_bridge_commands')->where('connection_id', $id)->where('command_id', $input['command_id'])->first();
            if ($old) {
                abort_unless(hash_equals($old->request_hash, $hash), 409, 'Command identity reused with changed inputs');
                return response()->json(json_decode($old->result, true, 512, JSON_THROW_ON_ERROR));
            }
            $result = $bridge->execute($id, $input['operation'], $input['payload']);
            DB::table('apex_bridge_commands')->insert(['connection_id' => $id, 'command_id' => $input['command_id'],
                'operation' => $input['operation'], 'request_hash' => $hash, 'result' => json_encode($result, JSON_THROW_ON_ERROR),
                'created_at' => now(), 'updated_at' => now()]);
            return response()->json($result);
        });
    }
}
