<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class AlarmsPage extends Component
{
    public ?array $status = null;
    public ?array $log    = null;
    public ?string $error = null;
    public ?string $flash = null;

    public int $limit = 200;

    public function mount(DumbOltClient $client): void
    {
        $this->load($client);
    }

    public function load(?DumbOltClient $client = null): void
    {
        $client ??= app(DumbOltClient::class);
        $this->error = null;
        try {
            $this->status = $client->alarmsStatus();
            $this->log    = $client->alarmsLog($this->limit);
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
            $this->status = $this->log = null;
        }
    }

    public function restartListener(string $olt): void
    {
        try {
            app(DumbOltClient::class)->alarmRestart($olt);
            $this->load();
            $this->flash = "Listener restarted for $olt";
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    public function render()
    {
        return view('livewire.alarms-page');
    }
}
