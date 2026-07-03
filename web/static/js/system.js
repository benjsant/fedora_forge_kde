// system.js — outils systeme Fedora KDE, assistant SELinux, pare-feu,
// paquets optionnels, historique des actions et rollback.

// =============================================
// Outils systeme Fedora KDE
// =============================================
function loadSystemTools() {
    const grid = document.getElementById('systemToolsGrid');
    grid.innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
    api('/api/tools')
        .then(data => {
            if (!data.success || !data.tools) {
                grid.innerHTML = '<div style="color: var(--text-muted);">Aucun outil disponible.</div>';
                return;
            }
            grid.innerHTML = '';
            data.tools.forEach(t => {
                const card = document.createElement('div');
                card.style.cssText = 'background: var(--card-bg); border-radius: 10px; padding: 12px; box-shadow: var(--card-shadow); display: flex; flex-direction: column; gap: 6px; opacity: ' + (t.available ? '1' : '0.55');
                const status = t.available
                    ? '<span style="color: var(--success); font-size: 0.78em;">installe</span>'
                    : '<span style="color: var(--text-muted); font-size: 0.78em;">non installe</span>';
                card.innerHTML = `
                    <div style="font-size: 1.4em;">${t.icon || '🔧'}</div>
                    <div style="font-weight: 600; font-size: 0.92em;">${esc(t.name)}</div>
                    <div style="font-size: 0.8em; color: var(--text-muted); flex: 1;">${esc(t.description)}</div>
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px;">
                        ${status}
                        <button class="btn-small tool-launch" data-id="${esc(t.id)}" ${t.available ? '' : 'disabled'} style="font-size: 0.82em; padding: 5px 10px;">Lancer</button>
                    </div>
                `;
                grid.appendChild(card);
            });
            grid.querySelectorAll('.tool-launch').forEach(btn => {
                btn.addEventListener('click', () => launchSystemTool(btn.dataset.id, btn));
            });
        })
        .catch(() => {
            grid.innerHTML = '<div style="color: var(--danger);">Erreur reseau</div>';
        });
}

function launchSystemTool(toolId, btn) {
    if (btn) { btn.disabled = true; btn.textContent = 'Lancement...'; }
    api('/api/tools/launch/' + encodeURIComponent(toolId), { method: 'POST' })
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Outil lance', 'success');
                addLog('Outil : ' + (data.message || toolId));
            } else {
                showToast(data.error || 'Erreur', 'error');
            }
        })
        .catch(err => showToast('Erreur reseau : ' + err, 'error'))
        .finally(() => {
            if (btn) { btn.disabled = false; btn.textContent = 'Lancer'; }
        });
}

// =============================================
// Assistant SELinux
// =============================================
function _renderSelinux(data) {
    const modeEl = document.getElementById('selinuxMode');
    const boolEl = document.getElementById('selinuxBooleans');
    const denEl = document.getElementById('selinuxDenials');
    if (!data.success) { modeEl.textContent = 'Non disponible'; boolEl.innerHTML = ''; denEl.textContent = ''; return; }
    const mode = data.mode || 'Inconnu';
    const color = mode === 'Enforcing' ? 'var(--success)' : (mode === 'Permissive' ? 'var(--warning, #b8860b)' : 'var(--text-muted)');
    modeEl.textContent = 'Mode : ' + mode;
    modeEl.style.color = color;

    if (!data.available) {
        boolEl.innerHTML = '<div style="font-size: 0.85em; color: var(--text-muted);">SELinux desactive sur ce systeme : rien a regler ici.</div>';
        denEl.textContent = '(SELinux inactif)';
        return;
    }
    const booleans = data.booleans || {};
    const keys = Object.keys(booleans);
    boolEl.innerHTML = keys.length ? keys.map(name => {
        const b = booleans[name];
        const on = b.value;
        return '<div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; background: var(--light); padding: 8px 12px; border-radius: 8px;">' +
            '<div style="flex: 1; min-width: 200px;"><code style="font-size: 0.8em;">' + esc(name) + '</code>' +
            '<div style="font-size: 0.78em; color: var(--text-muted);">' + esc(b.description) + '</div></div>' +
            '<button class="btn-small" onclick="toggleSelinuxBoolean(\'' + esc(name) + '\', ' + (on ? 'false' : 'true') + ')" ' +
            'style="border-color: ' + (on ? 'var(--danger)' : 'var(--success)') + '; color: ' + (on ? 'var(--danger)' : 'var(--success)') + ';">' +
            (on ? 'Actif - desactiver' : 'Inactif - activer') + '</button></div>';
    }).join('') : '<div style="color: var(--text-muted);">Aucun boolean expose.</div>';

    const denials = data.denials || [];
    denEl.textContent = denials.length ? denials.join('\n') : 'Aucun refus AVC recent.';
}

