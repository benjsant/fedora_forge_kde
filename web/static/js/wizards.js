// wizards.js — wizards Fedora (RPM Fusion, codecs, NVIDIA, Flathub) et
// catalogue COPR experimental. Les actions partent en tache de fond cote
// serveur : la reponse revient tout de suite, la progression passe par les
// logs SSE et les badges se rafraichissent a la fin de la tache (via
// refreshWizards() appele par updateTaskStatus dans core.js).

let _coprData = [];

function refreshWizards() {
    loadRpmFusion();
    loadCodecs();
    loadNvidia();
    loadFlathub();
    loadCopr();
}

function loadRpmFusion() {
    api('/api/fedora/rpmfusion')
        .then(data => {
            const badge = document.getElementById('rpmFusionBadge');
            const btn = document.getElementById('btnRpmFusionEnable');
            const warn = document.getElementById('rpmFusionWarn');
            if (!data.success) { badge.textContent = '(indisponible)'; return; }
            const ver = data.fedora_version ? ' - Fedora ' + data.fedora_version : '';
            if (data.enabled) {
                badge.textContent = 'Actif' + ver;
                badge.style.color = 'var(--success)';
                btn.disabled = true;
                btn.textContent = 'Active';
            } else {
                const partial = data.free_enabled || data.nonfree_enabled;
                badge.textContent = (partial ? 'Partiel' : 'Inactif') + ver;
                badge.style.color = partial ? 'var(--warning, #b8860b)' : 'var(--danger)';
                btn.disabled = false;
                btn.textContent = 'Activer';
            }
            if (data.selinux === 'enforcing') {
                warn.textContent = 'SELinux enforcing : certains paquets nonfree peuvent generer des denials AVC (verifier journalctl -t setroubleshoot).';
                warn.style.display = 'block';
            } else {
                warn.style.display = 'none';
            }
        })
        .catch(() => {
            document.getElementById('rpmFusionBadge').textContent = '(indisponible)';
        });
}

// Reaction commune aux wizards asynchrones : si la tache est lancee
// (data.started), on fige le bouton — le badge sera rafraichi a la fin de la
// tache. Sinon (deja fait, refus, erreur), on recharge l'etat tout de suite.
function _wizardStarted(data, btn, busyText, reload) {
    if (data.success && data.started) {
        showToast(data.message || 'Lance, suivez les logs', 'info');
        if (btn) { btn.disabled = true; btn.textContent = busyText; }
        return;
    }
    if (data.success) showToast(data.message || 'Deja fait', 'success');
    else showToast('Erreur : ' + (data.error || 'echec'), 'error');
    reload();
}

function rpmFusionEnable() {
    showConfirm('Activer RPM Fusion ?',
        'Les depots free + nonfree seront ajoutes (codecs, pilotes, paquets non libres). Le telechargement est lance en arriere-plan, suivez les logs.',
        () => {
            const btn = document.getElementById('btnRpmFusionEnable');
            btn.disabled = true;
            btn.textContent = 'Activation...';
            api('/api/fedora/rpmfusion/enable', { method: 'POST' })
                .then(data => _wizardStarted(data, btn, 'Activation...', () => {
                    loadRpmFusion();
                    loadCodecs();
                    loadNvidia();
                }))
                .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadRpmFusion(); });
        });
}

function loadCodecs() {
    api('/api/fedora/codecs')
        .then(data => {
            const badge = document.getElementById('codecsBadge');
            const btn = document.getElementById('btnCodecsInstall');
            if (!data.success) { badge.textContent = '(indisponible)'; return; }
            if (data.installed) {
                badge.textContent = 'Installes';
                badge.style.color = 'var(--success)';
                btn.disabled = true;
                btn.textContent = 'Installes';
            } else if (!data.rpmfusion_enabled) {
                badge.textContent = 'RPM Fusion requis';
                badge.style.color = 'var(--warning, #b8860b)';
                btn.disabled = true;
                btn.textContent = 'Installer';
            } else {
                badge.textContent = 'Absents';
                badge.style.color = 'var(--danger)';
                btn.disabled = false;
                btn.textContent = 'Installer';
            }
        })
        .catch(() => {
            document.getElementById('codecsBadge').textContent = '(indisponible)';
        });
}

function codecsInstall() {
    showConfirm('Installer les codecs multimedia ?',
        'ffmpeg complet et les plugins GStreamer seront installes (swap depuis ffmpeg-free). Telechargement lance en arriere-plan, suivez les logs.',
        () => {
            const btn = document.getElementById('btnCodecsInstall');
            btn.disabled = true;
            btn.textContent = 'Installation...';
            api('/api/fedora/codecs/install', { method: 'POST' })
                .then(data => _wizardStarted(data, btn, 'Installation...', loadCodecs))
                .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadCodecs(); });
        });
}

