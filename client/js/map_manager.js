/**
 * HelpOn Map Manager Module
 * Refined MapManager class using ES Modules
 */
import { getSupabase, getCurrentUser } from './auth.js';
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
    loadLastAlertTimestamp,
    escapeHtml
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
        this.currentSettings = { 
            health: true, 
            danger: true, 
            fire: true, 
            helpers: true, 
            satellite: false,
            hospital: true,
            police: true,
            fireStation: true,
            pharmacy: true
        };
        this.rawEmergencies = [];
        this.supabase = getSupabase();
        
        // UI Callbacks
        this.onEmergencyAlert = options.onEmergencyAlert || (() => {});
        this.onToast = options.onToast || ((m, t) => console.log(`[${t}] ${m}`));
        this.onEmergencyListUpdate = options.onEmergencyListUpdate || (() => {});

        this.init();
    }

    async init() {
        await this.initMap();
        this.initRealtime();
        this.startLocationTracking();
    }

    initRealtime() {
        if (!this.supabase) return;
        this.supabaseChannel = this.supabase
            .channel('map-updates')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'emergencies' }, () => {
                this.fetchEmergencies();
            })
            .on('postgres_changes', { event: '*', schema: 'public', table: 'profiles' }, () => {
                this.fetchActiveUsers();
            })
            .subscribe();

        window.addEventListener('beforeunload', () => {
            if (this.supabaseChannel) {
                this.supabase.removeChannel(this.supabaseChannel);
            }
        });
    }

    async initMap() {
        const savedLocation = loadSavedLocation();
        let initialLat = DEFAULT_LOCATION.lat;
        let initialLon = DEFAULT_LOCATION.lon;
        let hasCoords = false;

        if (savedLocation) {
            initialLat = savedLocation.lat;
            initialLon = savedLocation.lon;
            hasCoords = true;
        } else {
            // Try fetching from database profile
            try {
                const user = await getCurrentUser();
                if (user && this.supabase) {
                    const { data: profile, error } = await this.supabase
                        .from('profiles')
                        .select('latitude, longitude')
                        .eq('id', user.id)
                        .maybeSingle();

                    if (!error && profile && profile.latitude !== null && profile.longitude !== null) {
                        initialLat = parseFloat(profile.latitude);
                        initialLon = parseFloat(profile.longitude);
                        saveLocation(initialLat, initialLon);
                        hasCoords = true;
                        console.log('[MapManager] Loaded user location from database profile.');
                    }
                }
            } catch (e) {
                console.warn('[MapManager] Failed to fetch coordinates from DB profile.', e);
            }
        }

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
        this.fetchNearbyServices(initialLat, initialLon);

        if (navigator.geolocation && (!hasCoords || !isLocationFresh(savedLocation))) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude: lat, longitude: lon } = position.coords;
                    
                    const distance = getDistanceKm(this.currentLocation.lat, this.currentLocation.lon, lat, lon);
                    if (!hasCoords || distance > 0.1) {
                        saveLocation(lat, lon);
                        this.currentLocation = { lat, lon };
                        this.map.setView([lat, lon], 14);
                        this.setUserMarker(lat, lon);
                        this.fetchEmergencies();
                        this.fetchNearbyServices(lat, lon);
                        this.sendLocationUpdate(lat, lon);
                    }
                },
                () => this.onToast('Location access denied.', 'warning'),
                { enableHighAccuracy: true, timeout: 5000 }
            );
        }
    }

    async sendLocationUpdate(lat, lon) {
        try {
            const user = await getCurrentUser();
            if (!user || !this.supabase) return;
            await this.supabase.from('profiles').update({
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
            if (!this.supabase) return;
            const { data: users, error } = await this.supabase
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
                                .bindPopup(`<b>${escapeHtml(u.full_name)}${isVerified ? ' <i class="bi bi-patch-check-fill text-primary"></i>' : ''}</b><br><small>Ready to Help</small>`);
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
                    const source = localStorage.getItem('user_location_source');
                    if (source === 'manual') {
                        // Do not overwrite manual search location in the background
                        return;
                    }
                    const { latitude: lat, longitude: lon } = position.coords;
                    const distanceMoved = getDistanceKm(this.currentLocation.lat, this.currentLocation.lon, lat, lon);

                    this.currentLocation = { lat, lon };
                    this.setUserMarker(lat, lon);
                    saveLocation(lat, lon);

                    if (distanceMoved > 0.5) {
                        this.fetchNearbyServices(lat, lon);
                    }

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
            if (!this.supabase) return;
            // Fetch both 'active' and 'accepted' so helpers can see in-progress SOS
            const { data: emergencies, error } = await this.supabase
                .from('emergencies')
                .select('*')
                .in('status', ['active', 'accepted']);
            
            if (error) throw error;
            this.rawEmergencies = emergencies || [];
            this.renderEmergenciesWithFilter();
        } catch (err) {
            console.error("Core: Emergency fetch failed", err);
        }
    }

    renderEmergenciesWithFilter() {
        if (!this.rawEmergencies) return;
        this.emergencyMarkers.clearLayers();

        const now = Date.now();
        const filtered = this.rawEmergencies.filter(e => {
            const createdTime = new Date(e.created_at).getTime();
            if (now - createdTime > EMERGENCY_TTL_MS) return false;
            const distance = getDistanceKm(this.currentLocation.lat, this.currentLocation.lon, e.latitude, e.longitude);
            if (distance > MAX_EMERGENCY_DISTANCE_KM) return false;

            // Apply type filters
            const normalizedType = (e.type || '').toLowerCase();
            if (this.currentSettings) {
                if (normalizedType.includes('health') || normalizedType.includes('medical')) {
                    return this.currentSettings.health;
                }
                if (normalizedType.includes('danger') || normalizedType.includes('safety')) {
                    return this.currentSettings.danger;
                }
                if (normalizedType.includes('fire')) {
                    return this.currentSettings.fire;
                }
            }
            return true;
        });

        this.onEmergencyListUpdate(filtered);

        filtered.forEach(e => {
            if (!this.alertedEmergencies.has(e.id)) {
                if (!this.initialFetch) this.onEmergencyAlert(e);
                this.alertedEmergencies.add(e.id);
            }

            const severity = e.severity || 'medium';
            const severityClass = severity === 'high' ? 'bg-danger text-white' : (severity === 'low' ? 'bg-info text-dark' : 'bg-warning text-dark');
            const severityText = severity.toUpperCase();

            const popupContent = `
                <div style="min-width: 180px; padding: 2px;">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <h6 class="fw-bold mb-0 text-danger" style="font-size: 14px;">${escapeHtml(e.type)}</h6>
                        <span class="badge ${severityClass}" style="font-size: 9px; padding: 3px 6px;">${escapeHtml(severityText)}</span>
                    </div>
                    <p class="small text-muted mb-2" style="font-size: 12px; line-height: 1.3;">${escapeHtml(e.description)}</p>
                    ${e.image_url ? `
                    <div class="text-center mb-2">
                        <img src="${escapeHtml(e.image_url)}" class="img-thumbnail" style="max-height: 80px; max-width: 100%; border-radius: 6px;" alt="SOS attachment">
                    </div>` : ''}
                    <div class="d-flex flex-column gap-1">
                        <a href="chat.html?user=${escapeHtml(e.user_id)}&emergency=${escapeHtml(e.id)}" class="btn btn-sm btn-outline-primary py-1 fw-bold text-decoration-none text-center"><i class="bi bi-chat-dots-fill me-1"></i>Chat Seeker</a>
                        <button class="btn btn-sm btn-success py-1 fw-bold text-white" onclick="window.mapManager?.acceptEmergency('${escapeHtml(e.id)}')">Accept SOS</button>
                    </div>
                </div>
            `;
            const marker = L.marker([e.latitude, e.longitude], { icon: this.getEmergencyIcon(e.type) })
                            .bindPopup(popupContent);
            this.emergencyMarkers.addLayer(marker);
        });

        this.initialFetch = false;
        saveAlertedSOS(this.alertedEmergencies);
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
            // NOTE: Points are awarded by the database trigger award_points_on_resolve.
            // Do NOT call awardPoints() here — doing so would double-credit the user.
            this.onToast('Emergency Resolved! +20 Points awarded by server.', 'success');
            this.fetchEmergencies();
        } else {
            this.onToast(error.message, 'danger');
        }
    }

    locateMe() {
        if (navigator.geolocation) {
            this.onToast('Locating your device via GPS...', 'info');
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude: lat, longitude: lon } = position.coords;
                    this.currentLocation = { lat, lon };
                    saveLocation(lat, lon);
                    localStorage.setItem('user_location_source', 'gps'); // Re-enable GPS updates in background
                    
                    if (this.map) {
                        this.map.setView([lat, lon], 14);
                        this.setUserMarker(lat, lon);
                        this.fetchEmergencies();
                        this.fetchNearbyServices(lat, lon);
                        this.sendLocationUpdate(lat, lon);
                    }
                    this.onToast('Location updated via GPS.', 'success');
                },
                (err) => {
                    console.warn('[GPS] locateMe failed:', err);
                    this.onToast('Could not retrieve GPS location. Showing last known location.', 'warning');
                    // Fallback: just center on last known location
                    if (this.currentLocation && this.map) {
                        this.map.setView([this.currentLocation.lat, this.currentLocation.lon], 14);
                        if (this.userMarker) this.userMarker.openPopup();
                    }
                },
                { enableHighAccuracy: true, timeout: 8000 }
            );
        } else {
            this.onToast('Geolocation is not supported by your browser.', 'danger');
        }
    }

    applyFilters(settings) {
        this.currentSettings = settings;
        if (this.map) {
            if (settings.helpers) {
                this.map.addLayer(this.activeUserMarkers);
            } else {
                this.map.removeLayer(this.activeUserMarkers);
            }

            // Toggle service layer groups
            const serviceMapping = {
                hospital: this.serviceClusters.hospital,
                police: this.serviceClusters.police,
                fireStation: this.serviceClusters.fire,
                pharmacy: this.serviceClusters.pharmacy
            };
            Object.entries(serviceMapping).forEach(([settingKey, clusterGroup]) => {
                if (settings[settingKey]) {
                    this.map.addLayer(clusterGroup);
                } else {
                    this.map.removeLayer(clusterGroup);
                }
            });
        }
        this.renderEmergenciesWithFilter();
    }

    updateUserLocation(lat, lon) {
        this.currentLocation = { lat, lon };
        saveLocation(lat, lon);
        localStorage.setItem('user_location_source', 'manual');
        this.setUserMarker(lat, lon);
        this.sendLocationUpdate(lat, lon);
        this.fetchEmergencies();
        this.fetchNearbyServices(lat, lon);
    }

    async fetchNearbyServices(lat, lon) {
        const query = `
            [out:json][timeout:25];
            (
              node["amenity"~"hospital|clinic|doctors|police|fire_station|pharmacy"](around:5000,${lat},${lon});
              way["amenity"~"hospital|clinic|doctors|police|fire_station|pharmacy"](around:5000,${lat},${lon});
            );
            out center;
        `;
        const url = `https://overpass-api.de/api/interpreter?data=${encodeURIComponent(query)}`;

        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Overpass response was not ok');
            const data = await response.json();
            
            // Clear existing service cluster layers
            Object.values(this.serviceClusters).forEach(group => group.clearLayers());

            (data.elements || []).forEach(element => {
                const elementLat = element.lat || (element.center && element.center.lat);
                const elementLon = element.lon || (element.center && element.center.lon);
                if (!elementLat || !elementLon) return;

                const amenity = element.tags.amenity;
                const name = element.tags.name || this.getServiceDefaultName(amenity);
                
                // Construct better address from tags
                const street = element.tags['addr:street'] || '';
                const house = element.tags['addr:housenumber'] || '';
                const city = element.tags['addr:city'] || '';
                const addressParts = [house, street, city].filter(Boolean);
                const address = addressParts.length > 0 ? addressParts.join(', ') : 'Address not available';

                let category = 'pharmacy';
                if (['hospital', 'clinic', 'doctors'].includes(amenity)) category = 'hospital';
                else if (amenity === 'police') category = 'police';
                else if (amenity === 'fire_station') category = 'fire';

                // Phone logic
                const phone = element.tags.phone || element.tags['contact:phone'] || '';
                const fallbackPhone = this.getFallbackEmergencyPhone(amenity);
                const dialPhone = phone || fallbackPhone;

                const phoneButtonHtml = dialPhone 
                    ? `<a href="tel:${encodeURIComponent(dialPhone)}" class="btn btn-sm btn-success w-100 mb-1 fw-bold text-white"><i class="bi bi-telephone-fill me-1"></i> Call ${phone ? escapeHtml(phone) : ('Emergency (' + escapeHtml(dialPhone) + ')')}</a>`
                    : '';

                const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${elementLat},${elementLon}`;
                const directionsButtonHtml = `<a href="${directionsUrl}" target="_blank" class="btn btn-sm btn-primary w-100 fw-bold text-white"><i class="bi bi-geo-alt-fill me-1"></i> Get Directions</a>`;

                const popupContent = `
                    <div style="min-width:200px; padding:2px;">
                        <h6 class="fw-bold mb-1" style="color:#1e293b; font-size:14px; margin-bottom: 4px;">${escapeHtml(name)}</h6>
                        <span class="badge bg-${this.getServiceBadgeClass(category)} mb-2" style="font-size:10px; padding:4px 8px; text-transform:uppercase;">${escapeHtml(category === 'fire' ? 'fire station' : category)}</span>
                        <p class="small text-muted mb-3" style="font-size:12px; line-height:1.3; margin-top: 6px;"><i class="bi bi-geo-alt me-1"></i>${escapeHtml(address)}</p>
                        <div class="d-flex flex-column gap-1">
                            ${phoneButtonHtml}
                            ${directionsButtonHtml}
                        </div>
                    </div>
                `;

                const marker = L.marker([elementLat, elementLon], { icon: this.getServiceIcon(category) })
                    .bindPopup(popupContent);
                
                if (this.serviceClusters[category]) {
                    this.serviceClusters[category].addLayer(marker);
                }
            });

            // Re-apply filters to show newly added layers if they are enabled
            this.applyFilters(this.currentSettings);
        } catch (err) {
            console.error('Error fetching nearby services:', err);
            this.onToast('Could not fetch nearby emergency services.', 'warning');
        }
    }

    getFallbackEmergencyPhone(amenity) {
        if (['hospital', 'clinic', 'doctors'].includes(amenity)) return '102'; // Ambulance (India fallback)
        if (amenity === 'police') return '100'; // Police (India fallback)
        if (amenity === 'fire_station') return '101'; // Fire Service
        return '';
    }

    getServiceBadgeClass(category) {
        if (category === 'hospital') return 'danger';
        if (category === 'police') return 'primary';
        if (category === 'fire') return 'warning text-dark';
        if (category === 'pharmacy') return 'success';
        return 'secondary';
    }

    getServiceIcon(category) {
        let color = '#2563eb', icon = 'bi-building-fill';
        if (category === 'hospital') { color = '#dc2626'; icon = 'bi-hospital-fill'; }
        else if (category === 'police') { color = '#1e3a8a'; icon = 'bi-shield-fill-check'; }
        else if (category === 'fire') { color = '#f97316'; icon = 'bi-fire'; }
        else if (category === 'pharmacy') { color = '#059669'; icon = 'bi-capsule'; }

        const html = `<div style="background:${color}; width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; border:2px solid white; box-shadow:0 3px 8px rgba(0,0,0,0.3);"><i class="bi ${icon}" style="font-size:12px;"></i></div>`;
        return L.divIcon({ className: '', html, iconSize: [28, 28], iconAnchor: [14, 14] });
    }

    getServiceDefaultName(amenity) {
        if (['hospital', 'clinic', 'doctors'].includes(amenity)) return 'Medical Clinic / Hospital';
        if (amenity === 'police') return 'Police Station';
        if (amenity === 'fire_station') return 'Fire Station';
        if (amenity === 'pharmacy') return 'Pharmacy';
        return 'Emergency Service';
    }
}