function loadSelinux() {
    api('/api/selinux/status')
        .then(_renderSelinux)
        .catch(() => { document.getElementById('selinuxMode').textContent = 'Non disponible'; });
}

function toggleSelinuxBoolean(name, enable) {
    api('/api/selinux/boolean', { body: { name, enable } })
        .then(data => {
            if (data.success) { showToast(data.message || 'Boolean mis a jour', 'success'); _renderSelinux(data); }
            else { showToast(data.error || 'Erreur', 'error'); loadSelinux(); }
        })
        .catch(() => { showToast('Erreur reseau', 'error'); loadSelinux(); });
}

// =============================================
// Pare-feu (firewalld)
// =============================================
function loadFirewall() {
    api('/api/system/firewall')
        .then(data => {
            const el = document.getElementById('firewallStatus');
            const out = document.getElementById('firewallOutput');
            if (!data.success) {
                el.textContent = 'Non disponible';
                el.style.color = 'var(--text-muted)';
                return;
            }
            el.textContent = data.enabled ? 'Actif' : 'Inactif';
            el.style.color = data.enabled ? 'var(--success)' : 'var(--danger)';
            if (data.output) {
                out.textContent = data.output;
                out.style.display = 'block';
            }
        })
        .catch(() => {
            document.getElementById('firewallStatus').textContent = 'Non disponible';
        });
}

function firewallEnable() {
    showConfirm('Activer le pare-feu ?', 'firewalld sera active avec les regles par defaut.', () => {
        api('/api/system/firewall/enable', { method: 'POST' })
            .then(data => {
                if (data.success) { loadFirewall(); showToast('Pare-feu active', 'success'); }
                else showToast('Erreur : ' + data.error, 'error');
            })
            .catch(err => showToast('Erreur reseau : ' + err, 'error'));
    });
}

function firewallDisable() {
    showConfirm('Desactiver le pare-feu ?', 'Le systeme ne sera plus protege par firewalld.', () => {
        api('/api/system/firewall/disable', { method: 'POST' })
            .then(data => {
                if (data.success) { loadFirewall(); showToast('Pare-feu desactive', 'warning'); }
                else showToast('Erreur : ' + data.error, 'error');
            })
            .catch(err => showToast('Erreur reseau : ' + err, 'error'));
    }, true);
}

// =============================================
// Paquets optionnels
// =============================================
function loadOptionalPackages() {
    const grid = document.getElementById('optionalGrid');
    grid.innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
    api('/api/optional/list')
        .then(data => {
            if (!data.packages || data.packages.length === 0) {
                grid.innerHTML = '<div style="color: var(--text-muted);">Aucun paquet optionnel configure.</div>';
                return;
            }
            grid.innerHTML = data.packages.map(pkg => {
                const status = pkg.installed
                    ? '<span style="color: var(--success); font-weight: bold;">installe</span>'
                    : '<span style="color: var(--text-muted);">non installe</span>';
                return `<div style="background: var(--light); border-radius: 8px; padding: 10px 14px; border: 1px solid var(--border);">
                    <div style="font-weight: 600; font-size: 0.92em;">${esc(pkg.name)}</div>
                    <div style="font-size: 0.82em; color: var(--text-muted);">${esc(pkg.description)}</div>
                    <div style="font-size: 0.8em; margin-top: 4px;">${status}</div>
                </div>`;
            }).join('');
        })
        .catch(() => {
            grid.innerHTML = '<div style="color: var(--danger);">Erreur de chargement.</div>';
        });
}

