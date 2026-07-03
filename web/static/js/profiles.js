// profiles.js — grille des profils, selection, modal detail, installation
// (complete ou personnalisee), preflight, dry-run, export/import de selection.

let selectedProfiles = new Set();
let profilesData = {};
let _modalProfileSlug = null;

function loadProfiles() {
    const grid = document.getElementById('profilesGrid');
    grid.innerHTML = '<div style="color: var(--text-muted); padding: 10px;">Chargement...</div>';
    api('/api/profiles')
        .then(data => {
            if (!data.success) {
                grid.innerHTML = '<div style="color: var(--danger); padding: 10px;">Erreur : ' + esc(data.error || 'impossible de charger les profils') + '</div>';
                return;
            }
            profilesData = data.profiles;
            grid.innerHTML = '';
            for (const [slug, p] of Object.entries(data.profiles)) {
                const card = document.createElement('div');
                card.className = 'profile-card';
                card.dataset.slug = slug;
                card.dataset.locked = p.locked ? '1' : '0';

                card.onclick = (e) => {
                    if (e.target.closest('.btn-detail')) return;
                    if (p.locked && card.dataset.unlocked !== '1') {
                        showConfirm(
                            'Profil non recommande',
                            'Ce profil est destine a un GPU different de celui detecte. Forcer l\'installation peut causer des conflits. Continuer quand meme ?',
                            () => { card.dataset.unlocked = '1'; toggleProfile(slug, card); }
                        );
                        return;
                    }
                    toggleProfile(slug, card);
                };

                const counts = [];
                if (p.counts.apt) counts.push(p.counts.apt + ' DNF');
                if (p.counts.flatpak) counts.push(p.counts.flatpak + ' Flatpak');
                if (p.counts.external) counts.push('⚠️ ' + p.counts.external + ' Externe');
                if (p.counts.remove) counts.push(p.counts.remove + ' Suppr.');

                const badgeHtml = p.suggested
                    ? '<div class="badge-suggested">Recommande</div>'
                    : (p.locked ? '<div class="badge-suggested" style="background: #64748b;">🔒 GPU different</div>' : '');

                card.innerHTML = `
                    <div class="check-mark"></div>
                    ${badgeHtml}
                    <div class="profile-icon" style="${p.locked ? 'opacity:0.5' : ''}">${ICON_MAP[p.icon] || '📦'}</div>
                    <div class="profile-name" style="${p.locked ? 'opacity:0.6' : ''}">${p.name}</div>
                    <div class="profile-desc" style="${p.locked ? 'opacity:0.6' : ''}">${p.description}</div>
                    <div class="profile-counts">
                        ${counts.map(c => '<span>' + c + '</span>').join('')}
                    </div>
                    <button class="btn-detail" onclick="showProfileDetail('${slug}')" title="Voir le detail">Detail &#8594;</button>
                `;
                if (p.locked) card.style.borderColor = '#94a3b8';
                grid.appendChild(card);

                if (p.suggested) toggleProfile(slug, card);
            }
        })
        .catch(() => {
            document.getElementById('profilesGrid').innerHTML =
                '<div style="color: var(--danger); padding: 10px;">Erreur reseau — verifiez que le serveur tourne.</div>';
        });
}

function toggleProfile(slug, card) {
    if (isTaskRunning) return;
    if (selectedProfiles.has(slug)) {
        selectedProfiles.delete(slug);
        card.classList.remove('selected');
        card.querySelector('.check-mark').textContent = '';
    } else {
        selectedProfiles.add(slug);
        card.classList.add('selected');
        card.querySelector('.check-mark').textContent = '✓';
    }
    updateProfileButton();
}

function selectAllProfiles() {
    if (isTaskRunning) return;
    document.querySelectorAll('.profile-card').forEach(card => {
        selectedProfiles.add(card.dataset.slug);
        card.classList.add('selected');
        card.querySelector('.check-mark').textContent = '✓';
    });
    updateProfileButton();
}

