<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class OltDetail extends Component
{
    public string $olt;

    public ?array $data = null;
    public ?string $error = null;
    public ?string $flash = null;

    public ?int $monitorPort = null;
    public ?int $monitorStatus = 0;   // 0 idle, 1 running, 2 done, 3 failed

    // public array $renameDraft = [];  // DISABLED — naming is owned by external program

    public function mount(string $olt, DumbOltClient $client): void
    {
        $this->olt = $olt;
        $this->load($client);
    }

    public function load(?DumbOltClient $client = null): void
    {
        $client ??= app(DumbOltClient::class);
        $this->error = null;
        try {
            $this->data = $client->results($this->olt);
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
            $this->data = null;
        }
    }

    public function refresh(): void
    {
        $this->load();
        $this->flash = 'Refreshed';
    }

    public function monitorAll(): void
    {
        $this->monitorPort = null;
        $this->runMonitor();
    }

    public function monitorPort(int $port): void
    {
        $this->monitorPort = $port;
        $this->runMonitor();
    }

    protected function runMonitor(): void
    {
        $this->monitorStatus = 1;
        $this->flash = null;
        try {
            $client = app(DumbOltClient::class);
            $ports = $this->monitorPort ? [$this->monitorPort] : null;
            $client->monitor($this->olt, $ports);
            $this->load($client);
            $this->monitorStatus = 2;
            $this->flash = 'Scan complete';
        } catch (\Throwable $e) {
            $this->monitorStatus = 3;
            $this->error = $e->getMessage();
        }
    }

    public function reboot(int $port, string $onuId): void
    {
        try {
            app(DumbOltClient::class)->reboot($this->olt, $port, $onuId);
            $this->flash = "Reboot sent for ONU $onuId on port $port";
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    /**
     * DISABLED — naming is owned by an external program via onu_names.json.
     * The /rename API endpoint still exists on the Python side, but no UI
     * surface exposes it. Kept here (commented) for future re-enable.
     */
    // public function rename(int $port, string $onuId): void
    // {
    //     $key = "$port|$onuId";
    //     $name = trim($this->renameDraft[$key] ?? '');
    //     try {
    //         app(DumbOltClient::class)->rename($this->olt, $port, $onuId, $name);
    //         $this->load();
    //         $this->flash = $name === ''
    //             ? "Cleared name for ONU $onuId on port $port"
    //             : "Renamed ONU $onuId on port $port to \"$name\"";
    //         unset($this->renameDraft[$key]);
    //     } catch (\Throwable $e) {
    //         $this->error = $e->getMessage();
    //     }
    // }

    public function deleteOnu(int $port, string $onuId, string $mac): void
    {
        try {
            app(DumbOltClient::class)->deleteOnu($this->olt, $port, $onuId, $mac);
            $this->load();
            $this->flash = "Deleted offline ONU $onuId on port $port";
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    public function render()
    {
        return view('livewire.olt-detail');
    }
}
