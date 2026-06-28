# FedoraForgeKDE

![CI](https://github.com/benjsant/fedora_forge_kde/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Distribution](https://img.shields.io/badge/Fedora%20KDE-41%2B-3c6eb4)
![Plasma](https://img.shields.io/badge/Plasma-6-3c6eb4)

Outil d'**automatisation post-installation** pour **Fedora KDE Plasma Spin** (Fedora Workstation Edition KDE).
Hard fork de [nobara-kde-forge](https://github.com/benjsant/nobara-kde-forge) adapte a Fedora vanilla, qui a moins de pre-configuration que Nobara natif : pas de codecs proprietaires, RPM Fusion a activer, NVIDIA a configurer, et **SELinux garde en enforcing** (Nobara, lui, le desactive au profit d'AppArmor).

Interface web Flask sur `http://localhost:5000` (ou mode CLI). Installe paquets DNF, Flatpaks, paquets externes (VSCode, Docker, Brave...), themes GTK/Plasma/icones/curseurs/Kvantum, configure KDE Plasma, le firewall, le display manager, sauvegarde la config bureau, expose des wizards Fedora (RPM Fusion, codecs, NVIDIA, Flathub), un assistant SELinux et des tweaks rapides.


## Pourquoi ?

Apres une install de Fedora KDE Spin, on refait souvent les memes manipulations : activer RPM Fusion, installer les codecs multimedia, configurer le pilote NVIDIA, ouvrir Flathub complet, ajouter Steam/son IDE/ses themes, regler firewalld... FedoraForgeKDE rassemble ces actions dans une UI cochable avec rollback, backup config et tweaks rapides.

L'objectif : le **confort facon Nobara, mais sur une base Fedora propre et sans baisser la garde securite** (SELinux reste enforcing, avec un assistant dedie pour composer avec).


## Lancement

```bash
# Cloner
git clone https://github.com/benjsant/fedora_forge_kde.git
cd fedora_forge_kde

# Tout-en-un : cree un venv jetable (Flask+Pydantic via pip), sudo, inhibe la
# veille, lance Flask, et propose de supprimer le venv a la sortie.
./fedoraforgeKDE.sh

# Optionnel : installer le raccourci dans le menu KDE
./packaging/install-desktop.sh
```

Aucun paquet Python n'est installe a demeure : l'outil est concu pour etre lance une poignee de fois (run-once) et ne rien laisser sur le systeme. Le seul prerequis non present partout est `python3-pip` (pour bootstrapper le venv) ; le launcher le signale clairement si besoin.

L'UI s'ouvre dans le navigateur. Selectionnez vos profils, cochez les paquets/themes/options, cliquez "Installer".

### Mode CLI (sans interface web)

```bash
.venv/bin/python fedora_kde_forge.py --list-profiles
.venv/bin/python fedora_kde_forge.py --profile gaming,dev
.venv/bin/python fedora_kde_forge.py --profile gaming --dry-run
```

### Desinstallation

```bash
./fedoraforgeKDE.sh --uninstall              # Retire fichiers systeme deposes + venv residuel
./packaging/install-desktop.sh --uninstall   # Retire le raccourci KDE
```

> Note : les **paquets installes ne sont PAS supprimes** par `--uninstall`. Pour ca, utilisez le rollback dans l'UI (`Historique -> Tout annuler`).


## Wizards Fedora

Ce qui differencie FedoraForgeKDE de l'upstream Nobara : des assistants inline pour ce que Nobara pre-configure et que Fedora vanilla laisse a faire.

| Wizard | Role |
|---|---|
| **RPM Fusion** | Active les depots free + nonfree (prerequis des codecs, NVIDIA, mesa-freeworld) |
| **Codecs multimedia** | ffmpeg complet + plugins GStreamer (h264/h265/AAC). Necessite RPM Fusion |
| **NVIDIA** | Pilote proprietaire `akmod-nvidia` + CUDA. Detection GPU + warning Secure Boot |
| **Flathub** | Active le depot Flathub complet (Fedora le livre filtre par defaut) |
| **Assistant SELinux** | Diagnostic des refus AVC + bascule de booleans cibles. Ne desactive jamais SELinux |


## Profils inclus (16)

| Profil | Contenu principal |
|---|---|
| `base` | Outils essentiels : htop/btop/bat/eza, sassc, kvantum, fastfetch, FiraCode, Flatseal, Warehouse |
| `office` | Thunderbird, LibreOffice, xournalpp, OnlyOffice, Joplin, PDFSlicer |
| `communication` | Signal, Element (Matrix), LocalSend, Discord - tous Flatpaks |
| `gaming` | Steam, gamemode, MangoHud, Heroic, Bottles, ProtonPlus, RetroDECK, solaar, gpu-screen-recorder |
| `htpc` | Steam HTPC, Kodi, gamescope (mode salon) |
| `handheld` | gamescope, goverlay, DeckyLoader (mode Steam Deck-like) |
| `dev` | gcc, cmake, gdb, ripgrep, fd, fzf, jq, gh, lazygit, zoxide, nodejs, npm, python3-pip |
| `multimedia` | mpv, krita, kdenlive, audacity, HandBrake, inkscape, OBS, GIMP, vlc, mkvtoolnix |
| `docker` | virt-manager, qemu, libvirt + Docker CE (repo officiel) |
| `distrobox` | podman, distrobox, BoxBuddy |
| `browsers` | Chromium + Brave (repo officiel) |
| `privacy` | firewall-config, ClamAV, WireGuard, KeePassXC, BleachBit, kgpg |
| `vpn` | 7 backends VPN avec integration KDE Plasma |
| `system` | gparted, partitionmanager, timeshift, kdeconnect, scrcpy, hplip-gui |
| `amd` | Pilotes Mesa de base + swap **freeworld** conditionnel (si RPM Fusion actif) |
| `nvidia` | Pilote proprietaire `akmod-nvidia` (garde par RPM Fusion) |

Auto-detection GPU : le profil oppose (NVIDIA si AMD detecte, et vice versa) est **verrouille** sauf confirmation explicite.


## Features

### Installation
- **Profils d'installation** combinables, avec dedoublonnage paquet/Flatpak en session
- **Mode personnalise** : choisir paquet par paquet via le bouton "Detail" sur chaque profil
- **Pre-flight check** : detecte conflits (paquet a installer dans X et a supprimer dans Y), warnings GPU
- **Dry-run** : apercu de ce qui serait installe sans rien faire
- **Snapshot Timeshift** optionnel avant chaque install (si timeshift installe)
- **Rollback** automatique : chaque action enregistree dans `data/state.json`, annulable depuis l'UI

### Configuration bureau
- **Parametres KDE** via `kwriteconfig6` : themes GTK/Plasma/icones/curseur/Kvantum, fonts, espaces de travail, veilleuse, VRR, DRM Leasing (gaming Wayland)
- **Catalogue de themes** installables depuis git : Orchis, Sweet, Layan, Catppuccin (GTK + Kvantum), Tela, Bibata, Phinger, etc.
- **Mode sombre/clair** persistant dans l'UI
- **Plasma Login Manager / SDDM** : detection automatique du DM et synchro theme/curseur/numlock

### Backup & restore config KDE
- Cree des `tar.gz` horodates de la config KDE (~15 fichiers : kdeglobals, kwinrc, plasmarc, panel layout, raccourcis, Kvantum, etc.)
- Etiquettes optionnelles, restauration en 2 clics
- Retention auto a 30 backups max (les plus anciens pruned automatiquement)

### Tweaks rapides
- **Reset Plasma** : kquitapp6 + clear cache + kstart6 (resout les bugs de panel)
- **Vider les caches** : ~/.cache/thumbnails, plasma*, krunner, ksycoca6
- **Services systemd toggleables** : fstrim.timer, bluetooth, cups, sshd, firewalld
- **Audio PipeWire** : sample rate (44.1/48/96/192 kHz) + codecs BT premium (LDAC/aptX-HD/AAC)
- **Sysctls gaming** : split_lock_mitigate=0, max_map_count=16M, tcp_mtu_probing=1 (drop-in /etc/sysctl.d/)

### Diagnostic & monitoring
- **Panneau "Identite systeme"** : kernel, stack graphique (Mesa/Plasma), LSM, etat SELinux, sysctls gaming, btrfs, zram
- **Indicateur services en erreur** dans la status-bar (vert si 0, rouge sinon)
- **Logs SSE temps reel** + historique persistant
- **Avertissement batterie** sur laptop : banniere warning si vous lancez une install sur batterie

### Outils systeme Fedora KDE
FedoraForgeKDE expose les outils GUI standard de Fedora KDE Spin (lances dans la session utilisateur) :
- `plasma-discover` - centre logiciel (apps, Flatpaks, MAJ)
- `systemsettings` - parametres systeme KDE
- `plasma-systemmonitor` - moniteur systeme
- `kinfocenter` - informations materiel/pilotes
- `partitionmanager` - gestion des partitions


## Configuration

Variable d'environnement | Defaut | Effet
---|---|---
`FEDORAFORGEKDE_SCRIPT_TIMEOUT` | `7200` | Timeout des scripts d'installation (secondes)

Tous les autres reglages se font via l'UI ou en editant les JSON dans [`configs/`](configs/). Guide technique complet pour developpeurs et IA : [CLAUDE.md](CLAUDE.md).


## Architecture (resume)

```
fedoraforgeKDE.sh          # Launcher bash : venv jetable + pip, sudo, inhibe veille, lance Flask
fedora_kde_forge.py        # Point d'entree Python (UI ou CLI)
web_app.py                 # Application Flask + blueprints

routes/                    # Blueprints REST
  ├─ legacy.py             # status, logs SSE, execute, theme, system info
  ├─ profiles.py           # /api/profiles/* - install, dry-run, preflight
  ├─ kde_settings.py       # /api/kde/* - kwriteconfig6 + backups
  ├─ themes.py             # /api/themes/* - catalogues GTK/icons/cursors/kvantum
  ├─ tweaks.py             # /api/tweaks/* - plasma reset, services, audio, sysctls gaming
  ├─ system.py             # /api/system/* - firewalld
  ├─ login_manager.py      # /api/sddm/* - plasma-login-manager OU SDDM (auto-detecte)
  ├─ fedora_wizards.py     # /api/fedora/* - RPM Fusion, codecs, NVIDIA, Flathub
  ├─ fedora_tools.py       # /api/tools/* - lancement outils GUI Fedora KDE
  ├─ selinux.py            # /api/selinux/* - assistant SELinux (diagnostic + booleans)
  └─ state_routes.py       # /api/state/* - rollback

utils/                     # subprocess, state, theme_manager, security, sandbox, lockfile,
                           # kde_backup, plasma_tweaks, services_manager, audio_tweaks,
                           # sysctl_tweaks, selinux_manager, system_info, power, etc.
schemas/                   # Modeles Pydantic strict (extra='forbid')
configs/                   # JSON : 16 profils, 4 catalogues themes, paquets DNF/Flatpak
web/                       # Frontend (HTML + Alpine.js + Vanilla JS + CSS)
tests/                     # 13 fichiers de tests pytest (176 tests)
```


## Securite

- **Lock file global** (PID file dans `$XDG_RUNTIME_DIR`) - interdit deux instances simultanees
- **Middleware anti-CSRF / anti-DNS-rebinding** : `Host` strict + `Origin`/`Referer` requis sur POST
- **Sandbox bwrap** des commandes utilisateur (themes installes depuis git)
- **Whitelist stricte** des services systemd toggleables, des booleans SELinux, des fichiers de config KDE backupes
- **Audit log** systematique des commandes externes avec detection de patterns suspects (`eval`, `/dev/tcp`, `curl|bash`, fork bomb, `rm -rf /`, etc.)
- **Validation multi-niveau** sur les backups : regex filename + validation des membres tar (anti path-traversal)
- **SELinux garde enforcing** : aucune action ne fait `setenforce 0` ; l'assistant ne propose que des booleans cibles


## Tester

```bash
# Dans le venv cree par le launcher (ou le votre)
.venv/bin/pip install pytest
.venv/bin/pytest tests/ -v
```

CI GitHub Actions (a venir) : matrix Python 3.10 -> 3.13, compile + ruff + pytest.


## Compatibilite

- ✅ **Fedora KDE Plasma Spin 41, 42, 43**
- ✅ **Plasma 6** (utilise `kwriteconfig6`/`kreadconfig6`)
- ✅ **SELinux enforcing** (compose avec, ne le desactive pas)
- ⚠️ Display manager : SDDM ou plasma-login-manager selon la version de Fedora KDE (auto-detecte)


## Licence

GPL-3.0 - voir [LICENSE](LICENSE).

## Contribuer

Issues et PR bienvenues. Les configs de profils dans `configs/profiles/` sont l'endroit le plus facile pour ajouter de la valeur (un nouveau preset = un JSON valide Pydantic).

## Liens

- Repo : https://github.com/benjsant/fedora_forge_kde
- Projet upstream (Nobara) : [benjsant/nobara-kde-forge](https://github.com/benjsant/nobara-kde-forge)
- Fedora Project : https://fedoraproject.org/
