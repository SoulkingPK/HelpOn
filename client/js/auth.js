/**
 * HelpOn Auth Module v5.0 — Clean, reliable OAuth handling
 * 
 * Strategy:
 * - Supabase JS v2 automatically handles the OAuth hash (#access_token=...)
 *   and the PKCE code (?code=...) in the URL.
 * - We just need to call getSession() and wait for it.
 * - No manual hash parsing. No localStorage as auth source of truth.
 * - localStorage is only used for non-auth UI state (name, preferences).
 */

let _client = null;

export function getSupabase() {
    if (_client) return _client;

    const lib = window.supabase;
    if (!lib || typeof lib.createClient !== 'function') {
        console.warn('[Auth] Supabase library not ready.');
        return null;
    }

    const url = window.SUPABASE_URL || (window.CONFIG && window.CONFIG.SUPABASE_URL);
    const key = window.SUPABASE_ANON_KEY || (window.CONFIG && window.CONFIG.SUPABASE_ANON_KEY);

    if (!url || !key) {
        console.warn('[Auth] Missing Supabase config.');
        return null;
    }

    _client = lib.createClient(url, key, {
        auth: {
            // Store session in localStorage automatically (default)
            persistSession: true,
            // Automatically detect and handle OAuth redirects
            detectSessionInUrl: true
        }
    });

    console.log('[Auth] Client ready (v5.0).');
    return _client;
}

/**
 * Waits for Supabase to process any pending OAuth redirect, then returns session.
 * This is the ONLY function home.html should use to check auth.
 */
export async function waitForSession(timeoutMs = 3000) {
    const client = getSupabase();
    if (!client) return null;

    // Supabase v2 with detectSessionInUrl:true automatically processes
    // the #access_token hash. We just need to poll briefly.
    const deadline = Date.now() + timeoutMs;

    while (Date.now() < deadline) {
        const { data: { session }, error } = await client.auth.getSession();
        if (error) {
            console.error('[Auth] getSession error:', error.message);
            return null;
        }
        if (session) {
            // Cache user name for UI
            if (session.user?.user_metadata?.full_name) {
                localStorage.setItem('helpon_user_name', session.user.user_metadata.full_name);
            } else if (session.user?.email) {
                localStorage.setItem('helpon_user_name', session.user.email.split('@')[0]);
            }
            // Clean up OAuth params from URL
            if (window.location.hash.includes('access_token') || window.location.search.includes('code=')) {
                history.replaceState(null, '', window.location.pathname);
            }
            return session;
        }
        await new Promise(r => setTimeout(r, 200));
    }

    return null;
}

export async function getCurrentUser() {
    const client = getSupabase();
    if (!client) return null;
    const { data: { user } } = await client.auth.getUser();
    return user;
}

export async function logout() {
    const client = getSupabase();
    if (client) await client.auth.signOut();
    localStorage.removeItem('helpon_user_name');
    window.location.href = 'index.html';
}

export async function signInWithGoogle() {
    const client = getSupabase();
    if (!client) throw new Error('Supabase not initialized');

    // Build redirect URL relative to the current page's folder
    // e.g. http://localhost:8000/client/home.html
    const base = window.location.origin + window.location.pathname.substring(0, window.location.pathname.lastIndexOf('/') + 1);
    const redirectTo = base + 'home.html';

    console.log('[Auth] OAuth redirectTo:', redirectTo);

    const { error } = await client.auth.signInWithOAuth({
        provider: 'google',
        options: {
            redirectTo,
            queryParams: { prompt: 'select_account' }
        }
    });

    if (error) throw error;
}

export async function signInWithPassword(email, password) {
    const client = getSupabase();
    if (!client) throw new Error('Supabase not initialized');
    const { data, error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data;
}

// Keep legacy exports for any other pages that import them
export { waitForSession as checkSession };
export const supabase = getSupabase();
window.helponAuth = { getSupabase, waitForSession, logout, signInWithGoogle };
