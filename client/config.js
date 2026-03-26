// Global configuration for the HelpOn frontend using Supabase
const CONFIG = {
    // IMPORTANT: Replace these with your actual Supabase URL and Anon Key
    SUPABASE_URL: 'https://yatmmbytwhpngzofiukt.supabase.co',
    SUPABASE_ANON_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlhdG1tYnl0d2hwbmd6b2ZpdWt0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwODc2MjgsImV4cCI6MjA4OTY2MzYyOH0.aPm4Bk-302CVfacQPkfdyABhB0-EvL4q5hFQiDnfP34'
};

// Initialize Supabase Client
// The CDN UMD build exposes: window.supabase = { createClient, ... }
// We call createClient here and replace window.supabase with the live client.
let supabase;
(function () {
    try {
        const lib = window.supabase;
        if (!lib) {
            console.error('[HelpOn] Supabase CDN script not loaded — window.supabase is undefined.');
            return;
        }
        if (typeof lib.createClient !== 'function') {
            console.error('[HelpOn] window.supabase exists but has no createClient(). CDN may have loaded the wrong build.', lib);
            return;
        }
        const client = lib.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY);
        if (!client || !client.auth) {
            console.error('[HelpOn] createClient() returned an object without .auth — check your Supabase URL and anon key.');
            return;
        }
        supabase = client;
        window.supabase = client;
        console.log('[HelpOn] Supabase client initialized successfully.');
    } catch (err) {
        console.error('[HelpOn] Exception during Supabase initialization:', err);
    }
})();



// Helper to check if user is nominally logged in via localStorage as a quick check
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

// Ensure Supabase session is synced with localStorage
if (supabase) {
    supabase.auth.onAuthStateChange((event, session) => {
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

    // Run initial sync check
    supabase.auth.getSession().then(({ data: { session } }) => {
        setLoggedInState(!!session);
    });
} else {
    console.error("Supabase client library not loaded. Make sure the CDN script is included in HTML.");
}

async function handleLogout() {
    if (supabase) {
        await supabase.auth.signOut();
    }
    setLoggedInState(false);
    localStorage.removeItem('helpon_user_name');
    window.location.href = 'index.html';
}

// Legacy function stub - this throws an error to catch places we haven't migrated yet
async function fetchWithAuth(url, options = {}) {
    console.error("fetchWithAuth is deprecated! You must use the 'supabase' client object to query the database.");
    throw new Error("Please migrate this API call to Supabase.");
}
