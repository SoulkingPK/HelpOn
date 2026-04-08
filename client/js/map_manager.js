/**
 * HelpOn Map Manager Module
 * Refined MapManager class using ES Modules
 */
import { supabase, getCurrentUser } from './auth.js';
import { 
    DEFAULT_LOCATION, 
    MAX_EMERGENCY_DISTANCE_KM, 
    EMERGENCY_TTL_MS,
    saveLocation,
    loadSavedLocation,
    isLocationFresh,
    getDistanceKm,
    formatDistance,
    loadAlertedSOS,
    saveAlertedSOS,
    loadLastAlertTimestamp
} from './utils.js';
import { acceptEmergency, resolveEmergency } from './sos.js';
import { awardPoints } from './rewards.js';

export class MapManager {
    constructor(options = {}) {
        this.containerId = options.containerId || 'leafletMap';
        this.map = null;
        this.userMarker = null;
        this.emergencyMarkers = L.layerGroup();
        this.activeUserMarkers = L.layerGroup();
        this.serviceClusters = {
            hospital: L.markerClusterGroup({ chunkedLoading: true }),
            police: L.markerClusterGroup({ chunkedLoading: true }),
            fire: L.markerClusterGroup({ chunkedLoading: true }),
            pharmacy: L.markerClusterGroup({ chunkedLoading: true })
        };
        this.currentLocation = { lat: DEFAULT_LOCATION.lat, lon: DEFAULT_LOCATION.lon };
        this.alertedEmergencies = loadAlertedSOS();
        this.lastAlertTimestamp = loadLastAlertTimestamp();
        this.initialFetch = true;
        this.isFilterVisible = false;
        
        // UI Callbacks
        this.onEmergencyAlert = options.onEmergencyAlert || (() => {});
        this.onToast = options.onToast || ((m, t) => console.log(`[${t}] ${m}`));
        this.onEmergencyListUpdate = options.onEmergencyListUpdate || (() => {});

        this.init();
    }

    async init() {
        this.initMap();
        this.initRealtime();
        this.startLocationTracking();
    }

