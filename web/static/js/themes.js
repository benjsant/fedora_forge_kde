// themes.js — catalogue de themes (GTK/icones/curseurs/Kvantum) : onglets,
// filtre "masquer installes", installation depuis git (opt-in).

let _themeCatalog = {};
let _currentThemeTab = 'gtk';

function reloadAllThemes() {
    showToast('Rechargement des themes...', 'info');
    loadThemeCatalog();
    loadKdeOptions();
}

function loadThemeCatalog() {
    document.getElementById('themeCatalogGrid').innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
    api('/api/themes/catalog')
        .then(data => {
            if (!data.success) return;
            _themeCatalog = data.catalog;
            renderThemeTab(_currentThemeTab);
        })
        .catch(() => {
            document.getElementById('themeCatalogGrid').innerHTML = '<div style="color: var(--danger);">Erreur chargement catalogue</div>';
        });
}

function switchThemeTab(type) {
    _currentThemeTab = type;
    ['gtk', 'icon', 'cursor', 'kvantum'].forEach(t => {
        const btn = document.getElementById('themeTab' + t.charAt(0).toUpperCase() + t.slice(1));
        if (btn) btn.style.borderColor = (t === type) ? 'var(--primary)' : '';
    });
    renderThemeTab(type);
}

function renderThemeTab(type) {
    const grid = document.getElementById('themeCatalogGrid');
    const hideInstalled = document.getElementById('themeHideInstalled')?.checked;
    let themes = (_themeCatalog[type] || []);
    if (hideInstalled) themes = themes.filter(t => !t.installed);
    if (!themes.length) {
        grid.innerHTML = '<div style="color: var(--text-muted);">' + (hideInstalled ? 'Tous les themes de ce catalogue sont deja installes.' : 'Aucun theme dans ce catalogue.') + '</div>';
        return;
    }
    grid.innerHTML = '';
    themes.forEach(t => {
        const card = document.createElement('div');
        card.style.cssText = 'background: var(--card-bg); border-radius: 12px; padding: 16px; box-shadow: var(--card-shadow); display: flex; flex-direction: column; gap: 8px;';
        const statusColor = t.installed ? 'var(--success)' : 'var(--text-muted)';
        const statusLabel = t.installed ? 'Installe' : 'Non installe';
        const canInstall  = t.has_url && !t.installed;
        card.innerHTML = `
            <div style="font-weight: 600; font-size: 0.95em; color: var(--dark);">${esc(t.name)}</div>
            <div style="font-size: 0.82em; color: var(--text-muted);">${esc(t.description)}</div>
            <div style="font-size: 0.8em; color: ${statusColor}; font-weight: 500;">${statusLabel}</div>
            ${canInstall
                ? `<button class="btn-small" style="margin-top: auto;" onclick="installTheme('${type}', '${esc(t.name)}', this)">
                       Installer → /usr/share
                   </button>`
                : `<button class="btn-small" style="margin-top: auto; opacity: 0.4; cursor: not-allowed;" disabled>${t.installed ? 'Deja installe' : 'Inclus systeme'}</button>`
            }
        `;
        grid.appendChild(card);
    });
}

function installTheme(type, name, btn) {
    if (isTaskRunning) { showToast('Une tache est en cours', 'warning'); return; }
    const system = document.getElementById('themeSystemInstall')?.checked || false;
    _themeInstallPending = true;
    btn.disabled = true;
    btn.textContent = system ? 'Install. systeme...' : 'Installation...';
    api('/api/themes/install', { body: {type, name, system} })
        .then(data => {
            if (data.success) {
                showToast('Installation de "' + name + '" lancee', 'success');
                addLog('Theme : installation de ' + name + ' lancee');
            } else {
                _themeInstallPending = false;
                showToast('Erreur : ' + data.error, 'error');
                btn.disabled = false;
                btn.textContent = 'Installer';
            }
        })
        .catch(err => { _themeInstallPending = false; showToast('Erreur reseau : ' + err, 'error'); btn.disabled = false; btn.textContent = 'Installer'; });
}
