<div>
    <h1 class="text-2xl font-bold mb-6">Auto-scan</h1>

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
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider">State</div>
                <div class="mt-1">
                    @if (!empty($status['enabled']))
                        <span class="text-emerald-400">● enabled</span>
                    @else
                        <span class="text-slate-400">○ disabled</span>
                    @endif
                </div>
                <button wire:click="toggle"
                        class="mt-3 px-3 py-1.5 text-sm rounded-md bg-slate-800 hover:bg-slate-700 transition">
                    {{ !empty($status['enabled']) ? 'Disable' : 'Enable' }}
                </button>
            </div>

            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider">Interval (seconds)</div>
                <div class="mt-1 flex items-center gap-2">
                    <input type="number" min="10" max="86400"
                           wire:model="newInterval"
                           class="w-28 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm
                                  focus:outline-none focus:border-sky-500">
                    <button wire:click="saveInterval"
                            class="px-3 py-1.5 text-sm rounded-md bg-slate-800 hover:bg-slate-700 transition">
                        Save
                    </button>
                </div>
                <div class="text-xs text-slate-500 mt-2">
                    currently: {{ $status['interval'] ?? '?' }}s
                </div>
            </div>

            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider">Run a cycle now</div>
                <button wire:click="runNow"
                        wire:loading.attr="disabled"
                        class="mt-3 px-3 py-1.5 text-sm rounded-md bg-sky-600 hover:bg-sky-500 transition disabled:opacity-50">
                    <span wire:loading.remove wire:target="runNow">▶ Run now</span>
                    <span wire:loading wire:target="runNow">Running…</span>
                </button>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider">Last run</div>
                <div class="mt-1 text-sm">{{ $status['last_run'] ?? 'never' }}</div>
            </div>
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider">Next run</div>
                <div class="mt-1 text-sm">{{ $status['next_run'] ?? '—' }}</div>
            </div>
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div class="text-xs text-slate-500 uppercase tracking-wider">Currently running</div>
                <div class="mt-1 text-sm">
                    @if (!empty($status['running']))
                        <span class="text-amber-400">● yes</span>
                    @else
                        <span class="text-slate-400">○ no</span>
                    @endif
                </div>
            </div>
        </div>

        @if (!empty($status['last_result']))
            <h2 class="text-lg font-semibold mb-3">Last cycle results</h2>
            <div class="rounded-lg border border-slate-800 overflow-hidden">
                <table class="w-full text-sm">
                    <thead class="text-slate-400 bg-slate-900/60">
                        <tr>
                            <th class="text-left px-3 py-2 font-medium">OLT</th>
                            <th class="text-left px-3 py-2 font-medium w-24">OK</th>
                            <th class="text-left px-3 py-2 font-medium w-24">ONUs</th>
                            <th class="text-left px-3 py-2 font-medium">Error</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800">
                        @foreach ($status['last_result'] as $oltName => $r)
                            <tr>
                                <td class="px-3 py-2">{{ $oltName }}</td>
                                <td class="px-3 py-2">
                                    @if (!empty($r['ok']))
                                        <span class="text-emerald-400">✅</span>
                                    @else
                                        <span class="text-red-400">❌</span>
                                    @endif
                                </td>
                                <td class="px-3 py-2 font-mono">{{ $r['total_onus'] ?? 0 }}</td>
                                <td class="px-3 py-2 text-xs font-mono text-red-300">{{ $r['error'] ?? '' }}</td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </div>
        @endif
    @endif
</div>
