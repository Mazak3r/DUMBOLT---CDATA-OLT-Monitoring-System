<div>
    <h1 class="text-2xl font-bold mb-6">Search</h1>

    <form wire:submit="search" class="mb-6 flex flex-wrap items-end gap-3">
        <div class="flex-1 min-w-[16rem]">
            <label class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Query</label>
            <input type="text"
                   wire:model="q"
                   placeholder="MAC substring or name…"
                   class="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2
                          focus:outline-none focus:border-sky-500">
        </div>

        <div>
            <label class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Status</label>
            <select wire:model="status"
                    class="bg-slate-900 border border-slate-700 rounded px-3 py-2
                           focus:outline-none focus:border-sky-500">
                <option value="">Any</option>
                <option value="online">Online</option>
                <option value="offline">Offline</option>
            </select>
        </div>

        <div>
            <label class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Limit</label>
            <input type="number" min="1" max="500"
                   wire:model="limit"
                   class="w-24 bg-slate-900 border border-slate-700 rounded px-3 py-2
                          focus:outline-none focus:border-sky-500">
        </div>

        <button type="submit"
                class="px-4 py-2 rounded-md bg-sky-600 hover:bg-sky-500 transition">
            Search
        </button>
    </form>

    @if ($error)
        <div class="rounded-lg bg-red-900/40 border border-red-700 p-4 mb-4">
            <div class="text-sm text-red-200 font-mono break-all">{{ $error }}</div>
        </div>
    @endif

    @if ($results !== null)
        <div class="text-sm text-slate-400 mb-3">
            {{ $results['count'] ?? 0 }} result(s) for "{{ $results['query'] ?? '' }}"
            @if (!empty($results['status_filter']))
                (status = {{ $results['status_filter'] }})
            @endif
        </div>

        @if (($results['count'] ?? 0) === 0)
            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-6 text-slate-400">
                No matches.
            </div>
        @else
            <div class="rounded-lg border border-slate-800 overflow-hidden">
                <table class="w-full text-sm">
                    <thead class="text-slate-400 bg-slate-900/60">
                        <tr>
                            <th class="text-left px-3 py-2 font-medium">OLT</th>
                            <th class="text-left px-3 py-2 font-medium w-16">Port</th>
                            <th class="text-left px-3 py-2 font-medium w-16">ID</th>
                            <th class="text-left px-3 py-2 font-medium w-20">Status</th>
                            <th class="text-left px-3 py-2 font-medium">Name</th>
                            <th class="text-left px-3 py-2 font-medium">MAC</th>
                            <th class="text-left px-3 py-2 font-medium w-28">Signal</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800">
                        @foreach ($results['results'] as $hit)
                            @php $onu = $hit['onu']; @endphp
                            <tr class="hover:bg-slate-900/40">
                                <td class="px-3 py-2">
                                    <a href="{{ route('olt.detail', ['olt' => $hit['olt']]) }}"
                                       class="text-sky-400 hover:text-sky-300">
                                        {{ $hit['olt'] }}
                                    </a>
                                </td>
                                <td class="px-3 py-2 font-mono">{{ $hit['port'] }}</td>
                                <td class="px-3 py-2 font-mono">{{ $onu['ID'] ?? '' }}</td>
                                <td class="px-3 py-2">
                                    @if (($onu['Status'] ?? '') === 'online')
                                        <span class="text-emerald-400">● online</span>
                                    @else
                                        <span class="text-red-400">● offline</span>
                                    @endif
                                </td>
                                <td class="px-3 py-2">
                                    @if (!empty($onu['Name']))
                                        {{ $onu['Name'] }}
                                    @else
                                        <span class="text-slate-500 italic">(unnamed)</span>
                                    @endif
                                </td>
                                <td class="px-3 py-2 font-mono text-slate-400">{{ $onu['Mac address'] ?? '' }}</td>
                                <td class="px-3 py-2 font-mono">{{ $onu['Onu signal'] ?? 'N/A' }}</td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </div>
        @endif
    @endif
</div>
