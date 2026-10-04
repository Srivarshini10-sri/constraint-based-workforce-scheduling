// Main client-side script for Workforce Scheduling System
document.addEventListener('DOMContentLoaded', () => {
    // 1. Auto-dismiss alert messages
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 6000);
    });

    // 2. Client-side employee filtering
    const searchInput = document.getElementById('empSearchInput');
    const roleFilter = document.getElementById('empRoleFilter');
    const employeeRows = document.querySelectorAll('.employee-row');

    function filterEmployees() {
        if (!employeeRows.length) return;
        const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
        const role = (roleFilter ? roleFilter.value : '').toLowerCase().trim();

        employeeRows.forEach(row => {
            const name = (row.getAttribute('data-name') || '').toLowerCase();
            const code = (row.getAttribute('data-code') || '').toLowerCase();
            const empRole = (row.getAttribute('data-role') || '').toLowerCase();
            const skills = (row.getAttribute('data-skills') || '').toLowerCase();

            const matchesQuery = !query || name.includes(query) || code.includes(query) || skills.includes(query);
            const matchesRole = !role || empRole === role;

            if (matchesQuery && matchesRole) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }

    if (searchInput) searchInput.addEventListener('input', filterEmployees);
    if (roleFilter) roleFilter.addEventListener('change', filterEmployees);
});

// Quick availability presets for employee form
function applyAvailabilityPreset(preset) {
    for (let day = 0; day < 7; day++) {
        const availCheck = document.getElementById(`avail_check_${day}`);
        const startInput = document.getElementById(`avail_start_${day}`);
        const endInput = document.getElementById(`avail_end_${day}`);

        if (!availCheck || !startInput || !endInput) continue;

        if (preset === 'standard_weekdays') {
            // Monday-Friday available 08:00 - 17:00, Saturday-Sunday unavailable
            if (day <= 4) {
                availCheck.checked = true;
                startInput.value = '08:00';
                endInput.value = '17:00';
            } else {
                availCheck.checked = false;
                startInput.value = '00:00';
                endInput.value = '00:00';
            }
        } else if (preset === 'open_all_week') {
            // 7 days open 24/7 (00:00 - 23:59)
            availCheck.checked = true;
            startInput.value = '00:00';
            endInput.value = '23:59';
        } else if (preset === 'shifts_all_week') {
            // 7 days open 07:00 - 23:00
            availCheck.checked = true;
            startInput.value = '07:00';
            endInput.value = '23:00';
        } else if (preset === 'clear_all') {
            // All unavailable
            availCheck.checked = false;
            startInput.value = '08:00';
            endInput.value = '17:00';
        }
        toggleAvailabilityRow(day);
    }
}

function toggleAvailabilityRow(day) {
    const availCheck = document.getElementById(`avail_check_${day}`);
    const startInput = document.getElementById(`avail_start_${day}`);
    const endInput = document.getElementById(`avail_end_${day}`);
    if (!availCheck || !startInput || !endInput) return;

    if (availCheck.checked) {
        startInput.disabled = false;
        endInput.disabled = false;
    } else {
        startInput.disabled = true;
        endInput.disabled = true;
    }
}
