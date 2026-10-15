<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class DiscoveryLogPage extends Component
{
    public int $limit = 100;
    public ?array $data = null;
    public ?string $error = null;

    public function mount(DumbOltClient $client): void
    {
        $this->load($client);
    }

    public function load(?DumbOltClient $client = null): void
    {
        $client ??= app(DumbOltClient::class);
        try {
            $this->data = $client->discoveryLog($this->limit);
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
            $this->data = null;
        }
    }

    public function updatedLimit(): void
    {
        $this->load();
    }

    public function render()
    {
        return view('livewire.discovery-log-page');
    }
}