function deselectAllProfiles() {
    document.querySelectorAll('.profile-card').forEach(card => {
        card.classList.remove('selected');
        card.querySelector('.check-mark').textContent = '';
    });
    selectedProfiles.clear();
    updateProfileButton();
}

function updateProfileButton() {
    const btn = document.getElementById('btnInstallProfiles');
    const sub = document.getElementById('profilesBtnSub');
    const count = selectedProfiles.size;
    btn.disabled = count === 0 || isTaskRunning;
    if (count === 0) {
        sub.textContent = 'Aucun profil selectionne';
    } else {
        let total = 0;
        selectedProfiles.forEach(s => { if (profilesData[s]) total += profilesData[s].counts.total; });
        sub.textContent = count + ' profil' + (count > 1 ? 's' : '') + ' — ' + total + ' packages';
    }
}

function installProfiles() {
    if (isTaskRunning || selectedProfiles.size === 0) return;
    const slugs = Array.from(selectedProfiles);
    const names = slugs.map(s => profilesData[s] ? profilesData[s].name : s);
    showConfirm(
        'Installer les profils ?',
        names.join(', ') + ' — cela peut prendre plusieurs minutes.',
        () => _doInstallProfiles(slugs, names)
    );
}
function _doInstallProfiles(slugs, names) {
    const snap = document.getElementById('snapshotToggle');
    const useSnapshot = !!(snap && snap.checked);
    api('/api/profiles/install', { body: {profiles: slugs, snapshot: useSnapshot} })
        .then(data => {
            if (data.success) addLog('Installation demarree: ' + names.join(', '));
            else showToast('Erreur : ' + data.error, 'error');
        })
        .catch(err => showToast('Erreur reseau : ' + err, 'error'));
}

// =============================================
// INSTALLATION PERSONNALISEE DEPUIS MODAL
// =============================================
function showProfileDetail(slug) {
    _modalProfileSlug = slug;
    api('/api/profiles/' + slug)
        .then(data => {
            if (!data.success) return;
            const p = data.profile;
            document.getElementById('modalTitle').textContent = (ICON_MAP[p.icon] || '') + ' ' + p.name;
            document.getElementById('modalDesc').textContent = p.description;

            let html = '';
            const sections = [
                ['apt',      'DNF',        'name', true],
                ['flatpak',  'Flatpak',    'app',  true],
                ['external', 'Externe',    'name', true],
                ['remove',   'Suppression','name', false],
            ];
            sections.forEach(([key, label, nameField, checkable]) => {
                if (!p[key].length) return;
                const extWarning = (key === 'external' && p[key].some(e => !e.config))
                    ? '<div style="background:#fff3cd;border-left:3px solid #f0ad4e;border-radius:5px;padding:7px 11px;margin-bottom:8px;font-size:0.82em;color:#856404;">⚠️ <strong>Paquets externes</strong> — ces commandes installent depuis des depots tiers (non officiels). Verifiez les sources avant d\'installer.</div>'
                    : '';
                html += '<div class="pkg-section"><h4>' + label + ' (' + p[key].length + ')</h4>' + extWarning + '<ul class="pkg-list">';
                p[key].forEach((pkg, i) => {
                    const id = 'mpkg_' + key + '_' + i;
                    const pkgName = pkg[nameField];
                    if (checkable) {
                        html += `<li style="display:flex; align-items:center; gap: 8px;">
                            <input type="checkbox" id="${id}" data-type="${key}" data-idx="${i}" checked style="cursor:pointer; width:15px; height:15px; flex-shrink:0;">
                            <label for="${id}" style="cursor:pointer; flex:1;">
                                <span class="pkg-name">${esc(pkgName)}</span>
                                <span class="pkg-desc">${esc(pkg.description)}</span>
                            </label>
                        </li>`;
                    } else {
                        html += '<li><span class="pkg-name">' + esc(pkgName) + '</span><span class="pkg-desc">' + esc(pkg.description) + '</span></li>';
                    }
                });
                html += '</ul></div>';
            });
            document.getElementById('modalContent').innerHTML = html;
            document.getElementById('modalContent').dataset.profile = JSON.stringify(p);
            document.getElementById('modalFooter').style.display = 'flex';
            document.getElementById('modalOverlay').classList.add('active');
        });
}

