<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class OltList extends Component
{
    public ?array $olts = null;
    public ?string $error = null;

    public function mount(DumbOltClient $client): void
    {
        $this->refresh($client);
    }

    public function refresh(?DumbOltClient $client = null): void
    {
        $client ??= app(DumbOltClient::class);
        $this->error = null;
        try {
            $this->olts = $client->olts()['olts'] ?? [];
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
            $this->olts = null;
        }
    }

    public function render()
    {
        return view('livewire.olt-list');
    }
}
