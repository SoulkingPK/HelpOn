/**
 * HelpOn Auth Module
 * Centralizes Supabase initialization and authentication state logic
 */

let supabaseInstance = null;

// Initialize Supabase client safely
const getSupabase = () => {
    // Return existing instance if available
    if (supabaseInstance) return supabaseInstance;

    // 1. Check if Supabase library is loaded
    const lib = window.supabase;
    if (!lib || (typeof lib.createClient !== 'function' && !lib.auth)) {
        console.error('[HelpOn] Supabase library (window.supabase) not found.');
        return null;
    }

    // If window.supabase is actually an instance (already initialized elsewhere), use it
    if (lib.auth && typeof lib.from === 'function') {
        supabaseInstance = lib;
        return supabaseInstance;
    }

    // 2. Check if configuration is loaded from config.js
    const url = window.SUPABASE_URL || (window.CONFIG && window.CONFIG.SUPABASE_URL);
    const key = window.SUPABASE_ANON_KEY || (window.CONFIG && window.CONFIG.SUPABASE_ANON_KEY);

    if (!url || !key) {
        console.error('[HelpOn] Configuration (config.js) not found or missing keys.');
        return null;
    }

    try {
        supabaseInstance = lib.createClient(url, key);
        console.log('[HelpOn] Supabase client initialized via auth module.');
        return supabaseInstance;
    } catch (err) {
        console.error('[HelpOn] Exception during createClient:', err);
        return null;
    }
};

// Exported client (lazy getter)
export const supabase = getSupabase();

// --- Auth State Helpers ---
export async function getCurrentUser() {
    const client = getSupabase();
    if (!client) return null;
    const { data: { user } } = await client.auth.getUser();
    return user;
}

/**
 * Check if the user is nominally logged in.
 * CRITICAL: We return true if an OAuth token is in the hash to prevent redirect loop.
 */
export function isUserLoggedIn() {
    const hash = window.location.hash || '';
    const hasToken = hash.includes('access_token=') || 
                     hash.includes('type=recovery') || 
                     hash.includes('type=signup') ||
                     hash.includes('error_code=');
    
    if (hasToken) {
        console.log('[HelpOn] OAuth/Sign-up hash detected, suppressing redirect.');
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

// Global exposure for non-module scripts (using a dedicated name)
window.helponAuth = { 
    getSupabase, 
    isUserLoggedIn, 
    logout, 
    setLoggedInState 
};



