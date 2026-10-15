<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ $title ?? 'DumbOLT' }} · DumbOLT</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
    @livewireStyles
</head>
<body class="h-full">

    @php
        /** @var \App\Models\User|null $user */
        $user = auth()->user();
        $isAdmin = $user?->isAdmin() ?? false;
    @endphp

    <header class="border-b border-slate-800 bg-slate-900/50 backdrop-blur sticky top-0 z-10">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center h-14 gap-6">

            <a href="{{ route('dashboard') }}" class="font-bold text-lg tracking-tight">
                Dumb<span class="text-sky-400">OLT</span>
            </a>

            <nav class="flex items-center gap-1 text-sm">
                @php
                    $links = [
                        ['dashboard',      'Dashboard'],
                        ['olts',           'OLTs'],
                        ['search.page',    'Search'],
                        ['discovery.page', 'Discovery log'],
                    ];
                    // Auto-scan is admin-only — NOC never sees this link
                    if ($isAdmin) {
                        $links[] = ['auto-scan.page', 'Auto-scan'];
                        $links[] = ['alarms.page',    'Alarms'];
                    }
                @endphp

                @foreach ($links as [$routeName, $label])
                    @php $active = request()->routeIs($routeName); @endphp
                    <a href="{{ route($routeName) }}"
                       class="px-3 py-1.5 rounded-md transition
                              {{ $active
                                    ? 'bg-slate-800 text-white'
                                    : 'text-slate-300 hover:bg-slate-800/60 hover:text-white' }}">
                        {{ $label }}
                    </a>
                @endforeach
            </nav>

            <div class="ml-auto flex items-center gap-3 text-sm">
                <div class="text-right leading-tight">
                    <div class="text-slate-200">{{ $user?->name ?? 'guest' }}</div>
                    <div class="text-xs text-slate-500 uppercase tracking-wide">
                        {{ $user?->role ?? '' }}
                    </div>
                </div>
                <form method="POST" action="{{ route('logout') }}">
                    @csrf
                    <button type="submit"
                            class="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 transition text-slate-300">
                        Logout
                    </button>
                </form>
            </div>

        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {{ $slot }}
    </main>

    @livewireScripts
</body>
</html>
