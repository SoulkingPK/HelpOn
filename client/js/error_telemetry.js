/**
 * HelpOn Error Telemetry
 * Captures and logs client-side errors to Supabase for debugging
 */
import { supabase, getCurrentUser } from './auth.js';

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

    console.info("HelpOn Telemetry: Initialized");
}

async function logErrorToSupabase(errorData) {
    try {
        const user = await getCurrentUser();
        const payload = {
            ...errorData,
            user_id: user ? user.id : null,
            url: window.location.href,
            user_agent: navigator.userAgent,
            created_at: new Date().toISOString()
        };

        // We use a silent background call to avoid interfering with UI
        const { error } = await supabase
            .from('error_logs')
            .insert([payload]);

        if (error) {
            // If logging itself fails, we just log to console to avoid infinite loops
            console.warn("Telemetry: Failed to upload log", error);
        }
    } catch (err) {
        console.error("Telemetry: Critical failure", err);
    }
}
