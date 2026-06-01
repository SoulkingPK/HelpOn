/**
 * HelpOn Global Utilities
 * Centralizes common helper functions to reduce code duplication
 */

// --- Constants ---
export const DEFAULT_LOCATION = { lat: 20.5937, lon: 78.9629 }; // India Center
export const MAX_EMERGENCY_DISTANCE_KM = 5;
export const EMERGENCY_TTL_MS = 2 * 60 * 60 * 1000; // 2 hours

// --- Security Helpers ---

/**
 * Escapes a string for safe insertion into HTML context.
 * Must be applied to ALL values sourced from the database or user input
 * before they are set as innerHTML or interpolated into template literals.
 * @param {string|null|undefined} str
 * @returns {string}
 */
export function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Generates a cryptographically secure random alphanumeric code.
 * Uses Web Crypto API (CSPRNG) — safe for invite codes and vouchers.
 * @param {number} length - number of characters
 * @returns {string}
 */
export function generateSecureCode(length = 8) {
    // Unambiguous characters (no 0/O, 1/I/l confusion)
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const arr = new Uint8Array(length);
    crypto.getRandomValues(arr);
    return Array.from(arr).map(b => chars[b % chars.length]).join('');
}

// --- Location Helpers ---
export function saveLocation(lat, lon) {
    localStorage.setItem('user_location', JSON.stringify({
        lat,
        lon,
        timestamp: Date.now()
    }));
}

export function loadSavedLocation() {
    const saved = localStorage.getItem('user_location');
    if (!saved) return null;
    try {
        return JSON.parse(saved);
    } catch (e) {
        return null;
    }
}

export function isLocationFresh(location) {
    if (!location || !location.timestamp) return false;
    const threshold = 15 * 60 * 1000; // 15 mins
    return (Date.now() - location.timestamp) < threshold;
}

// --- Coordinate/Distance Math ---
export function toRad(value) {
    return (value * Math.PI) / 180;
}

export function getDistanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371; // Radius of the earth in km
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

export function formatDistance(km) {
    if (!Number.isFinite(km)) return 'Unknown';
    if (km < 1) return `${Math.round(km * 1000)} m`;
    return `${km.toFixed(1)} km`;
}

// --- Time Formatting ---
export function formatTimeAgo(iso) {
    if (!iso) return 'Just now';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return 'Just now';
    const diffMs = Date.now() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
}

// --- Storage Helpers (SOS Alerts) ---
export function loadAlertedSOS() {
    const saved = localStorage.getItem('alerted_sos');
    if (!saved) return new Set();
    try {
        return new Set(JSON.parse(saved));
    } catch (e) {
        return new Set();
    }
}

export function saveAlertedSOS(set) {
    localStorage.setItem('alerted_sos', JSON.stringify([...set]));
}

export function loadLastAlertTimestamp() {
    return parseInt(localStorage.getItem('last_alert_ts') || '0', 10);
}

export function saveLastAlertTimestamp(ts) {
    localStorage.setItem('last_alert_ts', ts.toString());
}

// --- Shared Map Markers & UI ---
export function buildDirectionsLink(lat, lon) {
    return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;
}
