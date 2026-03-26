// Global configuration for the HelpOn frontend using Supabase
const CONFIG = {
    SUPABASE_URL: 'https://yatmmbytwhpngzofiukt.supabase.co',
    SUPABASE_ANON_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlhdG1tYnl0d2hwbmd6b2ZpdWt0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwODc2MjgsImV4cCI6MjA4OTY2MzYyOH0.aPm4Bk-302CVfacQPkfdyABhB0-EvL4q5hFQiDnfP34'
};

// Initialize Supabase Client
// The CDN UMD build sets: window.supabase = { createClient, ... }
// NOTE: We must NOT use `let supabase` here — the CDN already declares
// `var supabase` globally, and redeclaring with `let` causes a SyntaxError.
// We operate on window.supabase directly instead.
(function () {
    try {
        const lib = window.supabase;
        if (!lib) {
            console.error('[HelpOn] Supabase CDN not loaded — window.supabase is undefined.');
            return;
        }
        if (typeof lib.createClient !== 'function') {
            console.error('[HelpOn] window.supabase has no createClient() — wrong CDN build?', lib);
            return;
        }
        const client = lib.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY);
        if (!client || !client.auth) {
            console.error('[HelpOn] createClient() returned no .auth — check URL and anon key.');
            return;
        }
        // Replace the library object with the live client instance
        window.supabase = client;
        console.log('[HelpOn] Supabase client initialized successfully.');

        // Sync auth state with localStorage
        client.auth.onAuthStateChange((event, session) => {
            if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
                setLoggedInState(true);
                if (session?.user?.user_metadata?.full_name) {
                    localStorage.setItem('helpon_user_name', session.user.user_metadata.full_name);
                }
            } else if (event === 'SIGNED_OUT') {
                setLoggedInState(false);
                localStorage.removeItem('helpon_user_name');
            }
        });

        client.auth.getSession().then(({ data: { session } }) => {
            setLoggedInState(!!session);
        });

    } catch (err) {
        console.error('[HelpOn] Exception during Supabase initialization:', err);
    }
})();

// Helper to check if user is nominally logged in via localStorage
function isUserLoggedIn() {
    return localStorage.getItem('is_logged_in') === 'true';
}

function setLoggedInState(isLoggedIn) {
    if (isLoggedIn) {
        localStorage.setItem('is_logged_in', 'true');
    } else {
        localStorage.removeItem('is_logged_in');
    }
}

async function handleLogout() {
    if (window.supabase && window.supabase.auth) {
        await window.supabase.auth.signOut();
    }
    setLoggedInState(false);
    localStorage.removeItem('helpon_user_name');
    window.location.href = 'index.html';
}

// Legacy stub
async function fetchWithAuth(url, options = {}) {
    console.error('fetchWithAuth is deprecated! Use the supabase client directly.');
    throw new Error('Please migrate this API call to Supabase.');
}
