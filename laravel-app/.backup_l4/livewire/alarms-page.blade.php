<div @if($autoRefresh) wire:poll.{{ $refreshInterval }}s="load" @endif>

    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold">Alarms</h1>

        <div class="flex items-center gap-3 text-sm">
            <label class="flex items-center gap-2 cursor-pointer select-none">
                <input type="checkbox"
                       wire:click="toggleAutoRefresh"
                       @checked($autoRefresh)
                       class="rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500">
                <span class="{{ $autoRefresh ? 'text-emerald-400' : 'text-slate-400' }}">
                    ● Auto-refresh {{ $autoRefresh ? "({$refreshInterval}s)" : 'off' }}
                </span>
            </label>

            <button wire:click="load"
                    wire:loading.attr="disabled"
                    class="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 transition disabled:opacity-50">
                <span wire:loading.remove wire:target="load">⟳ Refresh</span>
                <span wire:loading wire:target="load">…</span>
            </button>
        </div>
    </div>

    @if ($flash)
        <div class="rounded-lg bg-emerald-900/40 border border-emerald-700 px-4 py-2 mb-4 text-sm text-emerald-200">
            {{ $flash }}
        </div>
    @endif
    @if ($error)
        <div class="rounded-lg bg-red-900/40 border border-red-700 px-4 py-2 mb-4 text-sm text-red-200">
            <span class="font-mono break-all">{{ $error }}</span>
        </div>
    @endif

    {{-- Listener status --}}
    @if ($status)
        <h2 class="text-lg font-semibold mb-3">Listeners</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
            @foreach (($status['listeners'] ?? []) as $oltName => $l)
                <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                    <div class="flex items-start justify-between mb-2">
                        <div class="font-semibold">{{ $oltName }}</div>
                        @if (!empty($l['connected']))
                            <span class="text-emerald-400 text-xs">● connected</span>
                        @else
                            <span class="text-red-400 text-xs">● disconnected</span>
                        @endif
                    </div>
                    <div class="text-xs font-mono text-slate-400 mb-2">{{ $l['olt_ip'] }}</div>

                    <div class="grid grid-cols-2 gap-2 text-xs mt-3">
                        <div>
                            <div class="text-slate-500">Events</div>
                            <div class="font-mono">{{ $l['events_processed'] ?? 0 }}</div>
                        </div>
                        <div>
                            <div class="text-slate-500">Reconnects</div>
                            <div class="font-mono">{{ $l['reconnects'] ?? 0 }}</div>
                        </div>
                        <div class="col-span-2">
                            <div class="text-slate-500">Last event</div>
                            <div class="font-mono">{{ $l['last_event_at'] ?? 'never' }}</div>
                        </div>
                        @if (!empty($l['last_error']))
                            <div class="col-span-2">
                                <div class="text-slate-500">Last error</div>
                                <div class="font-mono text-red-300 break-all">{{ $l['last_error'] }}</div>
                            </div>
                        @endif
                    </div>

                    <button wire:click="restart('{{ $oltName }}')"
                            wire:confirm="Restart listener for {{ $oltName }}?"
                            class="mt-3 w-full text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 transition">
                        ⟳ Restart listener
                    </button>
                </div>
            @endforeach
        </div>
    @endif

    {{-- Alarm log tail --}}
    <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Recent alarms</h2>
        <div class="flex items-center gap-2">
            <label class="text-xs text-slate-500 uppercase tracking-wider">Show last</label>
            <input type="number" min="10" max="5000"
                   wire:model.live="logLimit"
                   class="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm
                          focus:outline-none focus:border-sky-500">
        </div>
    </div>

    @if ($log && ($log['count'] ?? 0) > 0)
        <div class="rounded-lg border border-slate-800 bg-slate-950 p-4 overflow-x-auto">
            <pre class="text-xs font-mono text-slate-300 leading-relaxed">@foreach ($log['lines'] as $line){{ $line }}
@endforeach</pre>
        </div>
    @else
        <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-slate-400">
            No alarms yet. New ONU online/offline events will appear here.
        </div>
    @endif
</div>
