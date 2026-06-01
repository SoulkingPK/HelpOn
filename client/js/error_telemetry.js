/**
 * HelpOn Error Telemetry
 * Captures and logs client-side errors to Supabase for debugging
 *
 * FIX: Previously imported `supabase` as a static value from auth.js,
 * which was undefined at module parse time (race condition with UMD CDN).
 * Now uses getSupabase() lazily inside the async function.
 */
import { getSupabase, getCurrentUser } from './auth.js';

export function initTelemetry() {
    window.onerror = function(message, source, lineno, colno, error) {
        logErrorToSupabase({
            message,
            source,
            lineno,
            colno,
            stack: error ? error.stack : null,
            type: 'exception'
        });
    };

    window.onunhandledrejection = function(event) {
        logErrorToSupabase({
            message: event.reason ? event.reason.message : 'Unhandled Rejection',
            stack: event.reason ? event.reason.stack : null,
            type: 'promise_rejection'
        });
    };

    console.info('[HelpOn] Telemetry: Initialized');
}

let isUploadingLog = false;

async function logErrorToSupabase(errorData) {
    if (isUploadingLog) return;
    isUploadingLog = true;

    try {
        // FIX: Get supabase client lazily to avoid undefined at module parse time
        const client = getSupabase();
        if (!client) return; // Silently skip if Supabase isn't ready yet

        const user = await getCurrentUser();
        const payload = {
            ...errorData,
            user_id: user ? user.id : null,
            url: window.location.href,
            user_agent: navigator.userAgent,
            created_at: new Date().toISOString()
        };

        // We use a silent background call to avoid interfering with UI
        const { error } = await client
            .from('error_logs')
            .insert([payload]);

        if (error) {
            // If logging itself fails, just log to console to avoid infinite loops
            console.warn('[HelpOn] Telemetry: Failed to upload log', error);
        }
    } catch (err) {
        console.error('[HelpOn] Telemetry: Critical failure', err);
    } finally {
        // Wait 2 seconds before allowing the next log upload to avoid infinite loops
        setTimeout(() => { isUploadingLog = false; }, 2000);
    }
}
