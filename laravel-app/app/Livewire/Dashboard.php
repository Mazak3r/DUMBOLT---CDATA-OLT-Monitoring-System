<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class Dashboard extends Component
{
    public ?array $data = null;
    public ?string $error = null;
    public ?string $lastCheckedAt = null;

    public bool $autoRefresh = false;
    public int $refreshInterval = 15;

    /** Which tile is currently expanded (null = all collapsed) */
    public ?string $openBucket = null;

    public function mount(DumbOltClient $client): void
    {
        try {
            $cfg = $client->config();
            $this->refreshInterval = (int) ($cfg['dashboard']['refresh_interval_seconds'] ?? 15);
        } catch (\Throwable $e) {
            // keep default
        }
        $this->refresh($client);
    }

    public function refresh(?DumbOltClient $client = null): void
    {
        $client ??= app(DumbOltClient::class);
        $this->error = null;
        try {
            $this->data = $client->dashboard();
            $this->lastCheckedAt = now()->format('H:i:s');
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
            $this->data = null;
        }
    }

    public function toggleAutoRefresh(): void
    {
        $this->autoRefresh = !$this->autoRefresh;
    }

    /** Toggle a bucket open/closed. Clicking the open one collapses. */
    public function toggleBucket(string $bucket): void
    {
        $this->openBucket = ($this->openBucket === $bucket) ? null : $bucket;
    }

    public function render()
    {
        return view('livewire.dashboard');
    }
}
