// kde.js — parametres KDE (themes, polices, veille, Wayland/gaming), mode
// sombre, apercu des modifications, sauvegardes de config KDE, ecran de
// connexion (plasma-login-manager / SDDM).

let kdeCurrent = {};

function loadKdeOptions() {
    api('/api/kde/options')
        .then(data => {
            if (!data.success) return;
            kdeCurrent = data.current;
            const grid = document.getElementById('kdeGrid');
            grid.innerHTML = '';

            const isDark = data.current.color_scheme === 'BreezeDark';
            grid.innerHTML += `
                <div class="dconf-group">
                    <h3>Mode couleur</h3>
                    <p style="font-size:0.8em; color:var(--text-muted); margin-bottom:10px;">
                        Bascule le schema de couleurs KDE, theme Plasma et parametres associes.
                    </p>
                    <div style="display:flex; gap:8px;">
                        <button class="btn-small" id="btnLightMode"
                            style="${!isDark ? 'border-color:var(--primary);color:var(--primary);' : ''}"
                            onclick="applyDarkMode(false)">
                            Clair (Breeze)
                        </button>
                        <button class="btn-small" id="btnDarkMode"
                            style="${isDark ? 'border-color:var(--primary);color:var(--primary);' : ''}"
                            onclick="applyDarkMode(true)">
                            Sombre (Breeze Dark)
                        </button>
                    </div>
                </div>
            `;

            const themeFields = [
                {id: 'gtk_theme', label: 'Theme GTK', options: data.themes.gtk, current: data.current.gtk_theme},
                {id: 'icon_theme', label: 'Theme Icones', options: data.themes.icon, current: data.current.icon_theme},
                {id: 'cursor_theme', label: 'Theme Curseur', options: data.themes.cursor, current: data.current.cursor_theme},
                {id: 'plasma_theme', label: 'Theme Plasma', options: data.themes.plasma || [], current: data.current.plasma_theme},
            ];
            if ((data.themes.kvantum || []).length > 0) {
                themeFields.push({id: 'kvantum_theme', label: 'Theme Kvantum (Qt)', options: data.themes.kvantum, current: data.current.kvantum_theme});
            }
            grid.innerHTML += buildSelectGroup('Themes', themeFields);

            // Wayland / Gaming : VRR + DRM Leasing (Plasma 6+)
            const vrrCurrent = data.current.vrr_policy || '1';
            grid.innerHTML += `
                <div class="dconf-group">
                    <h3>Wayland / Gaming</h3>
                    <p style="font-size:0.8em; color:var(--text-muted); margin-bottom:10px;">
                        VRR (FreeSync/G-Sync) et DRM Leasing pour la VR/headsets. Necessite Wayland (defaut Fedora KDE).
                    </p>
                    <div class="dconf-field">
                        <label>VRR (Variable Refresh Rate)</label>
                        <select id="kde_vrr_policy">
                            <option value="0" ${vrrCurrent === '0' ? 'selected' : ''}>Jamais</option>
                            <option value="1" ${vrrCurrent === '1' ? 'selected' : ''}>Auto (sur les jeux plein ecran)</option>
                            <option value="2" ${vrrCurrent === '2' ? 'selected' : ''}>Toujours</option>
                        </select>
                    </div>
                    ${buildToggle('kde_drm_lease', 'DRM Leasing (VR / casques)', data.current.drm_lease === 'true')}
                </div>
            `;

            grid.innerHTML += `
                <div class="dconf-group">
                    <h3>Polices et Bureau</h3>
                    <div class="dconf-field">
                        <label>Police principale</label>
                        <input type="text" id="kde_font_name" value="${esc(data.current.font_name || 'Noto Sans,10')}">
                    </div>
                    <div class="dconf-field">
                        <label>Police a chasse fixe</label>
                        <input type="text" id="kde_fixed_font" value="${esc(data.current.fixed_font || 'Hack,10')}">
                    </div>
                    <div class="dconf-field">
                        <label>Nombre d'espaces de travail</label>
                        <input type="number" id="kde_num_workspaces" min="1" max="12" value="${data.current.num_workspaces || 2}">
                    </div>
                </div>
            `;

            grid.innerHTML += `
                <div class="dconf-group">
                    <h3>Parametres systeme</h3>
                    ${buildToggle('kde_night_color', 'Veilleuse (Night Color)', data.current.night_color_active === 'true')}
                    <div class="dconf-field">
                        <label>Temperature veilleuse (K)</label>
                        <input type="number" id="kde_night_color_temp" min="1700" max="6500" step="100"
                               value="${data.current.night_color_temp || 4500}">
                    </div>
                    ${buildToggle('kde_event_sounds', 'Sons systeme', data.current.event_sounds !== 'false')}
                    ${buildToggle('kde_show_hidden', 'Afficher fichiers caches (Dolphin)', data.current.show_hidden_files === 'true')}
                </div>
            `;

            grid.innerHTML += `
                <div class="dconf-group">
                    <h3>Veille et ecran</h3>
                    <div class="dconf-field">
                        <label>Delai extinction ecran (s, 0 = jamais)</label>
                        <input type="number" id="kde_dpms_timeout" min="0" step="60"
                               value="${data.current.dpms_timeout || 0}">
                    </div>
                    ${buildToggle('kde_lock_enabled', 'Verrouillage ecran', data.current.lock_enabled !== 'false')}
                    <div class="dconf-field">
                        <label>Delai verrouillage (s)</label>
                        <input type="number" id="kde_lock_timeout" min="0" step="60"
                               value="${data.current.lock_timeout || 300}">
                    </div>
                </div>
            `;

            grid.querySelectorAll('select, input').forEach(el => {
                el.addEventListener('change', updateKdePreview);
                el.addEventListener('input', updateKdePreview);
            });
        })
        .catch(err => console.error('KDE options error:', err));
}

