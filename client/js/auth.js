/**
 * HelpOn Auth Module
 * Centralizes Supabase initialization and authentication state logic
 */

// Initialize Supabase client safely
const getSupabaseClient = () => {
    // 1. Check if Supabase library is loaded
    const lib = window.supabase;
    if (!lib || typeof lib.createClient !== 'function') {
        console.error('[HelpOn] Supabase CDN not loaded yet or wrong version.');
        return null;
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

export function isUserLoggedIn() {
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

