<?php

namespace App\Services;

use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;

/**
 * Thin HTTP wrapper around the DumbOLT FastAPI backend.
 *
 * All methods return arrays (decoded JSON) or throw on failure.
 * Server-side only — the API is never exposed to the browser.
 */
class DumbOltClient
{
    protected string $baseUrl;
    protected int $timeout;

    public function __construct(?string $baseUrl = null, int $timeout = 120)
    {
        $this->baseUrl = rtrim($baseUrl ?? config('dumbolt.api_url'), '/');
        $this->timeout = $timeout;
    }

    /**
     * Perform a GET request. Throws on non-2xx unless $allow404.
     */
    protected function get(string $path, array $query = [], bool $allow404 = false): array
    {
        $res = Http::timeout($this->timeout)
            ->acceptJson()
            ->get($this->baseUrl . $path, $query);

        if ($allow404 && $res->status() === 404) {
            return [];
        }
        $res->throw();
        return $res->json() ?? [];
    }

    /**
     * Perform a POST request. Throws on non-2xx unless $allow404.
     */
    protected function post(string $path, array $body = [], bool $allow404 = false): array
    {
        $res = Http::timeout($this->timeout)
            ->acceptJson()
            ->asJson()
            ->post($this->baseUrl . $path, $body);

        if ($allow404 && $res->status() === 404) {
            return [];
        }
        $res->throw();
        return $res->json() ?? [];
    }

    /**
     * Perform a DELETE request.
     */
    protected function delete(string $path, array $body = []): array
    {
        $res = Http::timeout($this->timeout)
            ->acceptJson()
            ->asJson()
            ->delete($this->baseUrl . $path, $body);
        $res->throw();
        return $res->json() ?? [];
    }

    // ── Meta ───────────────────────────────────────────────────
    public function health(): array      { return $this->get('/health'); }
    public function config(): array      { return $this->get('/config'); }

    // ── OLTs ───────────────────────────────────────────────────
    public function olts(): array        { return $this->get('/olts'); }
    public function oltReachable(string $olt): array
    {
        return $this->get('/olts/' . rawurlencode($olt) . '/reachable');
    }
    public function results(string $olt): array
    {
        return $this->get('/olts/' . rawurlencode($olt) . '/results');
    }
    public function portResults(string $olt, int $port): array
    {
        return $this->get(
            '/olts/' . rawurlencode($olt) . '/ports/' . $port,
            [],
            allow404: true
        );
    }
    public function monitor(string $olt, ?array $ports = null): array
    {
        // Always send a JSON object. If no ports given, send {"ports": null}
        // so FastAPI parses it as a dict (not an empty list).
        $body = ['ports' => $ports];   // null or [1,2,3]
        return $this->post('/olts/' . rawurlencode($olt) . '/monitor', $body);
    }

    // ── Search ─────────────────────────────────────────────────
    public function search(string $q, ?string $status = null, int $limit = 50): array
    {
        $query = ['q' => $q, 'limit' => $limit];
        if ($status) {
            $query['status'] = $status;
        }
        return $this->get('/search', $query);
    }

    // ── Actions ────────────────────────────────────────────────
    public function reboot(string $olt, int $port, string $onuId): array
    {
        return $this->post('/reboot', [
            'olt' => $olt, 'port' => $port, 'onu_id' => $onuId,
        ]);
    }
    public function rename(string $olt, int $port, string $onuId, string $name): array
    {
        return $this->post('/rename', [
            'olt' => $olt, 'port' => $port, 'onu_id' => $onuId, 'name' => $name,
        ]);
    }
    public function deleteOnu(string $olt, int $port, string $onuId, string $mac): array
    {
        return $this->delete('/onu', [
            'olt' => $olt, 'port' => $port, 'onu_id' => $onuId, 'mac' => $mac,
        ]);
    }

    // ── Names ──────────────────────────────────────────────────
    public function names(): array       { return $this->get('/names'); }

    // ── Auto-scan ──────────────────────────────────────────────
    public function autoScanStatus(): array { return $this->get('/auto-scan/status'); }
    public function autoScanToggle(bool $enabled): array
    {
        return $this->post('/auto-scan/toggle', ['enabled' => $enabled]);
    }
    public function autoScanConfig(?bool $enabled = null, ?int $interval = null): array
    {
        $body = [];
        if ($enabled !== null) $body['enabled'] = $enabled;
        if ($interval !== null) $body['interval_seconds'] = $interval;
        return $this->post('/auto-scan/config', $body);
    }
    public function autoScanRunNow(): array
    {
        return $this->post('/auto-scan/run-now');
    }

    // ── Alarms ─────────────────────────────────────────────────
    public function alarmRestart(string $olt): array
    {
        return $this->post('/alarms/' . rawurlencode($olt) . '/restart');
    }

    // ── Discovery log ──────────────────────────────────────────
    public function discoveryLog(int $limit = 100): array
    {
        return $this->get('/discovery-log', ['limit' => $limit]);
    }

    // ── Dashboard ──────────────────────────────────────────────
    public function dashboard(): array
    {
        return $this->get('/dashboard');
    }

    // ── Alarms ─────────────────────────────────────────────────
    public function alarmsStatus(): array
    {
        return $this->get('/alarms/status');
    }
    public function alarmsLog(int $limit = 100): array
    {
        return $this->get('/alarms/log', ['limit' => $limit]);
    }}
