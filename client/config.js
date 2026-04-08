// Global configuration for the HelpOn frontend using Supabase
window.CONFIG = {
    SUPABASE_URL: 'https://yatmmbytwhpngzofiukt.supabase.co',
    SUPABASE_ANON_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlhdG1tYnl0d2hwbmd6b2ZpdWt0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwODc2MjgsImV4cCI6MjA4OTY2MzYyOH0.aPm4Bk-302CVfacQPkfdyABhB0-EvL4q5hFQiDnfP34',
    API_BASE_URL: '/api'
};

// Also set separate window globals for maximum reliability
window.SUPABASE_URL = window.CONFIG.SUPABASE_URL;
window.SUPABASE_ANON_KEY = window.CONFIG.SUPABASE_ANON_KEY;

// Log for debugging
console.log('[HelpOn] Configuration loaded.');