function checkAllModalPkgs(checked) {
    document.querySelectorAll('#modalContent input[type=checkbox]').forEach(cb => { cb.checked = checked; });
}

function installCustomFromModal() {
    if (isTaskRunning) { showToast('Une tache est en cours', 'warning'); return; }
    const p = JSON.parse(document.getElementById('modalContent').dataset.profile || '{}');
    const checked = {};
    document.querySelectorAll('#modalContent input[type=checkbox]:checked').forEach(cb => {
        const type = cb.dataset.type;
        const idx  = parseInt(cb.dataset.idx);
        if (!checked[type]) checked[type] = [];
        checked[type].push(idx);
    });
    const apt      = (checked.apt      || []).map(i => p.apt[i]);
    const flatpak  = (checked.flatpak  || []).map(i => p.flatpak[i]);
    const external = (checked.external || []).map(i => ({...p.external[i]}));
    const remove   = (p.remove || []);

    if (!apt.length && !flatpak.length && !external.length) {
        showToast('Aucun paquet coche', 'warning');
        return;
    }
    const total = apt.length + flatpak.length + external.length;
    const slug  = _modalProfileSlug;

    closeModal();
    if (slug) {
        selectedProfiles.delete(slug);
        const card = document.querySelector('.profile-card[data-slug="' + slug + '"]');
        if (card) { card.classList.remove('selected'); card.querySelector('.check-mark').textContent = ''; }
        updateProfileButton();
    }

    showConfirm(
        'Installer la selection ?',
        total + ' paquet(s) selectionne(s) du profil.',
        () => {
            api('/api/profiles/install-custom', { body: {apt, flatpak, external, remove} })
                .then(data => {
                    if (data.success) addLog('Installation personnalisee lancee (' + total + ' paquets)');
                    else showToast('Erreur : ' + data.error, 'error');
                })
                .catch(err => showToast('Erreur reseau : ' + err, 'error'));
        }
    );
}

// Dry-run / Preflight / Export / Import
function preflightProfiles() {
    if (selectedProfiles.size === 0) return showToast('Aucun profil selectionne.', 'warning');
    api('/api/profiles/preflight', { body: {profiles: Array.from(selectedProfiles)} })
        .then(data => {
            if (!data.success) return showToast('Erreur : ' + data.error, 'error');
            const s = data.summary;
            let html = '<div class="pkg-section"><h4>Resume</h4><ul class="pkg-list">'
                + '<li><span class="pkg-name">DNF a installer</span><span class="pkg-status to_install">' + s.apt_to_install + '</span></li>'
                + '<li><span class="pkg-name">DNF deja installes</span><span class="pkg-status installed">' + s.apt_already_installed + '</span></li>'
                + '<li><span class="pkg-name">Flatpak a installer</span><span class="pkg-status to_install">' + s.flatpak_to_install + '</span></li>'
                + '<li><span class="pkg-name">Flatpak deja installes</span><span class="pkg-status installed">' + s.flatpak_already_installed + '</span></li>'
                + '<li><span class="pkg-name">Externes (bash)</span><span class="pkg-status duplicate">' + s.external_count + '</span></li>'
                + '<li><span class="pkg-name">Paquets a supprimer</span><span class="pkg-status absent">' + s.remove_count + '</span></li>'
                + '</ul></div>';

            if ((data.conflicts || []).length) {
                html += '<div class="pkg-section"><h4 style="color:var(--danger);">Conflits detectes</h4><ul class="pkg-list">';
                data.conflicts.forEach(c => {
                    html += '<li><span class="pkg-name">' + esc(c.package) + '</span>'
                        + '<span class="pkg-status absent">install: ' + c.installed_by.join(',') + ' / remove: ' + c.removed_by.join(',') + '</span></li>';
                });
                html += '</ul></div>';
            }
            if ((data.warnings || []).length) {
                html += '<div class="pkg-section"><h4 style="color:var(--warning);">Avertissements</h4><ul class="pkg-list">';
                data.warnings.forEach(w => { html += '<li>' + esc(w) + '</li>'; });
                html += '</ul></div>';
            }
            if ((data.external || []).length) {
                html += '<div class="pkg-section"><h4>Commandes externes (bash) — verifier avant install</h4><ul class="pkg-list">';
                data.external.forEach(e => {
                    html += '<li><span class="pkg-name">' + esc(e.name) + '</span><span class="pkg-status duplicate">' + esc(e.profile) + '</span></li>';
                });
                html += '</ul></div>';
            }

            document.getElementById('modalTitle').textContent = 'Pre-flight check';
            document.getElementById('modalDesc').textContent = selectedProfiles.size + ' profil(s) — GPU detecte : ' + (data.gpu || 'inconnu');
            document.getElementById('modalContent').innerHTML = html;
            document.getElementById('modalOverlay').classList.add('active');
        })
        .catch(err => showToast('Erreur reseau : ' + err, 'error'));
}

