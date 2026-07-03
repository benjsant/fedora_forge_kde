// core.js — socle du frontend : helper api(), toasts, modale de confirmation,
// barre de tache, logs SSE, composant Alpine `forge` et bootstrap DOMContentLoaded.
// Charge en premier ; les autres modules (profiles.js, wizards.js, tweaks.js,
// themes.js, kde.js, system.js) supposent ses helpers disponibles.

let isTaskRunning = false;
let _themeInstallPending = false;
let eventSource = null;
let autoScroll = true;
const BASE_TITLE = 'FedoraForgeKDE';

const ICON_MAP = {
    'box': '📦', 'wrench': '🔧', 'gamepad': '🎮', 'cpu': '🖥️',
    'gpu': '🎛️', 'code': '💻', 'film': '🎬', 'shield': '🛡️', 'server': '🖧',
    'docker': '🐳', 'office': '📝'
};

function showToast(message, type) {
    const el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = message;
    document.getElementById('toastContainer').appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

// Helper API unique : centralise method/headers/JSON.stringify et le parsing
// de la reponse. `api(path)` -> GET ; `api(path, {body})` -> POST JSON.
// Retourne directement le JSON parse (remplace fetch().then(r => r.json())).
function api(path, opts) {
    opts = opts || {};
    const init = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: {} };
    if (opts.body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).then(r => r.json());
}

let _confirmCallback = null;
function showConfirm(title, message, onOk, danger) {
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;
    const btn = document.getElementById('confirmOk');
    btn.classList.toggle('danger', !!danger);
    _confirmCallback = onOk;
    document.getElementById('confirmOverlay').classList.add('active');
}
function confirmOk() {
    document.getElementById('confirmOverlay').classList.remove('active');
    if (_confirmCallback) { _confirmCallback(); _confirmCallback = null; }
}
function confirmCancel() {
    document.getElementById('confirmOverlay').classList.remove('active');
    _confirmCallback = null;
}

function esc(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

document.addEventListener('DOMContentLoaded', function() {
    loadTheme();
    // updateStatus + loadSystemInfo sont desormais geres par le composant Alpine `forge()`
    // (voir x-data="forge()" sur <body>). Polling 5s gere par son init().
    loadProfiles();
    loadRpmFusion();
    loadCodecs();
    loadNvidia();
    loadFlathub();
    loadSystemTools();
    loadOptionalPackages();
    loadThemeCatalog();
    loadKdeOptions();
    loadKdeBackups();
    loadTweaks();
    loadCopr();
    loadHistory();
    loadSelinux();
    loadFirewall();
    loadSddmStatus();
    connectLogs();
    loadLogsHistory();
});

// Theme (clair/sombre) de l'UI elle-meme
function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    document.getElementById('themeIcon').textContent = isDark ? '🌙' : '☀️';
    localStorage.setItem('fedoraforgekde-theme', isDark ? 'light' : 'dark');
}

