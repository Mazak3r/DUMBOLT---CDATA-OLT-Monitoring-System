@php
    $totals  = $data['totals']  ?? [];
    $signals = $data['signals'] ?? [];
    $perOlt  = $data['per_olt'] ?? [];
    $outages = $data['pon_outages'] ?? [];
    $lists   = $data['lists']   ?? [];
    $listLimit = $data['list_limit'] ?? 200;

    // Helper closures for the bucket lists
    $onus = fn(string $bucket) => $lists[$bucket] ?? [];
@endphp

<div @if($autoRefresh) wire:poll.{{ $refreshInterval }}s="refresh" @endif>

    {{-- Header --}}
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold">Dashboard</h1>

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

            <span class="text-slate-500">checked {{ $lastCheckedAt ?? '—' }}</span>

            <button wire:click="refresh"
                    wire:loading.attr="disabled"
                    class="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 transition disabled:opacity-50">
                <span wire:loading.remove wire:target="refresh">⟳ Refresh</span>
                <span wire:loading wire:target="refresh">…</span>
            </button>
        </div>
    </div>

    @if ($error)
        <div class="rounded-lg bg-red-900/40 border border-red-700 p-4 mb-6">
            <div class="font-semibold text-red-300">❌ Cannot reach DumbOLT API</div>
            <div class="text-sm text-red-200 font-mono break-all mt-1">{{ $error }}</div>
        </div>
    @elseif ($data)

        {{-- ─── Stat tiles (clickable) ────────────────────────── --}}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">

            {{-- Online --}}
            <button wire:click="toggleBucket('online')"
                    class="text-left rounded-xl border p-5 transition
                           {{ $openBucket === 'online'
                                ? 'border-emerald-500 ring-2 ring-emerald-500/40'
                                : 'border-emerald-800/50 hover:border-emerald-600/70' }}
                           bg-gradient-to-br from-emerald-900/60 to-emerald-950/40">
                <div class="flex items-center justify-between">
                    <div class="text-emerald-300/80 text-sm uppercase tracking-wider">Online</div>
                    <div class="text-2xl">🟢</div>
                </div>
                <div class="text-4xl font-bold text-emerald-200 mt-2">{{ $totals['online'] ?? 0 }}</div>
                <div class="text-xs text-emerald-300/70 mt-2 flex items-center justify-between">
                    <span>Total ONUs: {{ $totals['total'] ?? 0 }}</span>
                    <span class="text-emerald-400/80">{{ $openBucket === 'online' ? '▾ hide' : '▸ view' }}</span>
                </div>
            </button>

            {{-- Offline --}}
            <button wire:click="toggleBucket('offline')"
                    class="text-left rounded-xl border p-5 transition
                           {{ $openBucket === 'offline'
                                ? 'border-slate-500 ring-2 ring-slate-500/40'
                                : 'border-slate-700 hover:border-slate-500' }}
                           bg-gradient-to-br from-slate-800/60 to-slate-900/40">
                <div class="flex items-center justify-between">
                    <div class="text-slate-300/80 text-sm uppercase tracking-wider">Offline</div>
                    <div class="text-2xl">⚫</div>
                </div>
                <div class="text-4xl font-bold text-slate-100 mt-2">{{ $totals['offline'] ?? 0 }}</div>
                <div class="text-xs text-slate-400 mt-2 flex items-center justify-between">
                    <span>Total ONUs: {{ $totals['total'] ?? 0 }}</span>
                    <span class="text-slate-400/80">{{ $openBucket === 'offline' ? '▾ hide' : '▸ view' }}</span>
                </div>
            </button>

            {{-- Low signals — expand combined warning+critical --}}
            @php $lowTotal = ($signals['warning'] ?? 0) + ($signals['critical'] ?? 0); @endphp
            <button wire:click="toggleBucket('signals')"
                    class="text-left rounded-xl border p-5 transition
                           {{ $openBucket === 'signals'
                                ? 'border-amber-500 ring-2 ring-amber-500/40'
                                : 'border-amber-800/50 hover:border-amber-600/70' }}
                           bg-gradient-to-br from-amber-900/50 to-orange-950/40">
                <div class="flex items-center justify-between">
                    <div class="text-amber-300/80 text-sm uppercase tracking-wider">Low signals</div>
                    <div class="text-2xl">⚠</div>
                </div>
                <div class="text-4xl font-bold text-amber-200 mt-2">{{ $lowTotal }}</div>
                <div class="text-xs mt-2 flex items-center justify-between">
                    <span class="flex gap-3">
                        <span class="text-amber-300">
                            Warning: {{ $signals['warning'] ?? 0 }}
                            <span class="text-amber-400/60">(&lt; {{ $signals['warning_threshold'] ?? -24 }} dBm)</span>
                        </span>
                        <span class="text-red-400">
                            Critical: {{ $signals['critical'] ?? 0 }}
                            <span class="text-red-400/60">(&lt; {{ $signals['critical_threshold'] ?? -27 }} dBm)</span>
                        </span>
                    </span>
                    <span class="text-amber-400/80">{{ $openBucket === 'signals' ? '▾ hide' : '▸ view' }}</span>
                </div>
            </button>

            {{-- New (24h) --}}
            <button wire:click="toggleBucket('new_24h')"
                    class="text-left rounded-xl border p-5 transition
                           {{ $openBucket === 'new_24h'
                                ? 'border-sky-500 ring-2 ring-sky-500/40'
                                : 'border-sky-800/50 hover:border-sky-600/70' }}
                           bg-gradient-to-br from-sky-900/60 to-blue-950/40">
                <div class="flex items-center justify-between">
                    <div class="text-sky-300/80 text-sm uppercase tracking-wider">New (24h)</div>
                    <div class="text-2xl">✨</div>
                </div>
                <div class="text-4xl font-bold text-sky-200 mt-2">{{ $totals['new_24h'] ?? 0 }}</div>
                <div class="text-xs text-sky-300/70 mt-2 flex items-center justify-between">
                    <span>OLTs: {{ $totals['olts_count'] ?? 0 }}</span>
                    <span class="text-sky-400/80">{{ $openBucket === 'new_24h' ? '▾ hide' : '▸ view' }}</span>
                </div>
            </button>
        </div>

        {{-- ─── Expanded bucket panel ───────────────────────────── --}}
        @if ($openBucket)
            @php
                $bucketTitles = [
                    'online'   => ['Online ONUs',        'emerald'],
                    'offline'  => ['Offline ONUs',       'slate'],
                    'signals'  => ['Low-signal ONUs',    'amber'],
                    'new_24h'  => ['New ONUs (last 24h)','sky'],
                ];
                [$title, $accent] = $bucketTitles[$openBucket] ?? ['ONUs', 'slate'];

                // For 'signals', combine warning+critical, tag each row
                if ($openBucket === 'signals') {
                    $rows = [];
                    foreach ($onus('critical') as $row) { $row['_band'] = 'critical'; $rows[] = $row; }
                    foreach ($onus('warning')  as $row) { $row['_band'] = 'warning';  $rows[] = $row; }
                } else {
                    $rows = $onus($openBucket);
                }
            @endphp

            <div class="mb-8 rounded-lg border border-{{ $accent }}-700/60 bg-{{ $accent }}-950/20 overflow-hidden">
                <div class="flex items-center justify-between px-4 py-2 bg-{{ $accent }}-900/30 border-b border-{{ $accent }}-800/50">
                    <div class="font-semibold text-{{ $accent }}-200">
                        {{ $title }}
                        <span class="ml-2 text-sm font-normal text-{{ $accent }}-300/70">
                            {{ count($rows) }} shown (max {{ $listLimit }})
                        </span>
                    </div>
                    <button wire:click="toggleBucket('{{ $openBucket }}')"
                            class="text-xs text-{{ $accent }}-300 hover:text-{{ $accent }}-100">
                        ✕ Close
                    </button>
                </div>

                @if (count($rows) === 0)
                    <div class="px-4 py-6 text-sm text-slate-400">No ONUs in this bucket.</div>
                @else
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <thead class="text-slate-400 bg-slate-900/40">
                                <tr>
                                    @if ($openBucket === 'signals')
                                        <th class="text-left px-3 py-2 font-medium w-24">Band</th>
                                    @endif
                                    <th class="text-left px-3 py-2 font-medium">OLT</th>
                                    <th class="text-left px-3 py-2 font-medium w-16">Port</th>
                                    <th class="text-left px-3 py-2 font-medium w-16">ID</th>
                                    <th class="text-left px-3 py-2 font-medium w-20">State</th>
                                    <th class="text-left px-3 py-2 font-medium">Name</th>
                                    <th class="text-left px-3 py-2 font-medium">MAC</th>
                                    <th class="text-left px-3 py-2 font-medium w-28">Signal</th>
                                    <th class="text-left px-3 py-2 font-medium w-40">Last seen</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-800">
                                @foreach ($rows as $row)
                                    <tr class="hover:bg-slate-900/40">
                                        @if ($openBucket === 'signals')
                                            <td class="px-3 py-2">
                                                @if (($row['_band'] ?? '') === 'critical')
                                                    <span class="text-red-400 text-xs">● critical</span>
                                                @else
                                                    <span class="text-amber-400 text-xs">● warning</span>
                                                @endif
                                            </td>
                                        @endif
                                        <td class="px-3 py-2">
                                            <a href="{{ route('olt.detail', ['olt' => $row['olt']]) }}"
                                               class="text-sky-400 hover:text-sky-300">
                                                {{ $row['olt'] }}
                                            </a>
                                        </td>
                                        <td class="px-3 py-2 font-mono">{{ $row['port'] }}</td>
                                        <td class="px-3 py-2 font-mono">{{ $row['ID'] }}</td>
                                        <td class="px-3 py-2">
                                            @if (($row['Status'] ?? '') === 'online')
                                                <span class="text-emerald-400 text-xs">● online</span>
                                            @else
                                                <span class="text-red-400 text-xs">● offline</span>
                                            @endif
                                        </td>
                                        <td class="px-3 py-2">
                                            @if (!empty($row['Name']))
                                                {{ $row['Name'] }}
                                            @else
                                                <span class="text-slate-500 italic">(unnamed)</span>
                                            @endif
                                        </td>
                                        <td class="px-3 py-2 font-mono text-slate-400">{{ $row['Mac address'] ?? '' }}</td>
                                        <td class="px-3 py-2 font-mono">{{ $row['Onu signal'] ?? 'N/A' }}</td>
                                        <td class="px-3 py-2 font-mono text-slate-400 text-xs">{{ $row['last_seen'] ?? '—' }}</td>
                                    </tr>
                                @endforeach
                            </tbody>
                        </table>
                    </div>
                @endif
            </div>
        @endif

        {{-- ─── PON outages ─────────────────────────────────────── --}}
        <div class="mb-8">
            <div class="flex items-center justify-between mb-3">
                <h2 class="text-xl font-semibold">
                    PON outages
                    @if (count($outages) > 0)
                        <span class="ml-2 text-sm font-normal text-slate-400">{{ count($outages) }} port(s)</span>
                    @endif
                </h2>
            </div>

            @if (count($outages) === 0)
                <div class="rounded-lg border border-emerald-800/50 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-200">
                    ✅ All ports are healthy.
                </div>
            @else
                <div class="rounded-lg border border-slate-800 overflow-hidden">
                    <table class="w-full text-sm">
                        <thead class="bg-slate-900/60 text-slate-400">
                            <tr>
                                <th class="text-left px-3 py-2 font-medium w-24">Severity</th>
                                <th class="text-left px-3 py-2 font-medium">OLT</th>
                                <th class="text-left px-3 py-2 font-medium w-20">Port</th>
                                <th class="text-right px-3 py-2 font-medium w-24">Online</th>
                                <th class="text-right px-3 py-2 font-medium w-24">Offline</th>
                                <th class="text-right px-3 py-2 font-medium w-28">Total ever</th>
                                <th class="text-left px-3 py-2 font-medium">Last online seen</th>
                                <th class="text-right px-3 py-2 font-medium w-24"></th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800">
                            @foreach ($outages as $o)
                                <tr class="hover:bg-slate-900/40">
                                    <td class="px-3 py-2">
                                        @if ($o['severity'] === 'critical')
                                            <span class="text-red-400">● critical</span>
                                        @else
                                            <span class="text-amber-400">● warning</span>
                                        @endif
                                    </td>
                                    <td class="px-3 py-2">
                                        <a href="{{ route('olt.detail', ['olt' => $o['olt']]) }}"
                                           class="text-sky-400 hover:text-sky-300">
                                            {{ $o['olt'] }}
                                        </a>
                                    </td>
                                    <td class="px-3 py-2 font-mono">{{ $o['port'] }}</td>
                                    <td class="px-3 py-2 font-mono text-right">{{ $o['online'] }}</td>
                                    <td class="px-3 py-2 font-mono text-right">{{ $o['offline'] }}</td>
                                    <td class="px-3 py-2 font-mono text-right">{{ $o['total_ever'] }}</td>
                                    <td class="px-3 py-2 font-mono text-slate-400">{{ $o['last_online_seen'] ?? '—' }}</td>
                                    <td class="px-3 py-2 text-right">
                                        <a href="{{ route('olt.detail', ['olt' => $o['olt']]) }}"
                                           class="text-xs text-slate-400 hover:text-slate-200">
                                            Open →
                                        </a>
                                    </td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                </div>
            @endif
        </div>

        {{-- ─── Per-OLT summary ─────────────────────────────────── --}}
        <div>
            <h2 class="text-xl font-semibold mb-3">Per OLT</h2>
            <div class="rounded-lg border border-slate-800 overflow-hidden">
                <table class="w-full text-sm">
                    <thead class="bg-slate-900/60 text-slate-400">
                        <tr>
                            <th class="text-left px-3 py-2 font-medium">OLT</th>
                            <th class="text-left px-3 py-2 font-medium">IP</th>
                            <th class="text-right px-3 py-2 font-medium w-24">Online</th>
                            <th class="text-right px-3 py-2 font-medium w-24">Offline</th>
                            <th class="text-right px-3 py-2 font-medium w-24">Total</th>
                            <th class="text-right px-3 py-2 font-medium w-24"></th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800">
                        @foreach ($perOlt as $row)
                            <tr class="hover:bg-slate-900/40">
                                <td class="px-3 py-2 font-medium">{{ $row['olt'] }}</td>
                                <td class="px-3 py-2 font-mono text-slate-400">{{ $row['olt_ip'] }}</td>
                                <td class="px-3 py-2 font-mono text-right text-emerald-400">{{ $row['online'] }}</td>
                                <td class="px-3 py-2 font-mono text-right text-slate-400">{{ $row['offline'] }}</td>
                                <td class="px-3 py-2 font-mono text-right">{{ $row['total'] }}</td>
                                <td class="px-3 py-2 text-right">
                                    <a href="{{ route('olt.detail', ['olt' => $row['olt']]) }}"
                                       class="text-xs text-sky-400 hover:text-sky-300">
                                        Open →
                                    </a>
                                </td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </div>
        </div>

    @endif
</div>
