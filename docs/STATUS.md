# Etat du projet (handoff inter-session)

Document vivant : a lire en debut de session pour savoir ou en est le projet, ce
qui est valide, ce qui reste. Le guide technique de reference reste [CLAUDE.md](../CLAUDE.md).
Mettre a jour ce fichier quand une etape majeure change.

Derniere mise a jour : 2026-06-28.

## En une phrase

FedoraForgeKDE = outil de post-installation pour Fedora KDE Plasma Spin, hard fork
de nobara-kde-forge. Confort facon Nobara mais sur base Fedora propre et **SELinux
garde en enforcing** (Nobara, lui, desactive SELinux et passe sur AppArmor).

## Demarrage rapide pour une nouvelle session

1. Lire ce fichier puis [CLAUDE.md](../CLAUDE.md) (architecture, conventions, securite).
2. Env de dev = machine **Nobara** (SELinux Disabled, pas de DNF cible Fedora) :
   les tests systeme reels ne se font pas ici, mais en VM Fedora (voir plus bas).
3. Lancer les tests : creer un venv (`python3 -m venv .venv && .venv/bin/pip install
   flask pydantic pytest ruff`), puis `.venv/bin/pytest tests/` et `.venv/bin/ruff check .`.
4. Conventions de commit : style `Add/Fix/Refactor [Domaine]: bref`, **pas** de
   `Co-Authored-By: Claude` (regle 8 du CLAUDE.md). Pas d'em-dash, francais sans anglicismes.

## Ce qui est FAIT (et teste en mocke / CI)

- **4 wizards Fedora** ([routes/fedora_wizards.py](../routes/fedora_wizards.py), `/api/fedora/*`) :
  RPM Fusion, codecs multimedia, NVIDIA (akmod + Secure Boot), Flathub.
- **Assistant SELinux** ([routes/selinux.py](../routes/selinux.py), [utils/selinux_manager.py](../utils/selinux_manager.py)) :
  diagnostic AVC lecture seule + booleans whitelistes. Jamais `setenforce 0`.
- **Tweaks** ([routes/tweaks.py](../routes/tweaks.py)) : sysctls gaming + scheduler
  **sched-ext** (`scx_lavd`) sur kernel Fedora standard (alternative sure au kernel CachyOS)
  + menu Dolphin "Ouvrir en tant qu'administrateur" ([utils/admin_menu.py](../utils/admin_menu.py),
  installe `kio-admin` comme sur Nobara)
  + zram facon Nobara ([utils/zram_tweaks.py](../utils/zram_tweaks.py) : compression zstd +
  `vm.swappiness=100`, valide en VM Fedora 44)
  + barre des taches fixe/flottante ([utils/panel_tweaks.py](../utils/panel_tweaks.py))
  + Dolphin dossier personnel au demarrage ([utils/dolphin_tweaks.py](../utils/dolphin_tweaks.py), valide en VM)
  + filtre des faux positifs VM (mcelog) dans le compteur `failed_services` de `/api/status`.
- **Outils systeme** ([routes/fedora_tools.py](../routes/fedora_tools.py), `/api/tools/*`) :
  remplace l'ancien `nobara_tools` par Discover/systemsettings/etc.
- **Garde RPM Fusion au preflight** ([routes/profiles.py](../routes/profiles.py)) :
  avertit si un profil contient un paquet RPM Fusion-only (steam, vlc, kodi,
  kodi-inputstream-adaptive, HandBrake-gui) et que RPM Fusion est inactif.
- **Rebranding complet** Nobara -> Fedora (entrypoints, profils, suppression du
  fallback nobara-updater).
- **Launcher** [fedoraforgeKDE.sh](../fedoraforgeKDE.sh) : venv jetable + pip (run-once,
  rien laisse sur le systeme), supprime a la sortie. Plus de uv.
- **CI** GitHub Actions verte (matrix Python 3.10-3.13).
- **Outils de test VM** ([tools/](../tools/)) : voir [tools/CLAUDE.md](../tools/CLAUDE.md).

Etat tests : ~192 pytest verts, ruff clean.

## Ce qui est VALIDE vs PAS ENCORE

- VALIDE : logique Python (tests mockes), CI, validation Pydantic des 16 profils,
  syntaxe bash.
- **PAS valide** : comportement systeme reel (les wizards lancent `dnf`/`sudo`/`systemctl`
  sur un vrai Fedora enforcing). A faire en **VM Fedora 44 KDE** via le harnais SSH.

## Prochaines actions (par priorite)

1. **Valider en VM Fedora 44** : `tools/vm-enable-ssh.sh` dans la VM, puis
   `tools/vm-test-harness.sh user@ip` (et `--mutate` apres snapshot). Voir [tools/CLAUDE.md](../tools/CLAUDE.md).
2. **Paquets incertains** a confirmer via l'audit du harnais (section "Audit paquets profils") :
   `mkvtoolnix-gui`, `goverlay`, `ffmpegthumbnailer`, `lazygit`, `tealdeer`, `corectrl`.
   S'ils manquent sur Fedora : les ajouter a `_RPMFUSION_ONLY` dans [routes/profiles.py](../routes/profiles.py)
   ou basculer en Flatpak/COPR.
2b. **`scx-scheds` (wizard sched-ext)** : confirmer qu'il est dans les depots
   officiels Fedora 44. Sur la machine de dev Nobara il venait du repo tiers `terra`.
   Le wizard echoue proprement s'il est introuvable, mais si stock Fedora ne l'a pas,
   prevoir un COPR. Le harnais le verifie (section sched-ext, repoquery).
3. Optionnel : wizard ROCm (calcul AMD pour l'IA ; support RRDNA2/680M faible, basse priorite).
4. Cosmetique : unifier le nommage `fedorakdeforge` (lockfile/backups) vs `fedoraforgekde`
   (sudoers/launcher).
5. Non implemente, deconseille : wizard kernel CachyOS (seul capable de briquer le boot ;
   preferer le toggle sched-ext deja en place). Details dans [CLAUDE.md](../CLAUDE.md) section Phase 2.

## Historique des PR

- PR #1 (mergee) : implementation complete + CI.
- PR #2 : garde RPM Fusion (preflight) + audit paquets du harnais VM.

## Pieges connus / a ne pas refaire

- Nobara **n'utilise pas RPM Fusion** : depots curatos (`nobara-nvidia-production`
  avec `kmod-nvidia` precompile, `nobara-rocm`, mesa-freeworld via COPR gloriouseggroll).
  Donc l'attribution de repo sur la machine de dev Nobara n'est PAS un proxy fiable
  de la disponibilite sur Fedora vanilla. Verifier sur Fedora (VM / packages.fedoraproject.org).
- Toujours verifier RPM Fusion avant de recommander un paquet `-freeworld`, `nvidia-*`,
  ou multimedia non libre.
- SELinux reste enforcing : ne jamais ajouter de `setenforce 0`, meme avec confirmation.