function buildSelectGroup(title, fields) {
    let html = '<div class="dconf-group"><h3>' + title + '</h3>';
    fields.forEach(f => {
        html += '<div class="dconf-field"><label>' + f.label + '</label>';
        html += '<select id="kde_' + f.id + '">';
        f.options.forEach(opt => {
            html += '<option value="' + esc(opt) + '"' + (opt === f.current ? ' selected' : '') + '>' + opt + '</option>';
        });
        html += '</select></div>';
    });
    return html + '</div>';
}

function buildToggle(id, label, checked) {
    return `
        <div class="dconf-toggle">
            <label>${label}</label>
            <div class="toggle-switch">
                <input type="checkbox" id="${id}" ${checked ? 'checked' : ''}>
                <span class="slider" onclick="this.previousElementSibling.click(); updateKdePreview();"></span>
            </div>
        </div>
    `;
}

function getKdeSettings() {
    const val = (id) => { const el = document.getElementById(id); return el ? el.value : ''; };
    const chk = (id) => { const el = document.getElementById(id); return el ? el.checked : false; };
    const s = {
        gtk_theme: val('kde_gtk_theme'),
        icon_theme: val('kde_icon_theme'),
        cursor_theme: val('kde_cursor_theme'),
        plasma_theme: val('kde_plasma_theme'),
        font_name: val('kde_font_name'),
        fixed_font: val('kde_fixed_font'),
        num_workspaces: val('kde_num_workspaces'),
        night_color_active: chk('kde_night_color'),
        night_color_temp: val('kde_night_color_temp'),
        event_sounds: chk('kde_event_sounds'),
        show_hidden_files: chk('kde_show_hidden'),
        dpms_timeout: val('kde_dpms_timeout'),
        lock_enabled: chk('kde_lock_enabled'),
        lock_timeout: val('kde_lock_timeout'),
        vrr_policy: val('kde_vrr_policy'),
        drm_lease: chk('kde_drm_lease'),
    };
    // Kvantum optionnel : present uniquement si themes installes
    const kv = document.getElementById('kde_kvantum_theme');
    if (kv) s.kvantum_theme = kv.value;
    return s;
}

