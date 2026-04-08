/**
 * HelpOn Auth Module
 * Centralizes Supabase initialization and authentication state logic
 */

// Initialize Supabase client
const supabaseUrl = window.SUPABASE_URL; // From config.js
const supabaseKey = window.SUPABASE_ANON_KEY; 

export const supabase = window.supabase.createClient(supabaseUrl, supabaseKey);

// --- Auth State Helpers ---
export async function getCurrentUser() {
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
    await supabase.auth.signOut();
    window.location.href = 'index.html';
}

export async function logout() {
    await supabase.auth.signOut();
    setLoggedInState(false);
    window.location.href = 'index.html';
}

// Global exposure for non-module scripts if needed
window.supabase = supabase;
window.isUserLoggedIn = isUserLoggedIn;
window.handleAuthFailure = handleAuthFailure;
