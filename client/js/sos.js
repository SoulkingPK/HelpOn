/**
 * HelpOn SOS Module
 * Handles creation, acceptance, and resolution of emergency requests.
 * Includes AI Triage image uploads and client/server-side categorization.
 */
import { getSupabase, getCurrentUser } from './auth.js';
import { getDistanceKm, MAX_EMERGENCY_DISTANCE_KM } from './utils.js';

/**
 * Uploads an emergency image file to the Supabase Storage bucket 'emergency_attachments'
 */
export async function uploadEmergencyPhoto(file) {
    try {
        const client = getSupabase();
        if (!client) throw new Error('Supabase not initialized');

        const user = await getCurrentUser();
        if (!user) throw new Error('Authentication required');

        const fileName = `${user.id}/${Date.now()}_${file.name.replace(/\s+/g, '_')}`;
        
        const { data, error } = await client.storage
            .from('emergency_attachments')
            .upload(fileName, file, {
                cacheControl: '3600',
                upsert: false
            });

        if (error) throw error;

        // Retrieve public URL
        const { data: publicUrlData } = client.storage
            .from('emergency_attachments')
            .getPublicUrl(fileName);

        return publicUrlData.publicUrl;
    } catch (err) {
        console.error('[SOS Upload] Failed:', err);
        return null;
    }
}

/**
 * Creates a new emergency record in the database
 */
export async function createEmergency(type, description, lat, lon, imageUrl = null) {
    try {
        const client = getSupabase();
        if (!client) throw new Error('Supabase not initialized');

        const user = await getCurrentUser();
        if (!user) throw new Error('You must be logged in to send an SOS.');

        // Ensure profile row exists (INSERT only — never UPDATE here to avoid
        // hitting the restrict_profile_updates trigger on upsert conflicts)
        const fullName = localStorage.getItem('helpon_user_name') || 'User';
        await client.from('profiles').insert([{
            id: user.id,
            email: user.email,
            full_name: fullName
        }]).onConflict('id').ignore();

        const { data, error } = await client
            .from('emergencies')
            .insert([{
                user_id: user.id,
                type,
                description,
                latitude: lat,
                longitude: lon,
                status: 'active',
                image_url: imageUrl,
                created_at: new Date().toISOString()
            }])
            .select();

        if (error) throw error;
        
        const emergency = data[0];

        // Trigger AI triage (non-blocking async invocation)
        triggerEmergencyTriage(emergency.id, description, imageUrl);

        return { data: emergency, error: null };
    } catch (err) {
        console.error('SOS Creation Failed:', err);
        return { data: null, error: err };
    }
}

/**
 * Dispatches the emergency record to Supabase Edge Functions for triage,
 * falling back to local client-side keyword heuristics if the function is not deployed.
 */
export async function triggerEmergencyTriage(emergencyId, description, imageUrl) {
    const client = getSupabase();
    if (!client) return;

    try {
        // Try calling Supabase Edge Function
        const { data, error } = await client.functions.invoke('triage-emergency', {
            body: { emergencyId, imageUrl, description }
        });

        if (!error && data && data.success) {
            console.log('[AI Triage] Success:', data.severity);
            return;
        }
        
        if (error) console.warn('[AI Triage] Edge function unavailable, running client fallback...');
    } catch (err) {
        console.warn('[AI Triage] Local fallback trigger due to network:', err);
    }

    // Client-side local fallback simulation
    try {
        let severity = "medium";
        const text = (description || "").toLowerCase();
        
        if (
            text.includes("heart") || 
            text.includes("chest") || 
            text.includes("bleed") || 
            text.includes("fire") || 
            text.includes("unconscious") || 
            text.includes("accident") || 
            text.includes("chok") || 
            text.includes("breath") ||
            text.includes("dying")
        ) {
            severity = "high";
        } else if (
            text.includes("lost") || 
            text.includes("block") || 
            text.includes("dog") || 
            text.includes("cats") ||
            text.includes("flat tire")
        ) {
            severity = "low";
        }

        const aiAnalysis = {
            status: "simulated_client",
            notes: "Fallback keyword heuristics applied client-side."
        };

        await client
            .from('emergencies')
            .update({ severity, ai_analysis: aiAnalysis })
            .eq('id', emergencyId);

        console.log('[AI Triage] Client Fallback Complete. Classified as:', severity);
    } catch (err) {
        console.error('[AI Triage] Client Fallback update failed:', err);
    }
}

export async function acceptEmergency(id) {
    try {
        const client = getSupabase();
        if (!client) throw new Error('Supabase not initialized');

        const user = await getCurrentUser();
        if (!user) throw new Error('Login required');

        // Only accept if still 'active' — prevents race condition where two helpers
        // could simultaneously accept the same emergency.
        const { error } = await client
            .from('emergencies')
            .update({
                status: 'accepted',
                helper_id: user.id
            })
            .eq('id', id)
            .eq('status', 'active'); // Guard against double-accept

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

        const user = await getCurrentUser();
        if (!user) throw new Error('Login required');

        // Only allow the assigned helper to resolve the emergency
        const { error } = await client
            .from('emergencies')
            .update({
                status: 'resolved',
                resolved_at: new Date().toISOString()
            })
            .eq('id', id)
            .eq('helper_id', user.id); // Security: only the assigned helper can resolve

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
