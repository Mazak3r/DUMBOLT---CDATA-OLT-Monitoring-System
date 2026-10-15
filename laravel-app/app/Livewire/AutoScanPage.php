<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class AutoScanPage extends Component
{
    public ?array $status = null;
    public ?string $error = null;
    public ?string $flash = null;

    public ?int $newInterval = null;

    public function mount(DumbOltClient $client): void
    {
        $this->load($client);
    }

    public function load(?DumbOltClient $client = null): void
    {
        $client ??= app(DumbOltClient::class);
        try {
            $this->status = $client->autoScanStatus();
            $this->newInterval = $this->status['interval'] ?? 300;
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
            $this->status = null;
        }
    }

    public function toggle(): void
    {
        try {
            $client = app(DumbOltClient::class);
            $enabled = !($this->status['enabled'] ?? false);
            $client->autoScanToggle($enabled);
            $this->load($client);
            $this->flash = $enabled ? 'Auto-scan enabled' : 'Auto-scan disabled';
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    public function saveInterval(): void
    {
        try {
            $client = app(DumbOltClient::class);
            $client->autoScanConfig(interval: (int)$this->newInterval);
            $this->load($client);
            $this->flash = "Interval set to {$this->newInterval}s";
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    public function runNow(): void
    {
        $this->flash = null;
        try {
            app(DumbOltClient::class)->autoScanRunNow();
            $this->load();
            $this->flash = 'Cycle triggered';
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    public function render()
    {
        return view('livewire.auto-scan-page');
    }
}
