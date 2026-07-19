// tweaks.js — section Tweaks : reset Plasma, caches, services systemd, audio
// PipeWire/BT, sysctls gaming, scheduler sched-ext, barre des taches, zram,
// menu admin Dolphin, Dolphin dossier personnel.

function loadTweaks() {
    loadServices();
    loadAudioStatus();
    loadSysctls();
    loadScheduler();
    loadPanel();
    loadZram();
    loadAdminMenu();
    loadDolphin();
    loadDsTouchpad();
}

function loadDsTouchpad() {
    const ctrl = document.getElementById('dsTouchpadControls');
    if (!ctrl) return;
    api('/api/tweaks/ds-touchpad')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            const on = data.rule_installed;
            const detected = data.controller_present
                ? '<span style="font-size: 0.82em; color: var(--success);">Manette detectee : ' + esc((data.detected || []).join(', ')) + '</span>'
                : '<span style="font-size: 0.82em; color: var(--text-muted);">Aucune manette PlayStation branchee (la regle s\'appliquera au prochain branchement)</span>';
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (on ? 'var(--success)' : 'var(--text-muted)') + ';">' +
                    (on ? 'Pave tactile ignore' : 'Pave tactile actif (souris)') + '</span>' +
                  '<button class="btn-small" id="btnDsTouchpadToggle" onclick="toggleDsTouchpad(' + (on ? 'false' : 'true') + ')" ' +
                    'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
                    (on ? 'Reactiver la souris' : 'Ignorer le pave tactile') + '</button>' +
                '</div>' +
                '<div style="margin-top: 6px;">' + detected + '</div>';
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function toggleDsTouchpad(enable) {
    const btn = document.getElementById('btnDsTouchpadToggle');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/ds-touchpad/toggle', { body: { enable } })
        .then(data => {
            if (data.success) showToast(data.message || 'Pave tactile mis a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            loadDsTouchpad();
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadDsTouchpad(); });
}

function loadDolphin() {
    const ctrl = document.getElementById('dolphinControls');
    if (!ctrl) return;
    api('/api/tweaks/dolphin')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            if (!data.available) {
                ctrl.innerHTML = '<div style="font-size: 0.85em; color: var(--text-muted);">Outils KDE (kwriteconfig6) absents : indisponible.</div>';
                return;
            }
            const on = data.home_on_startup;
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (on ? 'var(--success)' : 'var(--text-muted)') + ';">' +
                    (on ? 'Ouvre le dossier personnel' : 'Memorise les onglets') + '</span>' +
                  '<button class="btn-small" id="btnDolphinToggle" onclick="toggleDolphin(' + (on ? 'false' : 'true') + ')" ' +
                    'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
                    (on ? 'Desactiver' : 'Activer') + '</button>' +
                '</div>';
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function toggleDolphin(enable) {
    const btn = document.getElementById('btnDolphinToggle');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/dolphin/home-startup', { body: { enable } })
        .then(data => {
            if (data.success) showToast(data.message || 'Dolphin mis a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            loadDolphin();
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadDolphin(); });
}

function loadPanel() {
    const ctrl = document.getElementById('panelControls');
    if (!ctrl) return;
    api('/api/tweaks/panel')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            if (!data.available) {
                ctrl.innerHTML = '<div style="font-size: 0.85em; color: var(--text-muted);">Aucun panneau Plasma detecte (ou outils KDE absents).</div>';
                return;
            }
            const floating = data.floating;
            // Bouton qui bascule vers l'etat oppose
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (floating ? 'var(--text-muted)' : 'var(--success)') + ';">' +
                    (floating ? 'Flottante' : 'Fixe') + '</span>' +
                  '<button class="btn-small" id="btnPanelToggle" onclick="togglePanel(' + (floating ? 'false' : 'true') + ')" ' +
                    'style="border-color: var(--primary); color: var(--primary);">' +
                    (floating ? 'Rendre fixe' : 'Rendre flottante') + '</button>' +
                  '<span style="font-size: 0.78em; color: var(--text-muted);">' + esc(String(data.panel_count)) + ' panneau(x)</span>' +
                '</div>';
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function togglePanel(floating) {
    const btn = document.getElementById('btnPanelToggle');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/panel/floating', { body: { floating } })
        .then(data => {
            if (data.success) showToast(data.message || 'Barre mise a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            setTimeout(loadPanel, 1500);
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadPanel(); });
}

function loadZram() {
    const ctrl = document.getElementById('zramControls');
    if (!ctrl) return;
    api('/api/tweaks/zram')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            if (!data.zram_present) {
                ctrl.innerHTML = '<div style="font-size: 0.85em; color: var(--text-muted);">Aucun device zram sur ce systeme : indisponible.</div>';
                return;
            }
            const on = data.applied;
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (on ? 'var(--success)' : 'var(--text-muted)') + ';">' +
                    (on ? 'Actif (zstd)' : 'Defaut Fedora') + '</span>' +
                  '<button class="btn-small" id="btnZramToggle" onclick="toggleZram(' + (on ? 'false' : 'true') + ')" ' +
                    'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
                    (on ? 'Desactiver' : 'Activer') + '</button>' +
                '</div>' +
                '<div style="margin-top: 8px; line-height: 1.6;">' +
                  '<code style="font-size: 0.78em; color: var(--text-muted);">algo = ' + esc(String(data.current_algo ?? '?')) + ' (cible ' + esc(data.target_algo) + ')</code><br>' +
                  '<code style="font-size: 0.78em; color: var(--text-muted);">vm.swappiness = ' + esc(String(data.current_swappiness ?? '?')) + ' (cible ' + esc(String(data.target_swappiness)) + ')</code>' +
                '</div>';
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function toggleZram(enable) {
    const btn = document.getElementById('btnZramToggle');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/zram/toggle', { body: { enable } })
        .then(data => {
            if (data.success) showToast(data.message || 'zram mis a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            loadZram();
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadZram(); });
}

function loadAdminMenu() {
    const ctrl = document.getElementById('adminMenuControls');
    if (!ctrl) return;
    api('/api/tweaks/admin-menu')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            const on = data.installed;
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (on ? 'var(--success)' : 'var(--text-muted)') + ';">' +
                    (on ? 'Installe' : 'Absent') + '</span>' +
                  '<button class="btn-small" id="btnAdminMenuToggle" onclick="toggleAdminMenu(' + (on ? 'false' : 'true') + ')" ' +
                    'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
                    (on ? 'Desactiver' : 'Activer') + '</button>' +
                '</div>';
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function toggleAdminMenu(enable) {
    const btn = document.getElementById('btnAdminMenuToggle');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/admin-menu/toggle', { body: { enable } })
        .then(data => {
            if (data.success) showToast(data.message || 'Menu administrateur mis a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            loadAdminMenu();
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadAdminMenu(); });
}

function loadScheduler() {
    const ctrl = document.getElementById('schedulerControls');
    if (!ctrl) return;
    api('/api/tweaks/scheduler')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            if (!data.kernel_supported) {
                ctrl.innerHTML = '<div style="font-size: 0.85em; color: var(--text-muted);">Le noyau courant n\'expose pas sched_ext : indisponible sur ce systeme.</div>';
                return;
            }
            const on = data.active;
            const scheds = data.schedulers || {};
            const opts = Object.keys(scheds).map(s =>
                `<option value="${esc(s)}" ${s === (data.active_scheduler || data.default) ? 'selected' : ''}>${esc(s)} - ${esc(scheds[s])}</option>`
            ).join('');
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (on ? 'var(--success)' : 'var(--text-muted)') + ';">' +
                    (on ? 'Actif : ' + esc(data.active_scheduler || '') : 'Inactif') + '</span>' +
                  '<select id="schedulerSelect" ' + (on ? 'disabled' : '') + ' style="padding: 5px 8px; border-radius: 6px; max-width: 340px;">' + opts + '</select>' +
                  '<button class="btn-small" id="btnSchedulerToggle" onclick="toggleScheduler(' + (on ? 'false' : 'true') + ')" ' +
                    'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
                    (on ? 'Desactiver' : 'Activer') + '</button>' +
                '</div>' +
                (data.scx_installed ? '' : '<div style="margin-top: 6px; font-size: 0.78em; color: var(--text-muted);">Le paquet scx-scheds sera installe a la premiere activation.</div>');
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function toggleScheduler(enable) {
    const btn = document.getElementById('btnSchedulerToggle');
    const sel = document.getElementById('schedulerSelect');
    const scheduler = sel ? sel.value : null;
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/scheduler/toggle', { body: { enable, scheduler } })
        .then(data => {
            if (data.success) showToast(data.message || 'Scheduler mis a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            loadScheduler();
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadScheduler(); });
}

function loadSysctls() {
    const ctrl = document.getElementById('sysctlsControls');
    if (!ctrl) return;
    api('/api/tweaks/sysctls')
        .then(data => {
            if (!data.success) { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; return; }
            const on = data.applied;
            const cur = data.current || {};
            const rows = Object.keys(data.target || {}).map(k =>
                `<code style="font-size: 0.78em; color: var(--text-muted);">${esc(k)} = ${esc(String(cur[k] ?? '?'))}</code>`
            ).join('<br>');
            ctrl.innerHTML =
                '<div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;">' +
                  '<span style="font-weight: bold; color: ' + (on ? 'var(--success)' : 'var(--text-muted)') + ';">' +
                    (on ? 'Actifs' : 'Inactifs') + '</span>' +
                  '<button class="btn-small" id="btnSysctlsToggle" onclick="toggleSysctls(' + (on ? 'false' : 'true') + ')" ' +
                    'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
                    (on ? 'Desactiver' : 'Activer') + '</button>' +
                '</div>' +
                '<div style="margin-top: 8px; line-height: 1.6;">' + rows + '</div>';
        })
        .catch(() => { ctrl.innerHTML = '<div style="color: var(--text-muted);">Non disponible</div>'; });
}

function toggleSysctls(enable) {
    const btn = document.getElementById('btnSysctlsToggle');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    api('/api/tweaks/sysctls/toggle', { body: { enable } })
        .then(data => {
            if (data.success) showToast(data.message || 'Sysctls mis a jour', 'success');
            else showToast(data.error || 'Erreur', 'error');
            loadSysctls();
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadSysctls(); });
}

function resetPlasma() {
    showConfirm('Reinitialiser Plasma',
        'Tue plasmashell, vide son cache, le relance. La barre des taches disparait 1-2 secondes. Continuer ?',
        () => {
            api('/api/tweaks/plasma/reset', { method: 'POST' })
                .then(data => {
                    if (data.success) showToast('Plasma reinitialise', 'success');
                    else showToast(data.error || 'Erreur', 'error');
                })
                .catch(() => showToast('Erreur reseau', 'error'));
        });
}

function clearCaches() {
    showConfirm('Vider les caches',
        'Vide ~/.cache/thumbnails, plasma*, krunner, icon-cache. Les miniatures seront regenerees au prochain affichage.',
        () => {
            api('/api/tweaks/cache/clear', { method: 'POST' })
                .then(data => {
                    if (data.success) {
                        const mb = (data.freed_bytes / 1024 / 1024).toFixed(1);
                        showToast(`${mb} Mo recuperes (${data.cleared.length} entrees)`, 'success');
                    } else {
                        showToast(data.error || 'Erreur', 'error');
                    }
                })
                .catch(() => showToast('Erreur reseau', 'error'));
        });
}

function loadServices() {
    const grid = document.getElementById('servicesGrid');
    if (!grid) return;
    api('/api/tweaks/services')
        .then(data => {
            if (!data.success || !data.services) {
                grid.innerHTML = '<div style="color: var(--danger);">Erreur de chargement.</div>';
                return;
            }
            grid.innerHTML = data.services.map(s => {
                const missing = s.raw_active === 'missing';
                const statusColor = missing ? 'var(--text-muted)' : (s.active ? 'var(--success)' : 'var(--text-muted)');
                const statusText = missing ? 'non installe' : (s.active ? 'actif' : 'arrete');
                const checked = s.enabled ? 'checked' : '';
                const control = missing
                    ? '<span style="font-size: 0.78em; color: var(--text-muted); flex-shrink: 0;">absent</span>'
                    : `<label class="toggle-switch" style="flex-shrink: 0;">
                          <input type="checkbox" ${checked} onchange="toggleService('${esc(s.name)}', this.checked)">
                          <span class="slider"></span>
                      </label>`;
                return `<div style="background: var(--light); border-radius: 8px; padding: 12px 14px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 200px;">
                        <div style="font-weight: 600; color: var(--dark);">
                            ${esc(s.name)}
                            <span style="color: ${statusColor}; font-size: 0.8em; font-weight: 500; margin-left: 8px;">[${statusText}]</span>
                        </div>
                        <div style="font-size: 0.78em; color: var(--text-muted); margin-top: 2px;">${esc(s.description)}</div>
                    </div>
                    ${control}
                </div>`;
            }).join('');
        })
        .catch(() => {
            grid.innerHTML = '<div style="color: var(--danger);">Erreur reseau.</div>';
        });
}

function toggleService(name, enable) {
    api('/api/tweaks/services/toggle', { body: {name, enable} })
        .then(data => {
            if (data.success) {
                showToast(`${name} ${enable ? 'active' : 'desactive'}`, 'success');
            } else {
                showToast(data.error || 'Erreur', 'error');
            }
            setTimeout(loadServices, 400);
        })
        .catch(() => {
            showToast('Erreur reseau', 'error');
            loadServices();
        });
}

function loadAudioStatus() {
    const ctrl = document.getElementById('audioControls');
    if (!ctrl) return;
    api('/api/tweaks/audio')
        .then(data => {
            if (!data.success) {
                ctrl.innerHTML = '<div style="color: var(--danger);">Erreur.</div>';
                return;
            }
            const activeRate = data.configured_rate || data.current_rate;
            const currentDisplay = data.current_rate ? `${data.current_rate} Hz` : 'inconnu (pw-metadata absent ?)';
            const configDisplay = data.configured_rate ? `${data.configured_rate} Hz` : 'non defini';
            const opts = data.allowed_rates.map(r =>
                `<option value="${r}" ${r === activeRate ? 'selected' : ''}>${r} Hz</option>`
            ).join('');
            ctrl.innerHTML = `
                <div style="background: var(--light); border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 220px;">
                        <div style="font-weight: 600; color: var(--dark);">Sample rate</div>
                        <div style="font-size: 0.78em; color: var(--text-muted); margin-top: 2px;">
                            Actuel : ${currentDisplay} — Config FedoraForgeKDE : ${configDisplay}
                        </div>
                    </div>
                    <select id="audioRateSelect" style="padding: 8px 12px; border: 2px solid var(--border); border-radius: 6px; background: var(--card-bg); color: var(--text); font-size: 0.9em;">
                        ${opts}
                    </select>
                    <button class="btn-small" onclick="applyAudioRate()" style="padding: 8px 16px;">Appliquer</button>
                </div>
                <div style="background: var(--light); border-radius: 8px; padding: 12px 14px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 220px;">
                        <div style="font-weight: 600; color: var(--dark);">Codecs Bluetooth premium</div>
                        <div style="font-size: 0.78em; color: var(--text-muted); margin-top: 2px;">
                            LDAC + aptX-HD + AAC (necessaire pour casques BT haut de gamme)
                        </div>
                    </div>
                    <label class="toggle-switch" style="flex-shrink: 0;">
                        <input type="checkbox" id="btCodecsToggle" ${data.bt_premium ? 'checked' : ''} onchange="applyBtCodecs(this.checked)">
                        <span class="slider"></span>
                    </label>
                </div>
            `;
        })
        .catch(() => {
            ctrl.innerHTML = '<div style="color: var(--danger);">Erreur reseau.</div>';
        });
}

function applyAudioRate() {
    const sel = document.getElementById('audioRateSelect');
    if (!sel) return;
    const rate = parseInt(sel.value, 10);
    api('/api/tweaks/audio/rate', { body: {rate} })
        .then(data => {
            if (data.success) {
                const msg = `Sample rate -> ${rate} Hz` + (data.warning ? ' (' + data.warning + ')' : '');
                showToast(msg, data.warning ? 'warning' : 'success');
                setTimeout(loadAudioStatus, 1500);
            } else {
                showToast(data.error || 'Erreur', 'error');
            }
        })
        .catch(() => showToast('Erreur reseau', 'error'));
}

function applyBtCodecs(enable) {
    api('/api/tweaks/audio/bt-codecs', { body: {enable} })
        .then(data => {
            if (data.success) {
                const verb = enable ? 'actives' : 'desactives';
                const msg = `Codecs BT premium ${verb}` + (data.warning ? ' (' + data.warning + ')' : '');
                showToast(msg, data.warning ? 'warning' : 'success');
            } else {
                showToast(data.error || 'Erreur', 'error');
                loadAudioStatus();
            }
        })
        .catch(() => {
            showToast('Erreur reseau', 'error');
            loadAudioStatus();
        });
}
