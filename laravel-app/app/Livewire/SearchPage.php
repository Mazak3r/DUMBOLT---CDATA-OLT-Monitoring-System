<?php

namespace App\Livewire;

use App\Services\DumbOltClient;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.app')]
class SearchPage extends Component
{
    public string $q = '';
    public ?string $status = null;
    public int $limit = 100;

    public ?array $results = null;
    public ?string $error = null;

    public function search(DumbOltClient $client): void
    {
        $this->error = null;
        $this->results = null;
        if (trim($this->q) === '') {
            return;
        }
        try {
            $this->results = $client->search($this->q, $this->status, $this->limit);
        } catch (\Throwable $e) {
            $this->error = $e->getMessage();
        }
    }

    public function render()
    {
        return view('livewire.search-page');
    }
}
