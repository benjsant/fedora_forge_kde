# FedoraForgeKDE

Outil d'automatisation post-installation pour **Fedora KDE Plasma Spin** (Fedora Workstation Edition KDE).
Hard fork du projet [nobara-kde-forge](https://github.com/benjsant/nobara-kde-forge) adapte a Fedora vanilla, qui a moins de pre-configuration que Nobara out-of-the-box (pas de kernel patche, pas de codecs proprietaires, RPM Fusion a activer, NVIDIA a configurer, etc.).

> **Nouvelle session ?** Lire d'abord [docs/STATUS.md](docs/STATUS.md) (etat du projet : fait / valide / a faire) puis revenir ici pour les details techniques. Le workflow de test VM est dans [tools/CLAUDE.md](tools/CLAUDE.md).

## Lancement

```bash
# Lancer : le script gere tout (cree un venv temporaire, installe Flask+Pydantic
# via pip dedans, lance Flask, et propose de supprimer le venv a la sortie).
# Aucun paquet Python n'est installe a demeure sur le systeme (outil run-once).
./fedoraforgeKDE.sh                           # Tout-en-un (venv, sudo, inhibe veille, lance Flask)
./fedoraforgeKDE.sh --uninstall               # Retire les fichiers systeme + le venv residuel

# Equivalent direct (necessite Flask/Pydantic dans l'env courant : activer le
# venv cree par le launcher, ou `python3 -m venv .venv && .venv/bin/pip install flask pydantic`)
.venv/bin/python fedora_kde_forge.py

# Mode CLI (sans Flask web, mais Pydantic requis pour valider les profils)
.venv/bin/python fedora_kde_forge.py --list-profiles
.venv/bin/python fedora_kde_forge.py --profile gaming,dev
.venv/bin/python fedora_kde_forge.py --profile gaming --dry-run

# Tests (dev) : dans le venv
.venv/bin/pip install pytest
.venv/bin/pytest tests/
```

Interface web Flask sur `http://localhost:5000`.

### Variables d'environnement

- `FEDORAFORGEKDE_SCRIPT_TIMEOUT` : timeout (secondes) des scripts d'installation lances via `/api/execute/*`. Defaut : 7200 (2h).

### Differences cles vs nobara-kde-forge

| Aspect | nobara-kde-forge | fedora-kde-forge |
|---|---|---|
| Cible | Nobara Linux 41+ KDE | Fedora KDE Spin 41+ |
| Install dependances | `uv sync` (uv installe via DNF/curl/pip) | venv temporaire + `pip install flask pydantic`, supprime a la sortie |
| Build/venv | Oui (.venv/ persistant) | venv .venv/ jetable (run-once, aucun paquet Python a demeure) |
| Outils integres | `nobara-welcome`, `nobara-driver-manager`, etc. | Remplaces par wizards inline (RPM Fusion, NVIDIA, codec) |
| Repos pre-configures | `nobara`, `nobara-updates`, `nobara-rocm`, etc. | Fedora vanilla + RPM Fusion (a activer via wizard) |
| Kernel | Custom Nobara (CachyOS+BORE+NTSYNC) | Standard Fedora (pas de patches detectes par defaut) |
| Sysctls gaming | Pre-configures par `nobara-login-sysctl` | Toggle UI (section Tweaks, drop-in /etc/sysctl.d/) |
| Codecs | `mesa-*-freeworld` direct dans profil AMD | RPM Fusion required avant, wizard codec inline |
| `nobara-updater` fallback dans `system_update()` | Oui | Non, DNF direct uniquement |
| Display Manager | plasma-login-manager (Nobara 42+) | SDDM ou plasma-login-manager selon Fedora KDE version |
| SELinux | Desactive, AppArmor a la place | Enforcing par defaut (compose avec, assistant dedie) |

## Packaging

Le projet a un layout "flat" : `routes/`, `scripts/`, `utils/`, `schemas/` sont des packages a la racine. `pyproject.toml` les declare via `[tool.hatch.build.targets.wheel]`. Pas de uv requis : le launcher cree un venv jetable et y installe Flask/Pydantic via pip (wheels PyPI, ~3s, ~28 Mo), puis propose de le supprimer a la sortie. Aucun paquet Python n'est laisse sur le systeme.

Les scripts dans `scripts/` sont invoques depuis Flask via `python -m scripts.<name>` (charge `scripts/__init__.py` qui configure `sys.path`). Pour execution CLI directe (`python scripts/X.py`), chaque script garde un fallback `if __package__ in (None, "")` pour rester autonome.

## CI

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) : matrix Python 3.10-3.13, install Flask/Pydantic via pip (CI sur ubuntu n'a pas DNF), `compileall`, ruff check, pytest, `bash -n` sur le launcher, validation JSON.

## Securite

- **Lock file global** ([utils/lockfile.py](utils/lockfile.py)) : `$XDG_RUNTIME_DIR/fedorakdeforge.lock` (fallback `/tmp/`) contient le PID Flask. Empeche 2 instances simultanees (sinon race sur DNF lock / `data/state.json`). Signal handlers SIGTERM/SIGINT pour nettoyage propre.
- **Anti-CSRF / DNS-rebinding** ([utils/security.py](utils/security.py)) :
  - Header `Host` doit etre `localhost[:port]` ou `127.0.0.1[:port]` (sinon 421).
  - Sur POST/PUT/DELETE : `Origin` ou `Referer` doit avoir un host autorise (sinon 403).
  - GET reste ouvert (favoris/refresh navigateur).
- **Sandbox des commandes user** ([utils/sandbox.py](utils/sandbox.py)) :
  - `bwrap` enveloppe les `cmd_user` des themes : FS read-only sauf `~/.themes`, `~/.icons`, `~/.local`, `~/.config` et le clone path. PID/UTS namespace isoles, network garde.
  - Non applicable aux commandes avec `sudo` : audit log systematique + `looks_dangerous()` detecte patterns suspects (`eval`, `/dev/tcp`, `curl|bash`, fork bomb, `rm -rf /`, etc.).
  - Fallback transparent si `bwrap` absent.
- **Backup config KDE** ([utils/kde_backup.py](utils/kde_backup.py)) : whitelist stricte de 15 fichiers (`kdeglobals`, `kwinrc`, `plasmarc`, panel layout, raccourcis, Kvantum, etc.) dans `~/.local/share/fedorakdeforge/backups/`. Filename valide par regex stricte. A la restauration, chaque membre du tar est filtre contre la whitelist + check `..`/chemin absolu. Retention max 30 backups (auto-prune).
- **Whitelist services systemd** ([utils/services_manager.py](utils/services_manager.py)) : seuls `fstrim.timer`, `bluetooth`, `cups`, `sshd`, `firewalld` sont toggleables depuis l'UI.

## SELinux : composer avec

Contrairement a Nobara (qui **desactive SELinux et bascule sur AppArmor** - confirme : `cat /sys/kernel/security/lsm` sur Nobara liste `apparmor`, pas `selinux`, et `getenforce` renvoie `Disabled`), **Fedora garde SELinux enforcing par defaut**. C'est la proposition de valeur du projet : confort facon Nobara mais sans baisser la garde. Plusieurs consequences :

1. **Wine/Proton** peuvent generer des denials AVC. Si l'utilisateur signale des crashes Wine, lui suggerer `journalctl -t setroubleshoot --since "10 min ago"` pour voir les blocages.
2. **Docker setup** peut necessiter `--security-opt label=disable` ou la creation d'un boolean SELinux dedie.
3. **Premier lancement de certaines apps** declenche des AVC silencieux mais l'app marche. Documenter dans le troubleshooting.

Le code ne desactive PAS SELinux meme avec confirmation utilisateur, et ne fait jamais `setenforce 0`.

**Assistant SELinux** ([utils/selinux_manager.py](utils/selinux_manager.py), [routes/selinux.py](routes/selinux.py)) : materialise cette ligne. Expose le mode courant, un diagnostic en lecture seule des denials AVC recents (via journald `setroubleshoot`), et la bascule **persistante** (`setsebool -P`) de booleans strictement whitelistes (`container_use_devices`, `container_manage_cgroup`, `selinuxuser_execmod`, `use_nfs_home_dirs`, `virt_use_nfs`). Aucune valeur de boolean arbitraire venue du client n'est acceptee. Degrade proprement si SELinux est Disabled (cas de la machine de dev Nobara).

## Pre-commit

```bash
sudo dnf install -y pre-commit
pre-commit install
```

Hooks configures ([.pre-commit-config.yaml](.pre-commit-config.yaml)) : trailing whitespace, EOF fixer, check-yaml/json, check-merge-conflict, ruff (lint + autofix), validation Pydantic des profils.

## Raccourci KDE

```bash
./packaging/install-desktop.sh                # Installe fedora-kde-forge.desktop dans ~/.local/share/applications/
./packaging/install-desktop.sh --uninstall    # Retire le raccourci
```

L'app apparait ensuite dans le menu Plasma sous le nom "FedoraForgeKDE".

## Architecture

```
fedora_kde_forge/
├── fedoraforgeKDE.sh        # Script d'entree bash (installe deps via DNF, sudo, inhibe veille, lance Flask)
├── fedora_kde_forge.py      # Point d'entree Python (verifie pre-requis puis lance web_app)
├── web_app.py               # Application Flask, enregistre les blueprints
├── start.sh                 # Alias vers fedoraforgeKDE.sh
├── pyproject.toml           # Config build (Flask, Pydantic)
│
├── routes/                  # Blueprints Flask (API JSON + SSE logs)
│   ├── __init__.py
│   ├── shared.py            # Logger SSE, fonctions communes, notify-send
│   ├── legacy.py            # /api/status (+ failed_services), /api/system/info, /api/execute/*, /api/theme/*
│   ├── profiles.py          # /api/profiles/*
│   ├── kde_settings.py      # /api/kde/* + /api/kde/backups/* (cycle backup KDE)
│   ├── login_manager.py     # /api/sddm/* (gere plasma-login-manager OU SDDM selon detection)
│   ├── system.py            # /api/system/* (firewalld)
│   ├── themes.py            # /api/themes/* (catalogues GTK/icon/cursor/kvantum)
│   ├── state_routes.py      # /api/state/* (rollback)
│   ├── fedora_wizards.py    # /api/fedora/* : RPM Fusion, codecs, NVIDIA, Flathub (faits)
│   ├── selinux.py           # /api/selinux/* : assistant SELinux (status, diagnostic AVC, toggle booleans)
│   └── tweaks.py            # /api/tweaks/* (reset plasma, services systemd, audio PipeWire/BT, sysctls gaming, scheduler sched-ext)
│
├── scripts/                 # Logique d'installation (appeles par les routes)
│   ├── __init__.py
│   ├── dnf_install.py, dnf_remove.py, flatpak_install.py
│   ├── external_install.py, optional_install.py
│   ├── profile_install.py
│   └── themes_install.py
│
├── utils/                   # Utilitaires
│   ├── subprocess_utils.py  # run_command, dnf_install/remove/update, rpm -q (PAS de nobara-updater fallback)
│   ├── state_manager.py     # Actions: ACTION_DNF_INSTALL, ACTION_DNF_REMOVE, rollback. Cap MAX_ENTRIES=500.
│   ├── logging_utils.py     # Logger CLI mode
│   ├── file_utils.py        # JSON, fichiers, ConfigManager
│   ├── validation.py        # Validation Pydantic des configs
│   ├── profile_loader.py    # Charge les profils depuis configs/profiles/
│   ├── theme_manager.py     # ThemeManager (KDE Plasma + Kvantum)
│   ├── security.py          # Anti-CSRF / anti-DNS-rebinding middleware Flask
│   ├── sandbox.py           # bwrap wrapper + detection patterns dangereux
│   ├── lockfile.py          # Lock file global (PID file + signal handlers)
│   ├── power.py             # Detection batterie (sysfs) -> warning UI
│   ├── kde_backup.py        # Backup/restore config KDE. MAX_BACKUPS=30.
│   ├── plasma_tweaks.py     # Reset plasmashell + clear caches
│   ├── services_manager.py  # Toggle services systemd whitelistes
│   ├── audio_tweaks.py      # PipeWire sample rate + codecs BT premium (drop-in user-level, atomic write)
│   ├── sysctl_tweaks.py     # Sysctls gaming (drop-in /etc/sysctl.d/, sudo via tee/rm + sysctl --system)
│   ├── sched_ext.py         # Scheduler sched-ext gaming (scx_lavd) sur kernel Fedora standard, unit systemd geree
│   ├── selinux_manager.py   # Assistant SELinux : mode, booleans whitelistes (setsebool -P), denials AVC. Jamais setenforce 0
│   └── system_info.py       # Detection identite Fedora (kernel vanilla, LSM, SELinux, btrfs, zram, cache 30s)
│
├── schemas/                 # Modeles Pydantic (extra='forbid')
│   ├── __init__.py
│   ├── packages.py, flatpak.py, external.py, themes.py, profile.py
│
├── configs/                 # Fichiers JSON de configuration
│   ├── install.json         # Paquets RPM a installer
│   ├── remove.json          # Paquets RPM a supprimer
│   ├── flatpak.json         # Flatpaks a installer
│   ├── external_packages.json
│   ├── optional_install.json
│   ├── themes_gtk.json, themes_icons.json, themes_cursors.json, themes_kvantum.json
│   ├── theme_config_recommended.json
│   └── profiles/            # 16 profils adaptes Fedora
│       ├── base.json, gaming.json, dev.json, multimedia.json, office.json
│       ├── docker.json, distrobox.json, browsers.json, privacy.json
│       ├── vpn.json, system.json, amd.json, nvidia.json
│       ├── communication.json, htpc.json, handheld.json
│
├── web/                     # Frontend (HTML + Vanilla JS + Alpine.js + CSS)
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css    # Palette bleu Fedora (#3c6eb4 primary) au lieu du violet Nobara
│       └── js/app.js
│
└── tests/                   # Tests pytest
    ├── test_schemas.py            # Validation Pydantic round-trip
    ├── test_app_smoke.py          # Boot Flask + ping endpoints
    ├── test_security.py           # Host/Origin/CSRF + lockfile
    ├── test_sandbox.py            # bwrap + looks_dangerous
    ├── test_power.py              # Detection batterie sysfs
    ├── test_kde_backup.py         # Cycle backup KDE + path traversal + retention
    ├── test_plasma_tweaks.py      # clear_caches + reset (mocke)
    ├── test_services_manager.py   # Whitelist + parsing systemctl
    ├── test_audio_tweaks.py       # Drop-in PipeWire/WirePlumber
    ├── test_sysctl_tweaks.py      # Drop-in sysctls gaming + route toggle
    ├── test_sched_ext.py          # Scheduler sched-ext : whitelist, unit, parsing sysfs, routes
    ├── test_selinux.py            # Assistant SELinux : booleans whitelist + parsing + routes
    ├── test_system_info.py        # Parsing OS/kernel/btrfs/zram
    └── test_fedora_wizards.py     # RPM Fusion, codecs, NVIDIA, Flathub (faits)
```

## Specificites Fedora a implementer (Phase 2)

Ces features differencient le projet de nobara-kde-forge et sont propres a Fedora vanilla. **Aucune n'est implementee dans le bootstrap, ce sont les TODOs prioritaires.**

### Wizard RPM Fusion (`routes/fedora_wizards.py:rpmfusion`)

Active les depots free + nonfree de RPM Fusion. C'est le prerequis pour quasi tous les autres wizards (NVIDIA, codecs, mesa-freeworld) :

```bash
sudo dnf install -y \
  https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
  https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
```

Detecte si deja active via `dnf repolist | grep -E 'rpmfusion-(free|nonfree)'`. UI : carte avec bouton "Activer", warning sur SELinux enforcing qui peut bloquer certains paquets nonfree.

### Wizard codecs multimedia

Apres RPM Fusion active, install :

```bash
sudo dnf install -y \
  ffmpeg-libs gstreamer1-plugins-bad-free gstreamer1-plugins-bad-free-extras \
  gstreamer1-plugins-good gstreamer1-plugins-good-extras gstreamer1-plugins-base \
  gstreamer1-plugin-libav gstreamer1-plugins-ugly
sudo dnf groupupdate -y multimedia --setop="install_weak_deps=False" \
    --exclude=PackageKit-gstreamer-plugin
sudo dnf groupupdate -y sound-and-video
```

Equivalent de `nobara-codec-wizard` mais inline.

### Wizard NVIDIA proprietaire

Apres RPM Fusion active :

```bash
sudo dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda
```

Detection auto carte NVIDIA via `lspci`. UI : warning si Secure Boot detecte (`mokutil --sb-state`) avec guidage signature manuelle mokutil.

### Wizard Flathub

Fedora Workstation 41+ a Flathub partiellement (filtered remote). Pour avoir Flathub complet :

```bash
flatpak remote-modify --no-filter --enable flathub
# OU si Flathub absent :
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

### Sysctls gaming optionnels (fait)

Applique les memes sysctls que Nobara (split_lock_mitigate=0, max_map_count=16M, tcp_mtu_probing=1) via toggle UI dans la section Tweaks. Implemente dans [utils/sysctl_tweaks.py](utils/sysctl_tweaks.py) (drop-in `/etc/sysctl.d/99-fedorakdeforge-gaming.conf` ecrit via `sudo -n tee`, recharge `sysctl --system`). Routes `/api/tweaks/sysctls` + `/api/tweaks/sysctls/toggle`. Pas de sudoers dedie : repose sur le cache sudo du launcher, comme les wizards DNF.

### Scheduler sched-ext (fait) - alternative recommandee au kernel CachyOS

Le kernel Fedora (>= 6.12) embarque deja `sched_ext` (`CONFIG_SCHED_CLASS_EXT=y`, verifie). On attache donc un scheduler eBPF gaming/latence (`scx_lavd`, paquet `scx-scheds`) **sur le kernel Fedora standard**, sans le remplacer. Implemente dans [utils/sched_ext.py](utils/sched_ext.py) + routes `/api/tweaks/scheduler[/toggle]` (section Tweaks).

Pourquoi c'est le bon choix (gaming + dev IA) :
- on recupere ~80% du gain d'interactivite de CachyOS (BORE) sans toucher au noyau ;
- **aucun risque de boot** : watchdog noyau qui detache le scheduler s'il defaille, retour au scheduler par defaut ;
- reversible a chaud, NVIDIA/CUDA (akmod) intacts - or l'IA est GPU-bound, le scheduler CPU n'y change rien ;
- whitelist stricte de schedulers (`scx_lavd`/`scx_bpfland`/`scx_rusty`), unit systemd geree par l'app (`fedoraforge-scx.service`), nettoyee a la desactivation.

### Kernel CachyOS optionnel (avance, non implemente - deconseille par defaut)

Via COPR `bieszczaders/kernel-cachyos` (`kernel-cachyos` + `kernel-cachyos-devel-matched`). Gains reels mais modestes (single-digit % FPS) ; c'est le **seul** wizard capable de briquer le boot :
- Secure Boot : kernel non signe Fedora -> "bad shim signature", signature MOK requise.
- NVIDIA + Secure Boot : le kernel CachyOS manque certaines options IMA -> le module NVIDIA signe MOK peut ne pas charger (no boot). Support nvidia prebuilt retire du COPR -> RPM Fusion akmod.
- Verifier que SELinux reste enforcing avec ce kernel.
Si implemente un jour : opt-in avance strict, snapshot timeshift force, detection Secure Boot (reutilise le wizard NVIDIA), refus/avertissement si Secure Boot + NVIDIA. Tester en VM d'abord. **Preferer le toggle sched-ext ci-dessus.**

Note modele Nobara (explore) : Nobara n'utilise PAS RPM Fusion. Depots curatos `nobara-nvidia-production` (avec `kmod-nvidia` **precompile**, instantane), `nobara-rocm`, mesa-freeworld par defaut via COPR `gloriouseggroll`. Fedora vanilla n'a que l'akmod (compile au 1er boot) cote NVIDIA.

### Profils a adapter pour Fedora

- `amd.json` : enlever variants `-freeworld` du nom de paquet de base. Detecter si RPM Fusion active, et installer conditionnellement les variants freeworld qui apportent les codecs.
- Suppression toute reference a `nobara-driver-manager` dans `external` (utiliser le wizard NVIDIA inline).
- Adapter les commandes externes des profils Docker/Brave qui mentionnent specifiquement Nobara.

## Conventions

- Le champ `"apt"` dans les JSON profils contient des paquets DNF/RPM (nom herite de minty_forge pour compat structure)
- Les routes KDE settings utilisent un `_SETTINGS_MAP` mappant chaque setting a un tuple `(fichier_kde, groupe, cle)`
- Le state manager utilise `ACTION_DNF_INSTALL` / `ACTION_DNF_REMOVE` pour le rollback
- Les logs SSE sont envoyes via `/api/logs/stream`
- Frontend communique avec `/api/kde/*` et `/api/sddm/*` (prefixe garde pour compat, gere plasma-login OU SDDM selon detection)
- `system_update()` ([utils/subprocess_utils.py](utils/subprocess_utils.py)) utilise `dnf check-update` + `dnf upgrade` directement (pas de `nobara-updater` fallback)
- Sudoers temporaire `/etc/sudoers.d/fedorakdeforge` (NOPASSWD pour `firewall-cmd`) cree au lancement et supprime via `trap cleanup EXIT`
- Snapshot timeshift optionnel avant `/api/profiles/install` si timeshift dispo (`data.checks.timeshift`)

## Pour AI assistants travaillant sur ce projet

Quelques points specifiques a garder en tete :

1. **Toujours verifier la presence de RPM Fusion** avant de recommander un paquet `-freeworld`, `nvidia-*`, ou multimedia non-free. La detection se fait via `dnf repolist | grep -E 'rpmfusion-(free|nonfree)'`.

2. **Le kernel detection dans `utils/system_info.py`** est conservee mais il est normal qu'aucun patch (CachyOS/BORE/NTSYNC) ne soit detecte sur Fedora vanilla. Le panneau identite affichera "Kernel X.Y.Z" sans suffixe patches.

3. **SELinux est enforcing par defaut sur Fedora**. Contrairement a Nobara qui le desactive, ici il faut composer avec. Quelques commandes externes (notamment Docker repos) peuvent declencher des AVC. Le wizard NVIDIA en particulier doit avertir des consequences.

4. **Le display manager** est SDDM par defaut sur Fedora KDE Spin (Fedora 42+ peut avoir migre vers plasma-login-manager). Le code de `routes/login_manager.py` detecte les deux et adapte.

5. **Pas de `nobara-*` commands** dans le PATH. Le blueprint `nobara_tools.py` du projet upstream a ete remplace par [routes/fedora_tools.py](routes/fedora_tools.py) (`/api/tools/*`) qui pointe vers les outils GUI standard de Fedora KDE (`plasma-discover`, `systemsettings`, `plasma-systemmonitor`, `kinfocenter`, `partitionmanager`). Pour les pilotes/codecs/depots, ce sont les wizards Fedora inline (`/api/fedora/*`).

6. **uv n'est PAS requis** pour ce projet. Le launcher cree un venv temporaire (`.venv/`) et installe Flask/Pydantic via pip, puis propose de le supprimer a la sortie (outil run-once : rien laisse a demeure). En non-interactif le venv est conserve. `--uninstall` supprime le venv residuel. Pour contribuer en local, tu peux utiliser ce venv OU le tien (uv/pip).

7. **Conventions de commit** : suivre le style "Add/Fix/Refactor/Update/Remove [Domain]: brief". Voir l'historique du projet upstream pour reference.

8. **Pas de `Co-Authored-By: Claude`** dans les commits (style cleanup, leve dans la phase de polish doc du projet upstream).

9. **Em-dashes (—) interdits dans la doc** (decision style projet, remplaces par tirets simples partout).

10. **Style français pur** : eviter les anglicismes facilement traduisibles (`trade-off` -> `compromis`, `best-effort` -> `meilleur effort`, `out-of-the-box` -> `natif`, `defense en profondeur` -> `validation multi-niveau`).

## Projet upstream

Le code source de **nobara-kde-forge** (projet original) se trouve sur :
https://github.com/benjsant/nobara-kde-forge

Les bugfixes utiles peuvent etre cherry-picked manuellement via `git format-patch`.
