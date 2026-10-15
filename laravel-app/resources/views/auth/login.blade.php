<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Login · DumbOLT</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="h-full">
    <div class="min-h-full flex items-center justify-center p-8">
        <div class="w-full max-w-sm">

            <div class="text-center mb-8">
                <div class="text-3xl font-bold tracking-tight">
                    Dumb<span class="text-sky-400">OLT</span>
                </div>
                <div class="text-sm text-slate-500 mt-1">Cdata EPON monitor</div>
            </div>

            <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-6">
                <form method="POST" action="{{ route('login.post') }}" class="space-y-4">
                    @csrf

                    <div>
                        <label class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Username</label>
                        <input type="text"
                               name="username"
                               value="{{ old('username') }}"
                               autofocus
                               required
                               class="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2
                                      focus:outline-none focus:border-sky-500">
                    </div>

                    <div>
                        <label class="block text-xs text-slate-500 uppercase tracking-wider mb-1">Password</label>
                        <input type="password"
                               name="password"
                               required
                               class="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2
                                      focus:outline-none focus:border-sky-500">
                    </div>

                    <label class="flex items-center gap-2 text-sm text-slate-400">
                        <input type="checkbox" name="remember" value="1"
                               class="rounded border-slate-700 bg-slate-900">
                        Remember me
                    </label>

                    @if ($errors->any())
                        <div class="rounded bg-red-900/40 border border-red-700 px-3 py-2 text-sm text-red-200">
                            {{ $errors->first() }}
                        </div>
                    @endif

                    <button type="submit"
                            class="w-full py-2 rounded-md bg-sky-600 hover:bg-sky-500 transition font-medium">
                        Log in
                    </button>
                </form>
            </div>

        </div>
    </div>
</body>
</html>
