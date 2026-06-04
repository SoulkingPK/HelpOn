// Global configuration for the HelpOn frontend using Supabase
// IMPORTANT: The __SUPABASE_URL__ and __SUPABASE_ANON_KEY__ tokens are
// substituted at Netlify build time by the build.command in netlify.toml.
// They are NOT secret — the anon key is a public, RLS-restricted key.
// Never commit real values here. Use Netlify env vars instead.
window.CONFIG = {
    SUPABASE_URL: '__SUPABASE_URL__',
    SUPABASE_ANON_KEY: '__SUPABASE_ANON_KEY__',
    API_BASE_URL: '/api'
};

// Also set separate window globals for maximum reliability
window.SUPABASE_URL = window.CONFIG.SUPABASE_URL;
window.SUPABASE_ANON_KEY = window.CONFIG.SUPABASE_ANON_KEY;

// Synchronous login presence check (localStorage only — used as a fast pre-check
// before the async JWT validation below kicks in on DOMContentLoaded).
// ⚠️  This does NOT verify the token signature — it only checks whether a
//     Supabase session key exists. Pages should ALWAYS perform the full async
//     check via supabase.auth.getSession() / getUser() before rendering
//     protected content. This helper exists only for immediate redirect UX.
window.isUserLoggedIn = function() {
    try {
        if (!window.CONFIG || !window.CONFIG.SUPABASE_URL || window.CONFIG.SUPABASE_URL.includes('__SUPABASE_URL__')) {
            return false;
        }
        const parts = window.CONFIG.SUPABASE_URL.split('//');
        if (parts.length < 2) return false;
        const projectRef = parts[1].split('.')[0];
        const tokenKey = `sb-${projectRef}-auth-token`;
        return localStorage.getItem(tokenKey) !== null;
    } catch (e) {
        console.warn('[HelpOn] isUserLoggedIn check failed:', e);
        return false;
    }
};

// Real async session validation. Resolves to the session object if the
// token is valid (signature check done by Supabase), or null if not.
// Use this — not isUserLoggedIn() — to guard protected content.
window.getValidSession = async function() {
    if (!window.supabase || typeof window.supabase.auth === 'undefined') return null;
    try {
        const { data: { session }, error } = await window.supabase.auth.getSession();
        if (error || !session) return null;
        // Cross-check against getUser() to ensure the JWT is accepted server-side
        const { data: { user }, error: userErr } = await window.supabase.auth.getUser();
        if (userErr || !user) return null;
        return session;
    } catch (e) {
        console.warn('[HelpOn] getValidSession error:', e);
        return null;
    }
};

// Initialize the global supabase client instance immediately
if (window.supabase && typeof window.supabase.createClient === 'function') {
    window.supabase = window.supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY, {
        auth: {
            persistSession: true,
            detectSessionInUrl: true
        }
    });
    console.log('[HelpOn] Supabase client initialized and set to window.supabase.');
} else {
    console.warn('[HelpOn] Supabase library not loaded when config.js executed.');
}

// Log for debugging
console.log('[HelpOn] Configuration loaded.');

