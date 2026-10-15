<div>
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold">Discovery log</h1>
        <div class="flex items-center gap-2">
            <label class="text-xs text-slate-500 uppercase tracking-wider">Show last</label>
            <input type="number" min="1" max="1000"
                   wire:model.live="limit"
                   class="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm
                          focus:outline-none focus:border-sky-500">
            <button wire:click="load"
                    class="px-3 py-1.5 text-sm rounded-md bg-slate-800 hover:bg-slate-700 transition">
                ⟳ Refresh
            </button>
        </div>
    </div>

    @if ($error)
        <div class="rounded-lg bg-red-900/40 border border-red-700 p-4">
            <div class="text-sm text-red-200 font-mono break-all">{{ $error }}</div>
        </div>
    @elseif ($data)
        <div class="text-xs text-slate-500 font-mono mb-2">{{ $data['file'] ?? '' }}</div>

        @if (($data['count'] ?? 0) === 0)
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-slate-400">
                No entries yet. New ONUs will appear here on first discovery.
            </div>
        @else
            <div class="rounded-lg border border-slate-800 bg-slate-950 p-4 overflow-x-auto">
                <pre class="text-xs font-mono text-slate-300 leading-relaxed">@foreach ($data['lines'] as $line){{ $line }}
@endforeach</pre>
            </div>
        @endif
    @endif
</div>
