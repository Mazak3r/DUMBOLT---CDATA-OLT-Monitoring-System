<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class UserSeeder extends Seeder
{
    public function run(): void
    {
        // admin — full access
        User::updateOrCreate(
            ['email' => 'admin'],
            [
                'name'     => 'admin',
                'password' => Hash::make('admin'),
                'role'     => 'admin',
            ]
        );

        // noc — view + reboot + rename only
        User::updateOrCreate(
            ['email' => 'noc'],
            [
                'name'     => 'user',
                'password' => Hash::make('user'),
                'role'     => 'noc',
            ]
        );
    }
}
