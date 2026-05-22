// Designer copy of frontend JS. This is a duplicate of the runtime frontend.
// Edit this file for UI experiments. Keep logic in sync with the app's frontend/js/app.js when needed.

console.log('UI workspace: designer copy of app.js');

// Small helper to show that the file is loaded
document.addEventListener('DOMContentLoaded', () => {
    const el = document.createElement('div');
    el.style.padding = '12px';
    el.style.background = '#f3f4f6';
    el.style.border = '1px dashed #ccc';
    el.style.margin = '12px';
    el.textContent = 'UI workspace loaded — edit ui/js/app.js for design changes.';
    document.body.insertBefore(el, document.body.firstChild);
});
