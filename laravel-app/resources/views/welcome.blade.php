<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>DumbOLT</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="h-full">
    <div class="min-h-full flex items-center justify-center p-8">
        <div class="max-w-2xl w-full">

            <h1 class="text-3xl font-bold mb-2">DumbOLT</h1>
            <p class="text-slate-400 mb-8">Cdata EPON monitor &amp; ONU management</p>

            @if ($error)
                <div class="rounded-lg bg-red-900/40 border border-red-700 p-4 mb-6">
                    <div class="font-semibold text-red-300 mb-1">❌ Cannot reach DumbOLT API</div>
                    <div class="text-sm text-red-200 font-mono break-all">{{ $error }}</div>
                </div>
            @else
                <div class="rounded-lg bg-emerald-900/40 border border-emerald-700 p-4 mb-6">
                    <div class="font-semibold text-emerald-300">
                        ✅ Connected to DumbOLT
                    </div>
                    <div class="text-sm text-emerald-200 mt-1">
                        {{ $health['olts_loaded'] ?? 0 }} OLT(s) loaded ·
                        {{ $health['names_entries'] ?? 0 }} name(s) in onu_names.json ·
                        server time {{ $health['time'] ?? '?' }}
                    </div>
                </div>

                @if (count($olts) > 0)
                    <h2 class="text-xl font-semibold mb-3">OLTs</h2>
                    <ul class="divide-y divide-slate-800 rounded-lg border border-slate-800">
                        @foreach ($olts as $olt)
                            <li class="px-4 py-3 flex items-center justify-between">
                                <div>
                                    <div class="font-medium">{{ $olt['name'] }}</div>
                                    <div class="text-sm text-slate-400 font-mono">{{ $olt['ip'] }}</div>
                                </div>
                                <div>
                                    @if (!empty($olt['reachable']))
                                        <span class="text-emerald-400 text-sm">● reachable</span>
                                    @else
                                        <span class="text-red-400 text-sm">● unreachable</span>
                                    @endif
                                </div>
                            </li>
                        @endforeach
                    </ul>
                @else
                    <p class="text-slate-400">No OLTs registered in bts_config.json.</p>
                @endif
            @endif

        </div>
    </div>
</body>
</html>
