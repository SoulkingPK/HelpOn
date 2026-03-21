// Global configuration for the HelpOn frontend using Supabase
const CONFIG = {
    // IMPORTANT: Replace these with your actual Supabase URL and Anon Key
    SUPABASE_URL: 'https://yatmmbytwhpngzofiukt.supabase.co',
    SUPABASE_ANON_KEY: 'sb_publishable_FVyDTtHsL5-CBALTP3BarA_iMr6nMEv'
};

// Initialize Supabase Client
// Note: This requires the Supabase JS script to be loaded in the HTML file:
// <script src="js/supabase-sdk.js"></script>
let supabase;
try {
    if (window.supabase && typeof window.supabase.createClient === 'function') {
        // Use a local variable for the library to avoid collision with our intended global 'supabase'
        const supabaseLib = window.supabase;
        supabase = supabaseLib.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY);
        // Expose the initialized client globally for all other scripts
        window.supabase = supabase;
        console.log("Supabase client initialized successfully.");
    } else if (window.supabase && window.supabase.auth) {
        // Already initialized? Just use it
        supabase = window.supabase;
        console.log("Supabase client already initialized.");
    } else {
        console.error("Supabase SDK not found or incorrectly loaded.");
    }
} catch (e) {
    console.error("Error initializing Supabase:", e);
}


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