function loadTheme() {
    const saved = localStorage.getItem('fedoraforgekde-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    document.getElementById('themeIcon').textContent = saved === 'dark' ? '☀️' : '🌙';
}

// ============================================================
// Composant Alpine.js : status-bar + panneau identite systeme
// ============================================================
// Remplace updateStatus(), loadSystemInfo(), updateCheck(),
// updatePowerStatus(), updateFailedServices(). Tout est declaratif via
// x-text/x-show/:class sur le HTML. Polling autonome via init() + setInterval.
// Le composant emet `status:updated` pour que le code legacy (task bar,
// snapshot toggle) puisse encore reagir au meme cycle de polling.
function forge() {
    return {
        checks: {},
        packages: {},
        systemInfo: null,

        init() {
            this.updateStatus();
            this.loadSystemInfo();
            setInterval(() => this.updateStatus(), 5000);
        },

        async updateStatus() {
            try {
                const data = await api('/api/status');
                this.checks = data.checks || {};
                this.packages = data.packages || {};
                // Notifie le code legacy (task bar, snapshot toggle)
                window.dispatchEvent(new CustomEvent('status:updated', {detail: data}));
            } catch (e) { console.error('Status error:', e); }
        },

        async loadSystemInfo() {
            try {
                const data = await api('/api/system/info');
                if (data.success) this.systemInfo = data.info;
            } catch (e) { console.error('System info error:', e); }
        },

        // --- Computed : status-bar ---
        get checkItems() {
            const c = this.checks, p = this.packages;
            const themes = (p.themes_gtk||0) + (p.themes_icons||0) + (p.themes_cursors||0);
            const disk = c.disk_free_gb;
            const failed = c.failed_services;
            return [
                { id: 'internet', label: 'Internet', value: c.internet ? '✅' : '❌', cls: c.internet ? 'ok' : 'error' },
                { id: 'sudo',     label: 'Sudo',     value: c.sudo ? '✅' : '❌',     cls: c.sudo ? 'ok' : 'error' },
                { id: 'python',   label: 'Python',   value: c.python_version ? '✅' : '❌', cls: c.python_version ? 'ok' : 'error' },
                { id: 'dnf',      label: 'DNF',      value: p.dnf ?? p.apt ?? 0,    cls: '' },
                { id: 'optional', label: 'Optionnel',value: p.optional ?? 0,        cls: '' },
                { id: 'flatpak',  label: 'Flatpaks', value: p.flatpak ?? 0,         cls: '' },
                { id: 'themes',   label: 'Themes',   value: themes,                  cls: '' },
                { id: 'disk',     label: 'Disque libre',
                  value: (disk !== undefined ? disk + ' Go' : '--'),
                  cls: (disk === undefined ? '' : (disk > 5 ? 'ok' : 'error')) },
                { id: 'failed',   label: 'Services en erreur',
                  value: (failed === null || failed === undefined ? '?' : failed),
                  cls: (failed === 0 ? 'ok' : (failed > 0 ? 'error' : '')) },
            ];
        },

        get powerCls() {
            if (!this.checks.power) return '';
            return this.checks.power.on_battery ? 'error' : 'ok';
        },
        get powerValue() {
            const p = this.checks.power;
            if (!p) return '--';
            return p.on_battery
                ? '🔋 ' + (p.capacity != null ? p.capacity + '%' : '')
                : '⚡ Secteur';
        },

        get missingTools() {
            const t = this.checks.tools || {};
            return Object.entries(t).filter(([,ok]) => !ok).map(([n]) => n);
        },

        get batteryMessage() {
            const p = this.checks.power;
            if (!p || !p.on_battery) return '';
            return '⚠ Vous etes sur batterie' +
                   (p.capacity != null ? ' (' + p.capacity + '%)' : '') +
                   '. Branchez le secteur avant une installation importante.';
        },

        // --- Computed : panneau identite ---
        get osLabel() {
            if (!this.systemInfo) return '';
            const o = this.systemInfo.os;
            return o.id === 'nobara' ? `Nobara ${o.version}` : (o.pretty || 'OS inconnu');
        },
        get kernelLabel() {
            if (!this.systemInfo) return '';
            const k = this.systemInfo.kernel;
            let txt = `Kernel ${k.release.split('-')[0]}`;
            if (k.patches?.length) txt += ` (${k.patches.join('+')})`;
            if (k.hz) txt += ` HZ=${k.hz}`;
            return txt;
        },
        get plasmaLabel() {
            return this.systemInfo
                ? (this.systemInfo.plasma ? `Plasma ${this.systemInfo.plasma}` : 'Plasma ?')
                : '';
        },
        get mesaLabel() {
            return this.systemInfo
                ? (this.systemInfo.mesa ? `Mesa ${this.systemInfo.mesa}` : 'Mesa ?')
                : '';
        },
        get sessionLabel() {
            if (!this.systemInfo) return '';
            return `${this.systemInfo.session.desktop || '?'} ${this.systemInfo.session.type || ''}`.trim();
        },
        get lsmLabel() {
            if (!this.systemInfo) return '';
            const lsm = (this.systemInfo.security.lsm || [])
                .filter(x => x && x !== 'capability').join('+');
            return `LSM: ${lsm || '?'}`;
        },
        get selinuxLabel() {
            return this.systemInfo ? `SELinux: ${this.systemInfo.security.selinux || '?'}` : '';
        },
        get sysctlLabel() {
            if (!this.systemInfo) return '';
            const gs = this.systemInfo.gaming_sysctls;
            const summary = [];
            if (gs.split_lock_mitigate === '0') summary.push('split_lock=0');
            if (gs.max_map_count && parseInt(gs.max_map_count) > 1000000) summary.push('max_map=ok');
            if (gs.tcp_mtu_probing === '1') summary.push('mtu=on');
            return summary.length ? `Sysctl gaming: ${summary.join(' ')}` : 'Sysctl: default';
        },
        get sysctlTooltip() {
            if (!this.systemInfo) return '';
            const gs = this.systemInfo.gaming_sysctls;
            return `swappiness=${gs.swappiness}, max_map_count=${gs.max_map_count}`;
        },
        get fsLabel() {
            if (!this.systemInfo) return '';
            const fs = this.systemInfo.btrfs_root;
            return fs.is_btrfs
                ? `btrfs ${fs.subvol || ''} ${fs.compress ? '+'+fs.compress : ''}`.trim()
                : 'FS: non-btrfs';
        },
        get fsTooltip() {
            if (!this.systemInfo?.btrfs_root?.is_btrfs) return '';
            return (this.systemInfo.btrfs_root.options || []).join(',');
        },
        get zramLabel() {
            if (!this.systemInfo) return '';
            const z = this.systemInfo.zram;
            if (!z || !z.length) return 'pas de zram';
            const total = z.reduce((s, d) => s + d.size_mb, 0);
            return `zram ${(total / 1024).toFixed(1)} Go`;
        },
    };
}

// Listener legacy pour task-bar et snapshot toggle (encore en vanilla JS).
// Le composant Alpine `forge` emet cet event a chaque polling /api/status.
window.addEventListener('status:updated', e => {
    const data = e.detail;
    const snapWrap = document.getElementById('snapshotToggleWrap');
    if (snapWrap) snapWrap.style.display = data.checks.timeshift ? 'inline-flex' : 'none';
    updateTaskStatus(data.task);
});

function updateTaskStatus(task) {
    const taskBar = document.getElementById('taskBar');
    const statusDiv = document.getElementById('taskStatus');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const wasRunning = isTaskRunning;

    if (task.running) {
        isTaskRunning = true;
        taskBar.style.display = 'block';
        statusDiv.innerHTML = '<span class="spinner"></span>' + task.name;
        statusDiv.classList.add('running');
        progressBar.style.display = 'block';
        progressFill.style.width = task.progress + '%';
        progressFill.textContent = task.progress + '%';
        document.title = '⏳ ' + task.name + ' - ' + BASE_TITLE;
        document.getElementById('btnCancelTask').style.display = '';
        setAllButtons(true);
    } else {
        document.getElementById('btnCancelTask').style.display = 'none';
        isTaskRunning = false;
        if (task.progress === 100 && task.name) {
            taskBar.style.display = 'block';
            statusDiv.textContent = task.name;
            statusDiv.classList.remove('running');
            progressBar.style.display = 'block';
            progressFill.style.width = '100%';
            progressFill.textContent = '100%';
            document.title = '✅ ' + task.name + ' - ' + BASE_TITLE;
        } else {
            taskBar.style.display = 'none';
            document.title = BASE_TITLE;
        }
        setAllButtons(false);
        if (wasRunning) {
            loadHistory();
            loadOptionalPackages();
            // Les wizards (RPM Fusion, codecs, NVIDIA, Flathub, COPR) tournent
            // desormais en tache de fond : leurs badges se rafraichissent ici,
            // a la fin de la tache.
            refreshWizards();
            if (_themeInstallPending) {
                _themeInstallPending = false;
                setTimeout(() => loadThemeCatalog(), 500);
            }
        }
    }
}

function setAllButtons(disabled) {
    document.querySelectorAll('.big-button, .install-profiles-btn, .dconf-section button, .history-toolbar button').forEach(btn => {
        btn.disabled = disabled;
    });
    document.querySelectorAll('#themeCatalogGrid .btn-small').forEach(btn => {
        btn.disabled = disabled;
        if (disabled) {
            btn.dataset.prevText = btn.textContent;
            btn.textContent = 'Tache en cours...';
        } else if (btn.dataset.prevText) {
            btn.textContent = btn.dataset.prevText;
        }
    });
    if (!disabled) {
        document.getElementById('btnInstallProfiles').disabled = selectedProfiles.size === 0;
    }
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('active');
    document.getElementById('modalFooter').style.display = 'none';
}
function closeModalOutside(e) { if (e.target === document.getElementById('modalOverlay')) closeModal(); }

function cancelTask() {
    showConfirm(
        'Annuler la tache en cours ?',
        'Le processus sera interrompu immediatement.',
        () => {
            api('/api/task/cancel', { method: 'POST' })
                .then(data => {
                    if (data.success) addLog('Tache annulee.');
                    else showToast('Rien a annuler.', 'warning');
                })
                .catch(err => showToast('Erreur : ' + err, 'error'));
        },
        true
    );
}

// Logs SSE
function connectLogs() {
    if (eventSource) eventSource.close();
    const indicator = document.getElementById('sseIndicator');
    eventSource = new EventSource('/api/logs/stream');
    eventSource.onopen = () => { indicator.className = 'sse-indicator connected'; };
    eventSource.onmessage = function(event) {
        indicator.className = 'sse-indicator connected';
        const container = document.getElementById('logsContainer');
        const line = document.createElement('div');
        line.className = 'log-line';
        line.textContent = event.data;
        container.appendChild(line);
        if (autoScroll) container.scrollTop = container.scrollHeight;
        while (container.children.length > 500) container.removeChild(container.firstChild);
    };
    eventSource.onerror = () => {
        indicator.className = 'sse-indicator disconnected';
        setTimeout(connectLogs, 5000);
    };
}

function loadLogsHistory() {
    api('/api/logs/history')
        .then(data => {
            if (!data.lines || !data.lines.length) return;
            const container = document.getElementById('logsContainer');
            container.innerHTML = '';
            data.lines.forEach(line => {
                const el = document.createElement('div');
                el.className = 'log-line';
                el.textContent = line;
                container.appendChild(el);
            });
            container.scrollTop = container.scrollHeight;
        })
        .catch(() => {});
}

function clearLogs() {
    document.getElementById('logsContainer').innerHTML = '';
    api('/api/logs/clear', { method: 'POST' });
}

function toggleAutoScroll() {
    autoScroll = !autoScroll;
    document.getElementById('btnAutoScroll').textContent = 'Auto-scroll: ' + (autoScroll ? 'ON' : 'OFF');
}

function addLog(message) {
    const container = document.getElementById('logsContainer');
    const line = document.createElement('div');
    line.className = 'log-line';
    line.textContent = new Date().toLocaleTimeString() + ' - ' + message;
    container.appendChild(line);
    if (autoScroll) container.scrollTop = container.scrollHeight;
}

function quitApp() {
    const bye = () => {
        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#666;"><div style="text-align:center;"><h2>FedoraForgeKDE ferme.</h2><p>Vous pouvez fermer cet onglet.</p></div></div>';
    };
    showConfirm('Quitter', 'Fermer FedoraForgeKDE ?', () => {
        api('/api/quit', { method: 'POST' }).then(bye).catch(bye);
    });
}
