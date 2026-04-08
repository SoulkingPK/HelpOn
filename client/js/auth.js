/**
 * HelpOn Auth Module
 * Centralizes Supabase initialization and authentication state logic
 */

// Initialize Supabase client safely
const getSupabaseClient = () => {
    // 1. Check if Supabase library is loaded
    const lib = window.supabase;
    if (!lib || (typeof lib.createClient !== 'function' && !lib.auth)) {
        console.error('[HelpOn] Supabase CDN not loaded yet or wrong version.');
        return null;
    }

    // If window.supabase is already an instance (has .auth), return it!
    if (lib.auth && typeof lib.from === 'function') {
        return lib;
    }

    // 2. Check if configuration is loaded
    const config = window.CONFIG;
    if (!config || !config.SUPABASE_URL || !config.SUPABASE_ANON_KEY) {
        console.error('[HelpOn] Configuration (config.js) not loaded or missing keys.');
        return null;
    }

    try {
        const client = lib.createClient(config.SUPABASE_URL, config.SUPABASE_ANON_KEY);
        console.log('[HelpOn] Supabase client initialized via module.');
        return client;
    } catch (err) {
        console.error('[HelpOn] Failed to create Supabase client:', err);
        return null;
    }
};

export const supabase = getSupabaseClient();

// --- Auth State Helpers ---
export async function getCurrentUser() {
    if (!supabase) return null;
    const { data: { user } } = await supabase.auth.getUser();
    return user;
}

/**
 * Check if the user is nominally logged in.
 * CRITICAL: We also return true if returning from an OAuth flow (Google)
 * or a Password Recovery flow to prevent premature redirection.
 */
export function isUserLoggedIn() {
    const hash = window.location.hash || '';
    if (hash.includes('access_token=') || hash.includes('type=recovery') || hash.includes('type=signup')) {
        return true;
    }
    return localStorage.getItem('helpon_logged_in') === 'true';
}

export function setLoggedInState(isLoggedIn) {
    if (isLoggedIn) {
        localStorage.setItem('helpon_logged_in', 'true');
    } else {
        localStorage.removeItem('helpon_logged_in');
        localStorage.removeItem('helpon_user_name');
    }
}

export async function handleAuthFailure() {
    setLoggedInState(false);
    if (supabase) await supabase.auth.signOut();
    window.location.href = 'index.html';
}

export async function logout() {
    if (supabase) await supabase.auth.signOut();
    setLoggedInState(false);
    window.location.href = 'index.html';
}

// Global exposure for non-module scripts if needed
if (supabase) {
    window.supabase = supabase;
}
window.isUserLoggedIn = isUserLoggedIn;
window.handleAuthFailure = handleAuthFailure;


