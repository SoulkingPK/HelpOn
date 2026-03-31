// HelpOn Service Worker
// Provides offline support for static assets with a network-first strategy for API calls

const CACHE_NAME = 'helpon-v3';
const STATIC_ASSETS = [
    'index.html',
    'register.html',
    'home.html',
    'map.html',
    'profile.html',
    'rewards.html',
    'inbox.html',
    'history.html',
    'leaderboard.html',
    'help.html',
    'admin.html',
    'config.js',
    'manifest.json',
    'css/style.css',
    'js/utils.js'
];

// Install: cache all static assets
self.addEventListener('install', event => {
    console.log('[SW] Installing HelpOn Service Worker...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('[SW] Caching static assets...');
                // Use individual fetch wrapped in try/catch to avoid install failure if one asset 404s
                return Promise.allSettled(
                    STATIC_ASSETS.map(url =>
                        cache.add(url).catch(err => console.warn(`[SW] Cache miss for ${url}:`, err))
                    )
                );
            })
            .then(() => self.skipWaiting())
    );
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
    console.log('[SW] Activating HelpOn Service Worker...');
    event.waitUntil(
        caches.keys()
            .then(cacheNames => {
                return Promise.all(
                    cacheNames
                        .filter(name => name !== CACHE_NAME)
                        .map(name => {
                            console.log('[SW] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => self.clients.claim())
    );
});

// Fetch: Network-first for API, Cache-first for static assets
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Skip non-GET requests
    if (event.request.method !== 'GET') return;

    // Skip websocket and chrome-extension requests
    if (url.protocol === 'ws:' || url.protocol === 'wss:' || url.protocol === 'chrome-extension:') return;

    // API calls (Legacy & Supabase): always go to network, never cache
    if (url.pathname.startsWith('/api/') || url.hostname.includes('supabase.co')) {
        event.respondWith(fetch(event.request));
        return;
    }

    // External CDN resources: network first, fallback to cache
    if (!url.hostname.includes('soulkingpk.github.io') && !url.hostname.includes('localhost') && !url.hostname.includes('127.0.0.1')) {
        event.respondWith(
            fetch(event.request)
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // Static App assets: Cache-first, fallback to network
    event.respondWith(
        caches.match(event.request)
            .then(cached => {
                if (cached) return cached;
                return fetch(event.request)
                    .then(response => {
                        // Cache valid responses
                        if (response && response.status === 200 && response.type === 'basic') {
                            const cloned = response.clone();
                            caches.open(CACHE_NAME).then(cache => cache.put(event.request, cloned));
                        }
                        return response;
                    })
                    .catch(() => {
                        // Offline fallback for navigation requests
                        if (event.request.mode === 'navigate') {
                            return caches.match('/client/index.html');
                        }
                    });
            })
    );
});
