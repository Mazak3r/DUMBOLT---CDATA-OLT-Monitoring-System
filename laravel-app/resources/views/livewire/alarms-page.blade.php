<div>
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold">Alarms</h1>
        <button wire:click="load"
                class="px-3 py-1.5 text-sm rounded-md bg-slate-800 hover:bg-slate-700 transition">
            ⟳ Refresh
        </button>
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

    @if ($status)
        <h2 class="text-lg font-semibold mb-3">Listeners</h2>
        <div class="rounded-lg border border-slate-800 overflow-hidden mb-8">
            <table class="w-full text-sm">
                <thead class="text-slate-400 bg-slate-900/60">
                    <tr>
                        <th class="text-left px-3 py-2 font-medium">OLT</th>
                        <th class="text-left px-3 py-2 font-medium w-28">Connected</th>
                        <th class="text-left px-3 py-2 font-medium">Last event</th>
                        <th class="text-left px-3 py-2 font-medium w-40">Events processed</th>
                        <th class="text-right px-3 py-2 font-medium w-32"></th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800">
                    @foreach (($status['listeners'] ?? []) as $name => $l)
                        <tr class="hover:bg-slate-900/40">
                            <td class="px-3 py-2 font-medium">{{ $name }}</td>
                            <td class="px-3 py-2">
                                @if (!empty($l['connected']))
                                    <span class="text-emerald-400">● yes</span>
                                @else
                                    <span class="text-red-400">● no</span>
                                @endif
                            </td>
                            <td class="px-3 py-2 font-mono text-xs text-slate-400">{{ $l['last_event_at'] ?? '—' }}</td>
                            <td class="px-3 py-2 font-mono">{{ $l['events_processed'] ?? 0 }}</td>
                            <td class="px-3 py-2 text-right">
                                <button wire:click="restartListener('{{ $name }}')"
                                        wire:confirm="Restart listener for {{ $name }}?"
                                        class="text-xs px-2 py-1 rounded bg-amber-700 hover:bg-amber-600 transition">
                                    Restart
                                </button>
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>
    @endif

    @if ($log)
        <h2 class="text-lg font-semibold mb-3">Recent alarm log</h2>
        <div class="mb-3 flex items-center gap-2 text-sm">
            <label class="text-slate-500">Show last</label>
            <input type="number" min="1" max="5000"
                   wire:model="limit"
                   wire:change="load"
                   class="w-20 bg-slate-800 border border-slate-700 rounded px-2 py-1
                          focus:outline-none focus:border-sky-500">
            <span class="text-slate-500">lines</span>
        </div>
        @if (($log['count'] ?? 0) === 0)
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-slate-400">
                No alarm entries yet.
            </div>
        @else
            <div class="rounded-lg border border-slate-800 bg-slate-950 p-4 overflow-x-auto max-h-[600px] overflow-y-auto">
                <pre class="text-xs font-mono text-slate-300 leading-relaxed">@foreach ($log['lines'] as $line){{ $line }}
@endforeach</pre>
            </div>
        @endif
    @endif
</div>
