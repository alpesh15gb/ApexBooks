<?php

namespace ApexBooks\Bridge;

use Closure;
use Illuminate\Http\Request;

class SignedConnection
{
    public function handle(Request $request, Closure $next)
    {
        $id = (string) $request->header('X-Apex-Connection', '');
        $config = config('apex-bridge.connections.'.$id);
        abort_unless(is_array($config) && strlen($config['secret'] ?? '') >= 32, 401, 'Unknown integration identity');
        $stamp = (string) $request->header('X-Apex-Timestamp', '');
        abort_unless(ctype_digit($stamp) && abs(time() - (int) $stamp) <= 300, 401, 'Expired signature');
        $message = $stamp."\n".$request->method()."\n".$request->getPathInfo()."\n".hash('sha256', $request->getContent());
        abort_unless(hash_equals(hash_hmac('sha256', $message, $config['secret']), (string) $request->header('X-Apex-Signature', '')), 401, 'Invalid signature');
        abort_if(strlen($request->getContent()) > 1000000, 413, 'Request too large');
        $request->attributes->set('apex_connection', $id);
        app(Bridge::class)->configuration($id); // Validate channel and exclusive inventory ownership.
        try { return $next($request); }
        catch (\Illuminate\Validation\ValidationException $e) { return response()->json(['error' => 'Invalid command inputs', 'errors' => $e->errors()], 422); }
        catch (\Symfony\Component\HttpKernel\Exception\HttpException $e) { return response()->json(['error' => $e->getMessage()], $e->getStatusCode()); }
        catch (\Throwable $e) {
            $trace = (string) \Illuminate\Support\Str::uuid();
            \Illuminate\Support\Facades\Log::error('ApexBridge operation failed', ['trace' => $trace, 'connection_id' => $id, 'exception' => $e]);
            return response()->json(['error' => 'Bridge operation failed', 'trace' => $trace], 500);
        }
    }
}