    initRealtime() {
        this.supabaseChannel = supabase
            .channel('map-updates')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'emergencies' }, () => {
                this.fetchEmergencies();
            })
            .on('postgres_changes', { event: '*', schema: 'public', table: 'profiles' }, () => {
                this.fetchActiveUsers();
            })
            .subscribe();
    }

    initMap() {
        const savedLocation = loadSavedLocation();
        const initialLat = savedLocation ? savedLocation.lat : DEFAULT_LOCATION.lat;
        const initialLon = savedLocation ? savedLocation.lon : DEFAULT_LOCATION.lon;

        this.map = L.map(this.containerId, {
            zoomControl: false 
        }).setView([initialLat, initialLon], 13);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(this.map);

        this.map.addLayer(this.emergencyMarkers);
        this.map.addLayer(this.activeUserMarkers);

        this.currentLocation = { lat: initialLat, lon: initialLon };
        this.setUserMarker(initialLat, initialLon);
        this.fetchEmergencies();

        if (navigator.geolocation && (!savedLocation || !isLocationFresh(savedLocation))) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude: lat, longitude: lon } = position.coords;
                    saveLocation(lat, lon);
                    this.currentLocation = { lat, lon };
                    this.map.setView([lat, lon], 14);
                    this.setUserMarker(lat, lon);
                    this.fetchEmergencies();
                },
                () => this.onToast('Location access denied.', 'warning'),
                { enableHighAccuracy: true, timeout: 5000 }
            );
        }
    }

    async sendLocationUpdate(lat, lon) {
        try {
            const user = await getCurrentUser();
            if (!user) return;
            await supabase.from('profiles').update({
                latitude: lat,
                longitude: lon,
                last_active: new Date().toISOString()
            }).eq('id', user.id);
        } catch (err) {
            console.error('Core: Location sync failed', err);
        }
    }

    async fetchActiveUsers() {
        try {
            const { data: users, error } = await supabase
                .from('profiles')
                .select('id, full_name, latitude, longitude, kyc_status, verified')
                .not('latitude', 'is', null)
                .gt('last_active', new Date(Date.now() - 10 * 60000).toISOString());

            if (error) throw error;
            this.activeUserMarkers.clearLayers();
            
            (users || []).forEach(u => {
                // Don't show self as a helper marker
                if (Math.abs(u.latitude - this.currentLocation.lat) < 0.0001 && 
                    Math.abs(u.longitude - this.currentLocation.lon) < 0.0001) return;

                const isVerified = u.verified || u.kyc_status === 'approved';
                const verifiedBadge = isVerified ? `<div style="position:absolute; top:-5px; right:-5px; background:white; border-radius:50%; width:12px; height:12px; display:flex; align-items:center; justify-content:center;"><i class="bi bi-patch-check-fill" style="color:#2563eb; font-size:10px;"></i></div>` : '';
                
                const iconHtml = `<div style="position:relative; background-color:var(--secondary, #6c757d); width:16px; height:16px; border-radius:50%; border:2px solid white; box-shadow:0 0 4px rgba(0,0,0,0.4);">${verifiedBadge}</div>`;
                const uIcon = L.divIcon({ className: '', html: iconHtml, iconSize: [16, 16], iconAnchor: [8, 8] });
                const marker = L.marker([u.latitude, u.longitude], { icon: uIcon })
                                .bindPopup(`<b>${u.full_name}${isVerified ? ' <i class="bi bi-patch-check-fill text-primary"></i>' : ''}</b><br><small>Ready to Help</small>`);
                this.activeUserMarkers.addLayer(marker);
            });
        } catch (err) {
            console.error('Core: User fetch failed', err);
        }
    }

    startLocationTracking() {
        if (navigator.geolocation) {
            this.locationWatchId = navigator.geolocation.watchPosition(
                (position) => {
                    const { latitude: lat, longitude: lon } = position.coords;
                    this.currentLocation = { lat, lon };
                    this.setUserMarker(lat, lon);
                    saveLocation(lat, lon);

                    const now = Date.now();
                    if (!this.lastLocationUpdate || now - this.lastLocationUpdate > 30000) {
                        this.sendLocationUpdate(lat, lon);
                        this.lastLocationUpdate = now;
                    }
                },
                null,
                { enableHighAccuracy: true, maximumAge: 10000, timeout: 5000 }
            );
            this.fetchActiveUsers();
        }
    }

    setUserMarker(lat, lon) {
        const userIconHtml = `<div style="background-color:#0d6efd; width:20px; height:20px; border-radius:50%; border:3px solid white; box-shadow:0 0 6px rgba(0,0,0,0.6);"></div>`;
        const userIcon = L.divIcon({ className: '', html: userIconHtml, iconSize: [20, 20], iconAnchor: [10, 10] });

        if (this.userMarker) {
            this.userMarker.setLatLng([lat, lon]);
        } else {
            this.userMarker = L.marker([lat, lon], { icon: userIcon, zIndexOffset: 1000 })
                              .addTo(this.map).bindPopup("<b>Your Location</b>");
        }
    }

    async fetchEmergencies() {
        try {
            const { data: emergencies, error } = await supabase
                .from('emergencies')
                .select('*')
                .eq('status', 'active');
            
            if (error) throw error;
            this.emergencyMarkers.clearLayers();

            const now = Date.now();
            const filtered = (emergencies || []).filter(e => {
                const createdTime = new Date(e.created_at).getTime();
                if (now - createdTime > EMERGENCY_TTL_MS) return false;
                const distance = getDistanceKm(this.currentLocation.lat, this.currentLocation.lon, e.latitude, e.longitude);
                return distance <= MAX_EMERGENCY_DISTANCE_KM;
            });

            this.onEmergencyListUpdate(filtered);

            filtered.forEach(e => {
                if (!this.alertedEmergencies.has(e.id)) {
                    if (!this.initialFetch) this.onEmergencyAlert(e);
                    this.alertedEmergencies.add(e.id);
                }

                const marker = L.marker([e.latitude, e.longitude], { icon: this.getEmergencyIcon(e.type) });
                this.emergencyMarkers.addLayer(marker);
            });

            this.initialFetch = false;
            saveAlertedSOS(this.alertedEmergencies);
        } catch (err) {
            console.error("Core: Emergency fetch failed", err);
        }
    }

    getEmergencyIcon(type) {
        // Shared logic for creating icons
        const normalized = (type || '').toLowerCase();
        let color = '#ef4444', icon = 'bi-bell-fill';
        if (normalized.includes('health')) { color = '#dc2626'; icon = 'bi-heart-pulse-fill'; }
        else if (normalized.includes('danger')) { color = '#f97316'; icon = 'bi-exclamation-triangle-fill'; }
        
        const html = `<div class="marker-pulse" style="background:${color}; width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; box-shadow:0 6px 14px rgba(15,23,42,0.25);"><i class="bi ${icon}" style="font-size:14px;"></i></div>`;
        return L.divIcon({ className: '', html, iconSize: [30, 30], iconAnchor: [15, 15] });
    }

    async acceptEmergency(id) {
        const { error } = await acceptEmergency(id);
        if (!error) {
            this.onToast('Emergency Accepted!', 'success');
            this.fetchEmergencies();
        } else {
            this.onToast(error.message, 'danger');
        }
    }

    async resolveEmergency(id) {
        const { error } = await resolveEmergency(id);
        if (!error) {
            awardPoints(20);
            this.onToast('Emergency Resolved! +20 Points', 'success');
            this.fetchEmergencies();
        } else {
            this.onToast(error.message, 'danger');
        }
    }
}