function updateKdePreview() {
    const s = getKdeSettings();
    const changes = [];

    const strFields = [
        ['gtk_theme', 'theme-gtk'], ['icon_theme', 'icones'],
        ['cursor_theme', 'curseur'], ['plasma_theme', 'theme-plasma'],
        ['font_name', 'police'], ['fixed_font', 'police-fixe'],
    ];
    strFields.forEach(([key, label]) => {
        if (s[key] !== kdeCurrent[key]) changes.push(label + ' = ' + s[key]);
    });
    if (s.num_workspaces !== (kdeCurrent.num_workspaces || '2')) changes.push('workspaces = ' + s.num_workspaces);

    const numFields = [
        ['dpms_timeout', 'extinction-ecran'], ['lock_timeout', 'delai-verrouillage'],
        ['night_color_temp', 'temperature-veilleuse'],
    ];
    numFields.forEach(([key, label]) => {
        if (s[key] !== (kdeCurrent[key] || '0')) changes.push(label + ' = ' + s[key]);
    });

    const boolFields = [
        ['night_color_active', 'veilleuse'], ['lock_enabled', 'verrouillage'],
        ['event_sounds', 'sons-systeme'], ['show_hidden_files', 'fichiers-caches'],
    ];
    boolFields.forEach(([key, label]) => {
        if (s[key] !== (kdeCurrent[key] === 'true')) changes.push(label + ' = ' + s[key]);
    });

    const wrap = document.getElementById('kdePreviewWrap');
    const pre = document.getElementById('kdePreview');
    if (changes.length) {
        wrap.style.display = 'block';
        pre.textContent = changes.length + ' modification(s):\n\n' + changes.join('\n');
    } else {
        wrap.style.display = 'none';
    }
}

function applyDarkMode(dark) {
    if (isTaskRunning) return showToast('Une tache est deja en cours', 'warning');
    const label = dark ? 'sombre' : 'clair';
    api('/api/kde/dark-mode', { body: {dark} })
        .then(data => {
            if (data.success) {
                showToast('Mode ' + label + ' applique', 'success');
                addLog('Mode ' + label + ' : ColorScheme=' + (data.color_scheme || ''));
                document.getElementById('btnLightMode').style.borderColor = dark ? '' : 'var(--primary)';
                document.getElementById('btnLightMode').style.color = dark ? '' : 'var(--primary)';
                document.getElementById('btnDarkMode').style.borderColor = dark ? 'var(--primary)' : '';
                document.getElementById('btnDarkMode').style.color = dark ? 'var(--primary)' : '';
                setTimeout(() => loadKdeOptions(), 800);
            } else {
                showToast('Erreur mode ' + label, 'error');
            }
        })
        .catch(err => showToast('Erreur reseau : ' + err, 'error'));
}

function applyKde() {
    if (isTaskRunning) return showToast('Une tache est deja en cours', 'warning');
    showConfirm(
        'Appliquer la config KDE ?',
        'Les themes et parametres du bureau seront modifies immediatement.',
        _doApplyKde
    );
}
function _doApplyKde() {
    api('/api/kde/apply', { body: {settings: getKdeSettings()} })
        .then(data => {
            if (data.success) {
                addLog('Config KDE lancee');
                const poll = setInterval(() => {
                    if (!isTaskRunning) {
                        clearInterval(poll);
                        loadKdeOptions();
                        showToast('Config KDE appliquee', 'success');
                    }
                }, 1000);
            }
            else showToast('Erreur: ' + data.error, 'error');
        })
        .catch(err => showToast('Erreur reseau: ' + err, 'error'));
}

function exportCurrentKde() { window.open('/api/kde/export', '_blank'); }

