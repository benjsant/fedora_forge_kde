        let isTaskRunning = false;
        let _themeInstallPending = false;
        let eventSource = null;
        let selectedProfiles = new Set();
        let profilesData = {};
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
            loadHistory();
            loadSelinux();
            loadFirewall();
            loadSddmStatus();
            connectLogs();
            loadLogsHistory();
        });

        // Theme
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
                        const r = await fetch('/api/status');
                        const data = await r.json();
                        this.checks = data.checks || {};
                        this.packages = data.packages || {};
                        // Notifie le code legacy (task bar, snapshot toggle)
                        window.dispatchEvent(new CustomEvent('status:updated', {detail: data}));
                    } catch (e) { console.error('Status error:', e); }
                },

                async loadSystemInfo() {
                    try {
                        const r = await fetch('/api/system/info');
                        const data = await r.json();
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

        // Profiles
        function loadProfiles() {
            const grid = document.getElementById('profilesGrid');
            grid.innerHTML = '<div style="color: var(--text-muted); padding: 10px;">Chargement...</div>';
            fetch('/api/profiles')
                .then(r => r.json())
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
                .catch(err => {
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
            fetch('/api/profiles/install', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({profiles: slugs, snapshot: useSnapshot})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) addLog('Installation demarree: ' + names.join(', '));
                else showToast('Erreur : ' + data.error, 'error');
            })
            .catch(err => showToast('Erreur reseau : ' + err, 'error'));
        }

        function closeModal() {
            document.getElementById('modalOverlay').classList.remove('active');
            document.getElementById('modalFooter').style.display = 'none';
        }
        function closeModalOutside(e) { if (e.target === document.getElementById('modalOverlay')) closeModal(); }

        // =============================================
        // Outils systeme Fedora KDE
        // =============================================
        function loadSystemTools() {
            const grid = document.getElementById('systemToolsGrid');
            grid.innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
            fetch('/api/tools')
                .then(r => r.json())
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
            fetch('/api/tools/launch/' + encodeURIComponent(toolId), { method: 'POST' })
                .then(r => r.json())
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
        // Display manager (plasma-login-manager)
        // =============================================
        function loadSddmStatus() {
            fetch('/api/sddm/status')
                .then(r => r.json())
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
                    fetch('/api/sddm/sync', { method: 'POST' })
                        .then(r => r.json())
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

        // Pare-feu
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
            fetch('/api/selinux/status')
                .then(r => r.json())
                .then(_renderSelinux)
                .catch(() => { document.getElementById('selinuxMode').textContent = 'Non disponible'; });
        }

        function toggleSelinuxBoolean(name, enable) {
            fetch('/api/selinux/boolean', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ name, enable })
            })
                .then(r => r.json())
                .then(data => {
                    if (data.success) { showToast(data.message || 'Boolean mis a jour', 'success'); _renderSelinux(data); }
                    else { showToast(data.error || 'Erreur', 'error'); loadSelinux(); }
                })
                .catch(() => { showToast('Erreur reseau', 'error'); loadSelinux(); });
        }

        function loadFirewall() {
            fetch('/api/system/firewall')
                .then(r => r.json())
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
                fetch('/api/system/firewall/enable', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) { loadFirewall(); showToast('Pare-feu active', 'success'); }
                        else showToast('Erreur : ' + data.error, 'error');
                    })
                    .catch(err => showToast('Erreur reseau : ' + err, 'error'));
            });
        }

        function firewallDisable() {
            showConfirm('Desactiver le pare-feu ?', 'Le systeme ne sera plus protege par firewalld.', () => {
                fetch('/api/system/firewall/disable', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) { loadFirewall(); showToast('Pare-feu desactive', 'warning'); }
                        else showToast('Erreur : ' + data.error, 'error');
                    })
                    .catch(err => showToast('Erreur reseau : ' + err, 'error'));
            }, true);
        }

        function loadRpmFusion() {
            fetch('/api/fedora/rpmfusion')
                .then(r => r.json())
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

        function rpmFusionEnable() {
            showConfirm('Activer RPM Fusion ?',
                'Les depots free + nonfree seront ajoutes (codecs, pilotes, paquets non libres). Le telechargement est lance en arriere-plan, suivez les logs.',
                () => {
                    const btn = document.getElementById('btnRpmFusionEnable');
                    btn.disabled = true;
                    btn.textContent = 'Activation...';
                    fetch('/api/fedora/rpmfusion/enable', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            if (data.success) {
                                showToast(data.already_enabled ? 'RPM Fusion deja actif' : 'RPM Fusion active', 'success');
                            } else {
                                showToast('Erreur : ' + (data.error || 'echec'), 'error');
                            }
                            loadRpmFusion();
                            loadCodecs();
                            loadNvidia();
                        })
                        .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadRpmFusion(); });
                });
        }

        function loadCodecs() {
            fetch('/api/fedora/codecs')
                .then(r => r.json())
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
                    fetch('/api/fedora/codecs/install', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            if (data.success) {
                                showToast(data.already_installed ? 'Codecs deja installes' : 'Codecs installes', 'success');
                            } else {
                                showToast('Erreur : ' + (data.error || 'echec'), 'error');
                            }
                            loadCodecs();
                        })
                        .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadCodecs(); });
                });
        }

        function loadNvidia() {
            fetch('/api/fedora/nvidia')
                .then(r => r.json())
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
                    fetch('/api/fedora/nvidia/install', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            if (data.success) {
                                showToast(data.already_installed ? 'Pilote NVIDIA deja installe' : 'Pilote NVIDIA installe (redemarrage requis)', 'success');
                            } else {
                                showToast('Erreur : ' + (data.error || 'echec'), 'error');
                            }
                            loadNvidia();
                        })
                        .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadNvidia(); });
                });
        }

        function loadFlathub() {
            fetch('/api/fedora/flathub')
                .then(r => r.json())
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
                    fetch('/api/fedora/flathub/enable', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            if (data.success) {
                                showToast(data.already_enabled ? 'Flathub deja actif' : 'Flathub active', 'success');
                            } else {
                                showToast('Erreur : ' + (data.error || 'echec'), 'error');
                            }
                            loadFlathub();
                        })
                        .catch(err => { showToast('Erreur reseau : ' + err, 'error'); loadFlathub(); });
                });
        }

        function loadLogsHistory() {
            fetch('/api/logs/history')
                .then(r => r.json())
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

        function cancelTask() {
            showConfirm(
                'Annuler la tache en cours ?',
                'Le processus sera interrompu immediatement.',
                () => {
                    fetch('/api/task/cancel', { method: 'POST' })
                        .then(r => r.json())
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

        function clearLogs() {
            document.getElementById('logsContainer').innerHTML = '';
            fetch('/api/logs/clear', { method: 'POST' });
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

        // KDE Settings builder
        let kdeCurrent = {};

        // =============================================
        // CATALOGUE DE THEMES
        // =============================================
        let _themeCatalog = {};
        let _currentThemeTab = 'gtk';

        function reloadAllThemes() {
            showToast('Rechargement des themes...', 'info');
            loadThemeCatalog();
            loadKdeOptions();
        }

        // --- Paquets optionnels ---
        function loadOptionalPackages() {
            const grid = document.getElementById('optionalGrid');
            grid.innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
            fetch('/api/optional/list')
                .then(r => r.json())
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
                fetch('/api/execute/optional_install', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) showToast('Installation optionnelle lancee', 'success');
                        else showToast(data.error || 'Erreur', 'error');
                    })
                    .catch(() => showToast('Erreur reseau', 'error'));
            });
        }

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
            fetch('/api/kde/backups')
                .then(r => r.json())
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
            fetch('/api/kde/backups/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({label})
            })
            .then(r => r.json())
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
                    fetch('/api/kde/backups/restore', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({filename})
                    })
                    .then(r => r.json())
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
                    fetch('/api/kde/backups/delete', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({filename})
                    })
                    .then(r => r.json())
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
        // TWEAKS RAPIDES (Plasma reset, services, audio)
        // =============================================
        function loadTweaks() {
            loadServices();
            loadAudioStatus();
            loadSysctls();
            loadScheduler();
            loadPanel();
            loadZram();
            loadAdminMenu();
            loadDolphin();
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
            fetch('/api/tweaks/scheduler')
                .then(r => r.json())
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
            fetch('/api/tweaks/scheduler/toggle', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ enable, scheduler })
            })
                .then(r => r.json())
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
            fetch('/api/tweaks/sysctls')
                .then(r => r.json())
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
            fetch('/api/tweaks/sysctls/toggle', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ enable })
            })
                .then(r => r.json())
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
                    fetch('/api/tweaks/plasma/reset', {method: 'POST'})
                        .then(r => r.json())
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
                    fetch('/api/tweaks/cache/clear', {method: 'POST'})
                        .then(r => r.json())
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
            fetch('/api/tweaks/services')
                .then(r => r.json())
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
            fetch('/api/tweaks/services/toggle', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, enable})
            })
            .then(r => r.json())
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
            fetch('/api/tweaks/audio')
                .then(r => r.json())
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
            fetch('/api/tweaks/audio/rate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({rate})
            })
            .then(r => r.json())
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
            fetch('/api/tweaks/audio/bt-codecs', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enable})
            })
            .then(r => r.json())
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

        function quitApp() {
            showConfirm('Quitter', 'Fermer FedoraForgeKDE ?', () => {
                fetch('/api/quit', { method: 'POST' })
                    .then(() => {
                        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#666;"><div style="text-align:center;"><h2>FedoraForgeKDE ferme.</h2><p>Vous pouvez fermer cet onglet.</p></div></div>';
                    })
                    .catch(() => {
                        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#666;"><div style="text-align:center;"><h2>FedoraForgeKDE ferme.</h2><p>Vous pouvez fermer cet onglet.</p></div></div>';
                    });
            });
        }

        function loadThemeCatalog() {
            document.getElementById('themeCatalogGrid').innerHTML = '<div style="color: var(--text-muted);">Chargement...</div>';
            fetch('/api/themes/catalog')
                .then(r => r.json())
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
            fetch('/api/themes/install', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type, name, system})
            })
            .then(r => r.json())
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

        // =============================================
        // INSTALLATION PERSONNALISEE DEPUIS MODAL
        // =============================================
        let _modalProfileSlug = null;

        function showProfileDetail(slug) {
            _modalProfileSlug = slug;
            fetch('/api/profiles/' + slug)
                .then(r => r.json())
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
                    fetch('/api/profiles/install-custom', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({apt, flatpak, external, remove})
                    })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) addLog('Installation personnalisee lancee (' + total + ' paquets)');
                        else showToast('Erreur : ' + data.error, 'error');
                    })
                    .catch(err => showToast('Erreur reseau : ' + err, 'error'));
                }
            );
        }

        function loadKdeOptions() {
            fetch('/api/kde/options')
                .then(r => r.json())
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
            fetch('/api/kde/dark-mode', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({dark})
            })
            .then(r => r.json())
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
            fetch('/api/kde/apply', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({settings: getKdeSettings()})
            })
            .then(r => r.json())
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

        // Historique & Rollback
        function loadHistory() {
            fetch('/api/state')
                .then(r => r.json())
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
                fetch('/api/state/rollback/last', { method: 'POST' })
                .then(r => r.json())
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
                fetch('/api/state/rollback/all', { method: 'POST' })
                .then(r => r.json())
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
                fetch('/api/state/clear', { method: 'DELETE' })
                .then(r => r.json())
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

        // Dry-run / Export / Import
        function preflightProfiles() {
            if (selectedProfiles.size === 0) return showToast('Aucun profil selectionne.', 'warning');
            fetch('/api/profiles/preflight', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({profiles: Array.from(selectedProfiles)})
            })
            .then(r => r.json())
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
            fetch('/api/profiles/dry-run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({profiles: Array.from(selectedProfiles)})
            })
            .then(r => r.json())
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
                        fetch('/api/profiles/import', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({profiles: data.profiles})
                        })
                        .then(r => r.json())
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