function installOptional() {
    if (isTaskRunning) { showToast('Une tache est deja en cours', 'warning'); return; }
    showConfirm('Paquets optionnels', 'Installer tous les paquets optionnels non presents ?', () => {
        api('/api/execute/optional_install', { method: 'POST' })
            .then(data => {
                if (data.success) showToast('Installation optionnelle lancee', 'success');
                else showToast(data.error || 'Erreur', 'error');
            })
            .catch(() => showToast('Erreur reseau', 'error'));
    });
}

// =============================================
// Historique & Rollback
// =============================================
function loadHistory() {
    api('/api/state')
        .then(data => {
            if (!data.success) return;
            const container = document.getElementById('historyContent');
            const summaryEl = document.getElementById('historySummary');

            if (!data.history.length) {
                container.innerHTML = '<div class="history-empty">Aucune action enregistree</div>';
                summaryEl.style.display = 'none';
                return;
            }

            const s = data.summary || {};
            const parts = [];
            if (s.total)      parts.push(s.total + ' action(s)');
            if (s.success)    parts.push(s.success + ' reussies');
            if (s.failed)     parts.push(s.failed + ' echouees');
            if (s.rollbackable) parts.push(s.rollbackable + ' annulables');
            summaryEl.textContent = parts.join(' · ');
            summaryEl.style.display = 'block';

            let html = '<ul class="history-list">';
            data.history.slice().reverse().forEach(entry => {
                const date = new Date(entry.timestamp).toLocaleString('fr-FR', {
                    hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'
                });
                let badge;
                if (entry.metadata && entry.metadata.rolled_back) {
                    badge = '<span class="hi-badge rollback">annule</span>';
                } else if (entry.success) {
                    badge = '<span class="hi-badge ok">ok</span>';
                } else {
                    badge = '<span class="hi-badge fail">echec</span>';
                }
                html += `<li class="history-item">
                    <span class="hi-action">${esc(entry.action)}</span>
                    <span class="hi-target">${esc(entry.target)}</span>
                    ${badge}
                    <span class="hi-time">${date}</span>
                </li>`;
            });
            html += '</ul>';
            container.innerHTML = html;
        })
        .catch(err => console.error('History error:', err));
}

function rollbackLast() {
    if (isTaskRunning) return showToast('Une tache est en cours', 'warning');
    showConfirm('Annuler la derniere action ?', 'Cette operation est irreversible.', () => {
        api('/api/state/rollback/last', { method: 'POST' })
            .then(data => {
                if (data.success) addLog('Rollback lance');
                else showToast('Erreur : ' + data.error, 'error');
            })
            .catch(err => showToast('Erreur reseau : ' + err, 'error'));
    });
}

function rollbackAll() {
    if (isTaskRunning) return showToast('Une tache est en cours', 'warning');
    showConfirm('Tout annuler ?', 'Toutes les actions enregistrees seront annulees.', () => {
        api('/api/state/rollback/all', { method: 'POST' })
            .then(data => {
                if (data.success) addLog('Rollback total lance');
                else showToast('Erreur : ' + data.error, 'error');
            })
            .catch(err => showToast('Erreur reseau : ' + err, 'error'));
    }, true);
}

function clearHistory() {
    if (isTaskRunning) return showToast('Une tache est en cours', 'warning');
    showConfirm('Effacer l\'historique ?', 'Aucun rollback ne sera effectue. L\'historique sera perdu.', () => {
        api('/api/state/clear', { method: 'DELETE' })
            .then(data => {
                if (data.success) {
                    loadHistory();
                    showToast('Historique efface', 'info');
                }
                else showToast('Erreur : ' + data.error, 'error');
            })
            .catch(err => showToast('Erreur reseau : ' + err, 'error'));
    }, true);
}
