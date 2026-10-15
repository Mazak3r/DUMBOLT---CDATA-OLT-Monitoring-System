<div>
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold">OLTs</h1>
        <button wire:click="refresh"
                class="px-3 py-1.5 text-sm rounded-md bg-slate-800 hover:bg-slate-700 transition">
            ⟳ Refresh
        </button>
    </div>

    @if ($error)
        <div class="rounded-lg bg-red-900/40 border border-red-700 p-4">
            <div class="font-semibold text-red-300">❌ Error</div>
            <div class="text-sm text-red-200 font-mono break-all mt-1">{{ $error }}</div>
        </div>
    @elseif (count($olts ?? []) === 0)
        <p class="text-slate-400">No OLTs registered in bts_config.json.</p>
    @else
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            @foreach ($olts as $olt)
                <a href="{{ route('olt.detail', ['olt' => $olt['name']]) }}"
                   class="block rounded-lg border border-slate-800 bg-slate-900/50 hover:bg-slate-900 transition p-4">
                    <div class="flex items-start justify-between mb-2">
                        <div class="font-semibold">{{ $olt['name'] }}</div>
                        @if (!empty($olt['reachable']))
                            <span class="text-emerald-400 text-xs">● reachable</span>
                        @else
                            <span class="text-red-400 text-xs">● unreachable</span>
                        @endif
                    </div>
                    <div class="text-sm font-mono text-slate-400">{{ $olt['ip'] }}</div>
                </a>
            @endforeach
        </div>
    @endif
</div>
