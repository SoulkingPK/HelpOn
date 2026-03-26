// --- Shared Utilities ---

// Toast notification function
window.showToast = function (message, type = 'info') {
    // Remove existing toasts
    const existingToasts = document.querySelectorAll('.custom-toast');
    existingToasts.forEach(toast => toast.remove());

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `custom-toast position-fixed top-0 start-50 translate-middle-x mt-3 p-3 rounded shadow-sm border-0 text-white`;
    toast.style.zIndex = '9999';

    // Set background color based on type
    if (type === 'success') {
        toast.classList.add('bg-success');
    } else if (type === 'error') {
        toast.classList.add('bg-danger');
    } else if (type === 'warning') {
        toast.classList.add('bg-warning', 'text-dark');
        toast.classList.remove('text-white');
    } else {
        toast.classList.add('bg-primary');
    }

    // Set content and icon
    let icon = 'bi-info-circle';
    if (type === 'success') icon = 'bi-check-circle';
    if (type === 'error') icon = 'bi-exclamation-circle';
    if (type === 'warning') icon = 'bi-exclamation-triangle';

    toast.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="bi ${icon} fs-4 me-2"></i>
            <div>${message}</div>
        </div>
    `;

    document.body.appendChild(toast);

    // Auto remove after 3 seconds
    setTimeout(() => {
        toast.style.transition = 'opacity 0.5s ease';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 500);
    }, 3000);
};

// Service worker registration
window.registerServiceWorker = function () {
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            // Need relative or absolute depending on scope, assume root
            const swPath = window.location.pathname.includes('/client/')
                ? 'service-worker.js'
                : '/service-worker.js';
            navigator.serviceWorker.register(swPath)
                .catch(function (e) { console.warn("SW registration failed:", e); });
        });
    }
};

// Initialize common features on load
document.addEventListener('DOMContentLoaded', () => {
    window.registerServiceWorker();

    // Auto-setup logout buttons where they exist, preventing duplicate binding if possible
    const logoutBtns = document.querySelectorAll('#logoutBtn, #modalLogoutBtn');
    logoutBtns.forEach(btn => {
        // Prevent duplicate attaching by checking a dataset flag
        if (btn.dataset.logoutBound) return;
        btn.dataset.logoutBound = "true";

        btn.addEventListener('click', async function (e) {
            e.preventDefault();
            if (typeof window.hasUnsavedChanges !== 'undefined' && window.hasUnsavedChanges) {
                if (!confirm('You have unsaved changes. Are you sure you want to logout?')) {
                    return;
                }
            }
            if (typeof handleLogout === 'function') {
                await handleLogout();
            } else {
                if (typeof setLoggedInState === 'function') setLoggedInState(false);
                localStorage.removeItem('helpon_user_name');
                window.location.href = 'index.html';
            }
        });
    });
});

// Dark Mode Manager
class DarkModeManager {
    constructor() {
        this.isDarkMode = localStorage.getItem('darkMode') === 'true';
        this.init();
    }

    init() {
        // Apply saved mode on page load
        this.applyDarkMode(this.isDarkMode);

        // Set toggle state
        const darkModeToggle = document.getElementById('darkModeToggle');
        if (darkModeToggle) {
            darkModeToggle.checked = this.isDarkMode;
        }
    }

    applyDarkMode(enable) {
        const body = document.body;
        const html = document.documentElement;

        if (enable) {
            body.classList.add('dark-mode');
            html.setAttribute('data-bs-theme', 'dark');
        } else {
            body.classList.remove('dark-mode');
            html.setAttribute('data-bs-theme', 'light');
        }

        this.isDarkMode = enable;
        localStorage.setItem('darkMode', enable);
    }

    toggle() {
        this.applyDarkMode(!this.isDarkMode);
        return this.isDarkMode;
    }
}
