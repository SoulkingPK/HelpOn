/**
 * HelpOn Auth Module v4.0
 * Centralizes Supabase initialization and robust authentication state logic.
 * Key fix: Use supabase.auth.getSession() as the source of truth, not localStorage.
 */

let _supabaseClient = null;

/**
 * Lazy getter for the Supabase Client.
 */
export function getSupabase() {
    if (_supabaseClient) return _supabaseClient;

    const lib = window.supabase;
    if (!lib || typeof lib.createClient !== 'function') {
        console.warn('[HelpOn] Supabase library not loaded yet.');
        return null;
    }

    const url = window.SUPABASE_URL || (window.CONFIG && window.CONFIG.SUPABASE_URL);
    const key = window.SUPABASE_ANON_KEY || (window.CONFIG && window.CONFIG.SUPABASE_ANON_KEY);

    if (!url || !key) {
        console.warn('[HelpOn] Supabase config missing.');
        return null;
    }

    try {
        _supabaseClient = lib.createClient(url, key);
        console.log('[HelpOn] Supabase client initialized (v4.0).');
        return _supabaseClient;
    } catch (err) {
        console.error('[HelpOn] Supabase init failed:', err);
        return null;
    }
}

/**
 * Get the current authenticated user from Supabase directly.
 * This is the ONLY reliable source of truth after OAuth.
 */
export async function getCurrentUser() {
    const client = getSupabase();
    if (!client) return null;
    const { data: { user } } = await client.auth.getUser();
    return user;
}

/**
 * Get current session — works after OAuth redirect with hash token.
 */
export async function getSession() {
    const client = getSupabase();
    if (!client) return null;
    const { data: { session } } = await client.auth.getSession();
    return session;
}

/**
 * isUserLoggedIn — checks ONLY the URL hash for OAuth tokens.
 * For actual session check, use checkSession() which is async.
 * This sync version is used as a fast pre-check only.
 */
export function isUserLoggedIn() {
    const hash = window.location.hash || '';
    if (hash.match(/access_token=|error_code=|type=recovery|type=signup/)) {
        console.log('[HelpOn] Auth hash detected.');
        return true;
    }
    return localStorage.getItem('helpon_logged_in') === 'true';
}

/**
 * ASYNC session check — the proper way to verify auth state.
 * Returns true if there is a valid Supabase session.
 */
export async function checkSession() {
    // First check hash (fast path for OAuth redirects)
    const hash = window.location.hash || '';
    if (hash.match(/access_token=|type=recovery|type=signup/)) {
        console.log('[HelpOn] Hash token detected, session incoming...');
        return true;
    }

    // Then check actual Supabase session
    const session = await getSession();
    if (session) {
        // Keep localStorage in sync
        localStorage.setItem('helpon_logged_in', 'true');
        if (session.user?.user_metadata?.full_name) {
            localStorage.setItem('helpon_user_name', session.user.user_metadata.full_name);
        }
        return true;
    }

    // No session found
    localStorage.removeItem('helpon_logged_in');
    return false;
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

// Legacy compat
export const supabase = getSupabase();

// Global hook
window.helponAuth = { getSupabase, isUserLoggedIn, checkSession, logout, setLoggedInState };