function dryRunProfiles() {
    if (selectedProfiles.size === 0) return showToast('Aucun profil selectionne.', 'warning');
    api('/api/profiles/dry-run', { body: {profiles: Array.from(selectedProfiles)} })
        .then(data => {
            if (!data.success) return showToast('Erreur: ' + data.error, 'error');
            const STATUS_LABELS = { to_install: 'A installer', installed: 'Deja installe', duplicate: 'Doublon', absent: 'Absent' };
            let html = '';
            for (const [slug, entry] of Object.entries(data.dry_run)) {
                const pName = profilesData[slug] ? profilesData[slug].name : slug;
                html += '<div class="pkg-section"><h4>' + pName + '</h4><ul class="pkg-list">';
                ['apt', 'flatpak', 'external', 'remove'].forEach(cat => {
                    entry[cat].forEach(pkg => {
                        const name = pkg.name || pkg.app;
                        html += '<li><span class="pkg-name">' + name + '</span>'
                            + '<span class="pkg-status ' + pkg.status + '">' + STATUS_LABELS[pkg.status] + '</span></li>';
                    });
                });
                html += '</ul></div>';
            }
            document.getElementById('modalTitle').textContent = 'Apercu (dry-run)';
            document.getElementById('modalDesc').textContent = selectedProfiles.size + ' profil(s)';
            document.getElementById('modalContent').innerHTML = html;
            document.getElementById('modalOverlay').classList.add('active');
        })
        .catch(err => showToast('Erreur reseau: ' + err, 'error'));
}

function exportProfiles() {
    if (selectedProfiles.size === 0) return showToast('Aucun profil selectionne.', 'warning');
    const blob = new Blob([JSON.stringify({profiles: Array.from(selectedProfiles)}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'fedoraforgekde_profiles.json';
    a.click();
    URL.revokeObjectURL(url);
    addLog('Selection exportee: ' + Array.from(selectedProfiles).join(', '));
}

function importProfiles() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = function(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(ev) {
            try {
                const data = JSON.parse(ev.target.result);
                if (!data.profiles || !Array.isArray(data.profiles)) {
                    return showToast('Fichier invalide : pas de liste "profiles".', 'error');
                }
                api('/api/profiles/import', { body: {profiles: data.profiles} })
                    .then(resp => {
                        if (!resp.success) return showToast('Erreur: ' + resp.error, 'error');
                        deselectAllProfiles();
                        resp.profiles.forEach(slug => {
                            const card = document.querySelector('.profile-card[data-slug="' + slug + '"]');
                            if (card) toggleProfile(slug, card);
                        });
                        if (resp.invalid.length) addLog('Profils ignores : ' + resp.invalid.join(', '));
                        addLog('Selection importee : ' + resp.profiles.join(', '));
                    });
            } catch (err) {
                showToast('Fichier JSON invalide.', 'error');
            }
        };
        reader.readAsText(file);
    };
    input.click();
}
