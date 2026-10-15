<?php

use App\Http\Controllers\Auth\LoginController;
use App\Livewire\AutoScanPage;
use App\Livewire\Dashboard;
use App\Livewire\DiscoveryLogPage;
use App\Livewire\OltDetail;
use App\Livewire\OltList;
use App\Livewire\SearchPage;
use Illuminate\Support\Facades\Route;

// ── Public ─────────────────────────────────────────────────────
Route::middleware('guest')->group(function () {
    Route::get('/login',  [LoginController::class, 'showLoginForm'])->name('login');
    Route::post('/login', [LoginController::class, 'login'])->name('login.post');
});

Route::post('/logout', [LoginController::class, 'logout'])
    ->middleware('auth')
    ->name('logout');

// ── Protected ──────────────────────────────────────────────────
Route::middleware('auth')->group(function () {
    Route::get('/',             Dashboard::class)->name('dashboard');
    Route::get('/olts',         OltList::class)->name('olts');
    Route::get('/olts/{olt}',   OltDetail::class)->name('olt.detail');
    Route::get('/search',       SearchPage::class)->name('search.page');
    Route::get('/discovery-log',DiscoveryLogPage::class)->name('discovery.page');

    // Admin-only pages — enforced at the route level too
    Route::middleware('admin')->group(function () {
        Route::get('/auto-scan', AutoScanPage::class)->name('auto-scan.page');
        Route::get('/alarms',    \App\Livewire\AlarmsPage::class)->name('alarms.page');
    });
});

// ── Redirect unauthenticated to login ──────────────────────────
// (Laravel's default auth middleware handles this via the `login` route)
