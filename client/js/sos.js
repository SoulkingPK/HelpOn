/**
 * HelpOn SOS Module
 * Handles creation, acceptance, and resolution of emergency requests
 *
 * FIX: Previously imported `supabase` as a static value from auth.js,
 * which was undefined at module parse time (race condition).
 * Now uses getSupabase() lazily inside each function.
 */
import { getSupabase, getCurrentUser } from './auth.js';
import { getDistanceKm, MAX_EMERGENCY_DISTANCE_KM } from './utils.js';

export async function createEmergency(type, description, lat, lon) {
    try {
        const client = getSupabase();
        if (!client) throw new Error('Supabase not initialized');

        const user = await getCurrentUser();
        if (!user) throw new Error('You must be logged in to send an SOS.');

        // Ensure profile row exists to satisfy FK constraint on emergencies.user_id
        const fullName = localStorage.getItem('helpon_user_name') || 'User';
        await client.from('profiles').upsert([{
            id: user.id,
            email: user.email,
            full_name: fullName
        }], { onConflict: 'id' });

        const { data, error } = await client
            .from('emergencies')
            .insert([{
                user_id: user.id,
                type,
                description,
                latitude: lat,
                longitude: lon,
                status: 'active',
                created_at: new Date().toISOString()
            }])
            .select();

        if (error) throw error;
        return { data: data[0], error: null };
    } catch (err) {
        console.error('SOS Creation Failed:', err);
        return { data: null, error: err };
    }
}

export async function acceptEmergency(id) {
    try {
        const client = getSupabase();
        if (!client) throw new Error('Supabase not initialized');

        const user = await getCurrentUser();
        if (!user) throw new Error('Login required');

        const { error } = await client
            .from('emergencies')
            .update({
                status: 'accepted',
                helper_id: user.id
            })
            .eq('id', id);

        if (error) throw error;
        return { error: null };
    } catch (err) {
        return { error: err };
    }
}

export async function resolveEmergency(id) {
    try {
        const client = getSupabase();
        if (!client) throw new Error('Supabase not initialized');

        const { error } = await client
            .from('emergencies')
            .update({
                status: 'resolved',
                resolved_at: new Date().toISOString()
            })
            .eq('id', id);

        if (error) throw error;
        return { error: null };
    } catch (err) {
        return { error: err };
    }
}

/**
 * Filter emergencies by distance and status
 */
export function filterEmergencies(emergencies, userLat, userLon) {
    return (emergencies || [])
        .map(e => ({
            ...e,
            lat: Number.parseFloat(e.latitude),
            lon: Number.parseFloat(e.longitude)
        }))
        .filter(e => {
            if (!Number.isFinite(e.lat) || !Number.isFinite(e.lon)) return false;
            const distance = getDistanceKm(userLat, userLon, e.lat, e.lon);
            return distance <= MAX_EMERGENCY_DISTANCE_KM;
        });
}
