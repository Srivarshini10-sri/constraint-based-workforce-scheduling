// Main client-side script for Workforce Scheduling System
document.addEventListener('DOMContentLoaded', () => {
    console.log('Workforce Scheduling & Workload Optimization System loaded.');

    // Auto-dismiss alert messages after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});