function loadNvidia() {
    api('/api/fedora/nvidia')
        .then(data => {
            const card = document.getElementById('nvidiaCard');
            if (!data.success || !data.gpu_detected) { card.style.display = 'none'; return; }
            card.style.display = 'block';
            const badge = document.getElementById('nvidiaBadge');
            const btn = document.getElementById('btnNvidiaInstall');
            const warn = document.getElementById('nvidiaWarn');
            if (data.installed) {
                badge.textContent = 'Installe';
                badge.style.color = 'var(--success)';
                btn.disabled = true;
                btn.textContent = 'Installe';
            } else if (!data.rpmfusion_enabled) {
                badge.textContent = 'RPM Fusion requis';
                badge.style.color = 'var(--warning, #b8860b)';
                btn.disabled = true;
                btn.textContent = 'Installer';
            } else {
                badge.textContent = 'Absent';
                badge.style.color = 'var(--danger)';
                btn.disabled = false;
                btn.textContent = 'Installer';
            }
            if (data.secure_boot === true) {
                warn.textContent = 'Secure Boot actif : le module akmod doit etre signe (MOK) sinon le pilote ne chargera pas apres redemarrage.';
                warn.style.display = 'block';
            } else {
                warn.style.display = 'none';
            }
        })
        .catch(() => { document.getElementById('nvidiaCard').style.display = 'none'; });
}

function nvidiaInstall() {
    showConfirm('Installer le pilote NVIDIA proprietaire ?',
        'akmod-nvidia et CUDA seront installes. Le module se compile au prochain demarrage : un redemarrage est requis. Suivez les logs.',
        () => {
            const btn = document.getElementById('btnNvidiaInstall');
            btn.disabled = true;
            btn.textContent = 'Installation...';
            api('/api/fedora/nvidia/install', { method: 'POST' })
                .then(data => _wizardStarted(data, btn, 'Installation...', loadNvidia))
                .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadNvidia(); });
        });
}

function loadFlathub() {
    api('/api/fedora/flathub')
        .then(data => {
            const badge = document.getElementById('flathubBadge');
            const btn = document.getElementById('btnFlathubEnable');
            if (!data.success) { badge.textContent = '(indisponible)'; return; }
            if (data.enabled) {
                badge.textContent = 'Actif (complet)';
                badge.style.color = 'var(--success)';
                btn.disabled = true;
                btn.textContent = 'Actif';
            } else {
                badge.textContent = data.present ? 'Filtre' : 'Absent';
                badge.style.color = 'var(--warning, #b8860b)';
                btn.disabled = false;
                btn.textContent = 'Activer';
            }
        })
        .catch(() => { document.getElementById('flathubBadge').textContent = '(indisponible)'; });
}

function flathubEnable() {
    showConfirm('Activer Flathub complet ?',
        'Le depot Flathub non filtre sera active (acces a toutes les applications Flatpak).',
        () => {
            const btn = document.getElementById('btnFlathubEnable');
            btn.disabled = true;
            btn.textContent = 'Activation...';
            api('/api/fedora/flathub/enable', { method: 'POST' })
                .then(data => _wizardStarted(data, btn, 'Activation...', loadFlathub))
                .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadFlathub(); });
        });
}

// =============================================
// CATALOGUE COPR EXPERIMENTAL (depots tiers)
// =============================================
function loadCopr() {
    const warn = document.getElementById('coprWarning');
    const list = document.getElementById('coprList');
    if (!list) return;
    api('/api/copr')
        .then(data => {
            if (!data.success) {
                if (warn) warn.textContent = 'Catalogue COPR indisponible.';
                list.innerHTML = '';
                return;
            }
            if (warn) warn.textContent = data.warning || '';
            _coprData = data.copr || [];
            renderCoprButtons();
        })
        .catch(() => { if (warn) warn.textContent = 'Erreur reseau.'; });
}

function renderCoprButtons() {
    const list = document.getElementById('coprList');
    if (!list) return;
    const ackEl = document.getElementById('coprAck');
    const ack = ackEl && ackEl.checked;
    if (!_coprData.length) {
        list.innerHTML = '<div style="color: var(--text-muted);">Aucun depot dans le catalogue.</div>';
        return;
    }
    list.innerHTML = _coprData.map(c =>
        '<div style="border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 10px;">' +
          '<div style="font-weight: bold;">' + esc(c.id) + '</div>' +
          '<div style="font-size: 0.85em; color: var(--text-muted); margin: 4px 0;">' + esc(c.description) + '</div>' +
          (c.danger ? '<div style="font-size: 0.82em; color: var(--danger); margin: 4px 0;">⚠ ' + esc(c.danger) + '</div>' : '') +
          '<div style="font-size: 0.78em; color: var(--text-muted);">Paquets : ' + esc((c.packages || []).join(', ')) + '</div>' +
          '<button class="btn-small" onclick="enableCopr(\'' + esc(c.id) + '\')" ' + (ack ? '' : 'disabled') +
            ' style="margin-top: 8px; border-color: var(--danger); color: var(--danger);">Activer + installer</button>' +
        '</div>'
    ).join('');
}

function enableCopr(id) {
    showConfirm('Activer un depot tiers',
        'Activer ' + id + ' et installer ses paquets ? Depot non maintenu par Fedora, a vos risques.',
        () => {
            api('/api/copr/enable', { body: { id, confirmed: true, install: true } })
                .then(data => {
                    if (data.success) showToast(data.message || 'Activation lancee, suivez les logs', 'info');
                    else showToast(data.error || 'Erreur', 'error');
                })
                .catch(() => showToast('Erreur reseau', 'error'));
        }, true);
}
