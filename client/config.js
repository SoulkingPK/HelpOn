// Global configuration for the HelpOn frontend using Supabase
window.CONFIG = {
    SUPABASE_URL: 'https://yatmmbytwhpngzofiukt.supabase.co',
    SUPABASE_ANON_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlhdG1tYnl0d2hwbmd6b2ZpdWt0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwODc2MjgsImV4cCI6MjA4OTY2MzYyOH0.aPm4Bk-302CVfacQPkfdyABhB0-EvL4q5hFQiDnfP34',
    API_BASE_URL: '/api'
};

// Also set separate window globals for maximum reliability
window.SUPABASE_URL = window.CONFIG.SUPABASE_URL;
window.SUPABASE_ANON_KEY = window.CONFIG.SUPABASE_ANON_KEY;

// Synchronous login checker utilizing local storage token check
window.isUserLoggedIn = function() {
    const projectRef = 'yatmmbytwhpngzofiukt';
    const tokenKey = `sb-${projectRef}-auth-token`;
    return localStorage.getItem(tokenKey) !== null;
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

