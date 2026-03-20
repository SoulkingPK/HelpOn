// Global configuration for the HelpOn frontend
const CONFIG = {
    // Current deployed Vercel backend URL
    API_BASE_URL: 'https://help-on.vercel.app/api',
    // WebSocket URL
    WS_BASE_URL: 'wss://help-on.vercel.app/api/ws'
    // Local testing URL (uncomment when testing locally)
    // API_BASE_URL: 'http://localhost:8000/api',
    // WS_BASE_URL: 'ws://localhost:8000/api/ws'
};

// Helper to get a cookie value
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

// --- Authentication Utilities ---

async function fetchWithAuth(url, options = {}) {
    options.credentials = 'include'; // Ensure cookies are sent

    // Add default headers if not provided
    if (!options.headers) {
        options.headers = {};
    }

    // Add CSRF token from cookie if available
    const csrfToken = getCookie('helpon_csrf_token');
    if (csrfToken) {
        options.headers['X-CSRF-Token'] = csrfToken;
    }

    // If we're not uploading a file (FormData), set Content-Type to application/json
    if (!(options.body instanceof FormData) && !options.headers['Content-Type']) {
        options.headers['Content-Type'] = 'application/json';
    }

    try {
        let response = await fetch(url, options);

        // If the token is expired (401), try to refresh it
        if (response.status === 401) {
            console.log('Access token expired, attempting to refresh...');
            const refreshResponse = await fetch(`${CONFIG.API_BASE_URL}/refresh`, {
                method: 'POST',
                credentials: 'include' // Send refresh token cookie
            });

            if (refreshResponse.ok) {
                // Refresh successful, cookies have been updated. Retry original request.
                console.log('Refresh successful, retrying request...');
                response = await fetch(url, options);
            } else {
                // Refresh failed, user needs to log in again
                console.error('Refresh failed, logging out...');
                handleAuthFailure();
                return response;
            }
        }
        return response;
    } catch (error) {
        console.error('Network error during fetchWithAuth:', error);
        throw error;
    }
}

function handleAuthFailure() {
    // Clear any residual localStorage tokens just in case
    localStorage.removeItem('helpon_token');
    localStorage.removeItem('helpon_refresh_token');

    // Call the logout endpoint to clear cookies
    fetch(`${CONFIG.API_BASE_URL}/logout`, { method: 'POST', credentials: 'include' })
        .finally(() => {
            if (window.location.pathname.indexOf('index.html') === -1 &&
                window.location.pathname.indexOf('register.html') === -1) {
                window.location.href = 'index.html';
            }
        });
}

// Helper to check if user is nominally logged in (client-side prediction)
// relies on a flag since httpOnly cookies can't be read by JS
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
