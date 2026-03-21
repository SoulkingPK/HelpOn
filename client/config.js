// Global configuration for the HelpOn frontend using Supabase
const CONFIG = {
    // IMPORTANT: Replace these with your actual Supabase URL and Anon Key
    SUPABASE_URL: 'https://yatmmbytwhpngzofiukt.supabase.co',
    SUPABASE_ANON_KEY: 'sb_publishable_FVyDTtHsL5-CBALTP3BarA_iMr6nMEv'
};

// Initialize Supabase Client
let supabase;
try {
    // Proactive validation: help the user catch if they used a Stripe key by mistake
    if (CONFIG.SUPABASE_ANON_KEY.startsWith('sb_')) {
        console.error("CRITICAL ERROR: Your SUPABASE_ANON_KEY looks like a STRIPE key! This will not work with Supabase.");
        alert("CRITICAL ERROR: Your SUPABASE_ANON_KEY looks like a STRIPE key! \n\nPlease get the 'anon (public)' key from your Supabase Dashboard -> Project Settings -> API.");
    }

    if (window.supabase && typeof window.supabase.createClient === 'function') {
        const supabaseLib = window.supabase;
        supabase = supabaseLib.createClient(CONFIG.SUPABASE_URL, CONFIG.SUPABASE_ANON_KEY);
        window.supabase = supabase;
        
        if (!supabase.auth) {
            console.error("Supabase Auth failed to initialize. This is usually due to an invalid Anon Key.");
        } else {
            console.log("Supabase client initialized successfully.");
        }
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
