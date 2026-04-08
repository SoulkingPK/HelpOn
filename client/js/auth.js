/**
 * HelpOn Auth Module
 * Centralizes Supabase initialization and authentication state logic
 */

let _supabaseClient = null;

/**
 * Lazy getter for the Supabase Client.
 * Ensures the library and config are loaded before initialization.
 */
export function getSupabase() {
    if (_supabaseClient) return _supabaseClient;

    const lib = window.supabase;
    if (!lib || (typeof lib.createClient !== 'function' && !lib.auth)) {
        console.warn('[HelpOn] Supabase library not found on window yet.');
        return null;
    }

    // Capture from window.supabase (library) or config.js globals
    const url = window.SUPABASE_URL || (window.CONFIG && window.CONFIG.SUPABASE_URL);
    const key = window.SUPABASE_ANON_KEY || (window.CONFIG && window.CONFIG.SUPABASE_ANON_KEY);

    if (!url || !key) {
        console.warn('[HelpOn] Supabase config not found on window yet.');
        return null;
    }

    try {
        _supabaseClient = lib.createClient(url, key);
        console.log('[HelpOn] Supabase client initialized.');
        return _supabaseClient;
    } catch (err) {
        console.error('[HelpOn] Failed to initialize Supabase:', err);
        return null;
    }
}

// Legacy export for compatibility (though getter is safer)
export const supabase = getSupabase();

export async function getCurrentUser() {
    const client = getSupabase();
    if (!client) return null;
    const { data: { user } } = await client.auth.getUser();
    return user;
}

export function isUserLoggedIn() {
    // Recognize OAuth / Signup / Recovery hashes immediately
    const hash = window.location.hash || '';
    if (hash.match(/access_token=|error_code=|type=recovery|type=signup/)) {
        console.log('[HelpOn] Auth hash detected in URL.');
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
    const client = getSupabase();
    if (client) await client.auth.signOut();
    window.location.href = 'index.html';
}

export async function logout() {
    const client = getSupabase();
    if (client) await client.auth.signOut();
    setLoggedInState(false);
    window.location.href = 'index.html';
}

// Global hook
window.helponAuth = { getSupabase, isUserLoggedIn, logout, setLoggedInState };




