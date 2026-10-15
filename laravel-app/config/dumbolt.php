<?php

return [
    /*
    |--------------------------------------------------------------------------
    | DumbOLT API base URL
    |--------------------------------------------------------------------------
    | The FastAPI backend that this Laravel app proxies to.
    */
    'api_url' => env('DUMBOLT_API_URL', 'http://localhost:8310'),
];
