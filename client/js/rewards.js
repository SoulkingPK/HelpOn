/**
 * HelpOn Rewards Module
 * Manages HelpPoints and user achievements
 */

const POINTS_KEY = 'helpon_user_points';
const HELPS_KEY = 'helpon_helps_count';
const HISTORY_KEY = 'helpon_points_history';

export function loadUserPoints() {
    const raw = localStorage.getItem(POINTS_KEY);
    if (raw === null) {
        localStorage.setItem(POINTS_KEY, '0');
        return 0;
    }
    const points = parseInt(raw, 10);
    return Number.isFinite(points) ? points : 0;
}

export function saveUserPoints(points) {
    const safePoints = Math.max(0, Math.floor(points));
    localStorage.setItem(POINTS_KEY, String(safePoints));
    return safePoints;
}

export function loadHelpsCount() {
    const raw = localStorage.getItem(HELPS_KEY);
    if (raw === null) {
        localStorage.setItem(HELPS_KEY, '0');
        return 0;
    }
    const helps = parseInt(raw, 10);
    return Number.isFinite(helps) ? helps : 0;
}

export function saveHelpsCount(count) {
    const safeCount = Math.max(0, Math.floor(count));
    localStorage.setItem(HELPS_KEY, String(safeCount));
    return safeCount;
}

export function incrementHelpsCount() {
    const current = loadHelpsCount();
    return saveHelpsCount(current + 1);
}

export function appendPointsHistory(points, description) {
    if (!points) return;
    let history = [];
    try {
        history = JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
    } catch (e) {
        history = [];
    }
    history.unshift({
        type: 'earned',
        description,
        points,
        date: new Date().toISOString()
    });
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 50)));
}

export function awardPoints(pointsToAdd, reason = 'Emergency completed') {
    const currentPoints = loadUserPoints();
    const newTotal = saveUserPoints(currentPoints + pointsToAdd);
    if (pointsToAdd > 0) {
        appendPointsHistory(pointsToAdd, reason);
    }
    return newTotal;
}