// =============================================
// SAUVEGARDES CONFIG KDE
// =============================================
function _formatBackupDate(ts) {
    // "YYYYMMDD-HHMMSS" -> "DD/MM/YYYY HH:MM:SS"
    const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/.exec(ts || '');
    return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}:${m[6]}` : '?';
}

function _formatSize(bytes) {
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' Ko';
    return (bytes / (1024 * 1024)).toFixed(2) + ' Mo';
}

function loadKdeBackups() {
    const list = document.getElementById('kdeBackupsList');
    if (!list) return;
    list.innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
    api('/api/kde/backups')
        .then(data => {
            if (!data.success) {
                list.innerHTML = '<div style="color: var(--danger);">Erreur : ' + esc(data.error || '') + '</div>';
                return;
            }
            if (!data.backups || data.backups.length === 0) {
                list.innerHTML = '<div style="color: var(--text-muted);">Aucune sauvegarde pour l\'instant.</div>';
                return;
            }
            list.innerHTML = data.backups.map(b => {
                const date = _formatBackupDate(b.timestamp);
                const size = _formatSize(b.size);
                const labelTag = b.label
                    ? `<span style="background: rgba(155,89,182,0.15); color: var(--primary); padding: 2px 8px; border-radius: 6px; font-size: 0.78em; font-weight: 600; margin-left: 8px;">${esc(b.label)}</span>`
                    : '';
                return `<div style="background: var(--light); border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 220px;">
                        <div style="font-weight: 600; color: var(--dark);">${date}${labelTag}</div>
                        <div style="font-size: 0.78em; color: var(--text-muted); margin-top: 2px;">${size} — ${esc(b.filename)}</div>
                    </div>
                    <button class="btn-small" onclick="restoreKdeBackup('${esc(b.filename)}')"
                            style="border-color: var(--primary); color: var(--primary);">Restaurer</button>
                    <button class="btn-small" onclick="deleteKdeBackup('${esc(b.filename)}')"
                            style="border-color: var(--danger); color: var(--danger);">Supprimer</button>
                </div>`;
            }).join('');
        })
        .catch(() => {
            list.innerHTML = '<div style="color: var(--danger);">Erreur reseau.</div>';
        });
}

function createKdeBackup() {
    const labelInput = document.getElementById('backupLabel');
    const label = labelInput ? labelInput.value.trim() : '';
    api('/api/kde/backups/create', { body: {label} })
        .then(data => {
            if (data.success) {
                showToast(`Sauvegarde creee (${data.backup.files_count} fichiers)`, 'success');
                if (labelInput) labelInput.value = '';
                loadKdeBackups();
            } else {
                showToast(data.error || 'Erreur', 'error');
            }
        })
        .catch(() => showToast('Erreur reseau', 'error'));
}

function restoreKdeBackup(filename) {
    showConfirm(
        'Restaurer la sauvegarde',
        `Les fichiers de config KDE actuels seront ecrases par "${filename}". Une re-connexion ou redemarrage peut etre necessaire pour que tous les changements soient visibles. Continuer ?`,
        () => {
            api('/api/kde/backups/restore', { body: {filename} })
                .then(data => {
                    if (data.success) {
                        showToast(`Restauration : ${data.count} fichier(s) restaure(s)`, 'success');
                        loadKdeOptions();
                    } else {
                        showToast(data.error || 'Erreur', 'error');
                    }
                })
                .catch(() => showToast('Erreur reseau', 'error'));
        },
        true
    );
}

function deleteKdeBackup(filename) {
    showConfirm(
        'Supprimer la sauvegarde',
        `Supprimer definitivement "${filename}" ? Cette action est irreversible.`,
        () => {
            api('/api/kde/backups/delete', { body: {filename} })
                .then(data => {
                    if (data.success) {
                        showToast('Sauvegarde supprimee', 'success');
                        loadKdeBackups();
                    } else {
                        showToast(data.error || 'Erreur', 'error');
                    }
                })
                .catch(() => showToast('Erreur reseau', 'error'));
        },
        true
    );
}

// =============================================
// Ecran de connexion (plasma-login-manager / SDDM)
// =============================================
function loadSddmStatus() {
    api('/api/sddm/status')
        .then(data => {
            const el = document.getElementById('sddmStatus');
            if (!data.success) {
                const msg = data.warning || data.error || 'plasma-login-manager non actif.';
                el.innerHTML = `<span style="color: var(--warning);"><b>Attention</b> : ${esc(msg)}</span>`;
                return;
            }
            const c = data.current || {};
            const lines = [
                ['Theme',    c['theme']],
                ['Curseur',  c['cursor_theme']],
                ['Numlock',  c['numlock']],
            ];
            el.innerHTML = lines
                .filter(([, v]) => v)
                .map(([k, v]) => `<span style="margin-right:18px;"><b>${k}</b> : ${esc(v)}</span>`)
                .join('') || 'Aucune configuration detectee (fichier vide ou absent)';
        })
        .catch(() => { document.getElementById('sddmStatus').textContent = 'Erreur reseau'; });
}

function sddmSync() {
    showConfirm(
        'Synchroniser l\'ecran de connexion ?',
        'Le theme, curseur et numlock seront appliques a plasma-login-manager.',
        () => {
            api('/api/sddm/sync', { method: 'POST' })
                .then(data => {
                    if (data.applied && data.applied.length > 0) {
                        showToast('plasma-login synchronise (' + data.applied.length + ' parametres)', 'success');
                        addLog('plasma-login : ' + data.applied.join(', '));
                    }
                    if (data.warnings && data.warnings.length > 0) {
                        data.warnings.forEach(w => {
                            showToast(w, 'warning');
                            addLog('[WARN] plasma-login : ' + w);
                        });
                    }
                    if (data.errors && data.errors.length > 0) {
                        showToast('Echecs plasma-login : ' + data.errors.join(', '), 'error');
                    }
                    loadSddmStatus();
                })
                .catch(err => showToast('Erreur reseau : ' + err, 'error'));
        }
    );
}
