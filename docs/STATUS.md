# Etat du projet (handoff inter-session)

Document vivant : a lire en debut de session pour savoir ou en est le projet, ce
qui est valide, ce qui reste. Le guide technique de reference reste [CLAUDE.md](../CLAUDE.md).
Mettre a jour ce fichier quand une etape majeure change.

Derniere mise a jour : 2026-07-04.

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
  avertit si un profil contient un paquet RPM Fusion-only (steam, vlc, HandBrake-gui)
  et que RPM Fusion est inactif. (kodi retire des profils ; `_RPMFUSION_ONLY` ajuste.)
- **Rebranding complet** Nobara -> Fedora (entrypoints, profils, suppression du
  fallback nobara-updater).
- **Launcher** [fedoraforgeKDE.sh](../fedoraforgeKDE.sh) : venv jetable + pip (run-once,
  rien laisse sur le systeme), supprime a la sortie. Plus de uv.
- **CI** GitHub Actions verte (matrix Python 3.10-3.13).
- **Outils de test VM** ([tools/](../tools/)) : voir [tools/CLAUDE.md](../tools/CLAUDE.md).
- **Harnais paquets en conteneur** ([tools/container-pkg-audit.sh](../tools/container-pkg-audit.sh)) :
  audite la resolution DNF de tous les paquets dans un conteneur Fedora jetable
  (podman), SANS VM. Classe FAIL (introuvable) vs WARN (renomme, resolu via Provides).
- **Catalogue COPR experimental** ([configs/copr.json](../configs/copr.json),
  [routes/copr.py](../routes/copr.py), `/api/copr`) : depots tiers opt-in (lazygit,
  kernel CachyOS) avec disclaimer obligatoire + whitelist + confirmation. Schema
  [schemas/copr.py](../schemas/copr.py).
- **Qualite** (session 2026-06-30) : `log_exc()` ([routes/shared.py](../routes/shared.py),
  traceback au fichier sur les `except` des threads d'install) ; `themes_install`
  n'applique plus rien (install seul).
- **Frontend decoupe + migration `api()` finie** (session 2026-07-03) : app.js
  (2321 lignes) remplace par 7 modules dans [web/static/js/](../web/static/js/)
  (core/profiles/wizards/tweaks/themes/kde/system.js, charges dans l'ordre,
  fonctions globales pour les handlers inline). Plus aucun `fetch()` hors du
  helper `api()`. Smoke test navigateur fait (Firefox headless : rendu complet,
  sections remplies, garde CSRF/Host verifiee sur port non standard).
- **Wizards + COPR en taches de fond** (2026-07-03) : les routes d'action
  (`rpmfusion/enable`, `codecs/install`, `nvidia/install`, `flathub/enable`,
  `copr/enable`) repondent tout de suite (`started: true`) et travaillent dans
  un thread via `start_background_task()` ([routes/shared.py](../routes/shared.py)) :
  fini les requetes HTTP bloquees 15-30 min, et un wizard ne peut plus tourner
  en meme temps qu'une install (slot de tache global, 409 sinon). Les badges UI
  se rafraichissent a la fin de tache (`refreshWizards()`).
- **COPR trace pour rollback** (2026-07-03) : `dnf copr enable` enregistre
  `ACTION_COPR_ENABLE` (rollback `dnf copr disable`) et chaque paquet installe
  est enregistre `ACTION_DNF_INSTALL` (metadata `{"copr": id}`) : l'historique
  et le rollback couvrent desormais les depots tiers.
- **`_stream_sudo` : stdin ferme (DEVNULL)** : si `dnf` pose une question
  malgre `-y` (prompt COPR suspect sur dnf5), echec immediat au lieu d'un hang
  de 15 min.
- **Chemins ancres sur PROJECT_ROOT** ([utils/paths.py](../utils/paths.py)) :
  routes/shared/legacy/themes/copr ne dependent plus du repertoire courant
  (lancement possible depuis n'importe ou).
- **Port configurable** : `FEDORAFORGEKDE_PORT` (defaut 5000) + bascule auto
  sur le port libre suivant si occupe ; le check anti-DNS-rebinding suit le
  port reel ; le launcher choisit le port et ouvre le navigateur dessus.

- **Mise a jour systeme depuis l'UI** (2026-07-04) : bouton "Mettre a jour le
  systeme" (section Outils systeme, `POST /api/system/update`, dnf upgrade
  --refresh en tache de fond via SSE) + pastille "Mises a jour dispo" dans la
  barre de statut (`GET /api/system/updates`, dnf check-update, cache 15 min
  invalide apres upgrade). Avant, la MAJ systeme n'existait que dans le flux
  "Installation complete".
- **CI etendue a Python 3.14** (python systeme de Fedora 43-44 ; l'app a tourne
  sur 3.14.6 en VM le 2026-07-04).

Etat tests : 270 pytest verts, ruff clean.

## Ce qui est VALIDE vs PAS ENCORE

- VALIDE : logique Python (tests mockes), CI, validation Pydantic des 16 profils,
  syntaxe bash.
- VALIDE EN VM Fedora 44 KDE reelle (campagne 2026-06-29, SELinux enforcing) :
  - `--all` complet (MAJ systeme + ~24 paquets + VS Code + nettoyage 15 paquets + flatpaks ;
    themes desormais exclus de `--all`, opt-in) ;
  - wizards **RPM Fusion** (free+nonfree), **codecs** (swap ffmpeg-free -> ffmpeg-libs), **NVIDIA akmod** (resolution) ;
  - flatpaks (install systeme via sudo), themes (Orchis/Sweet/Layan/Catppuccin/Tela/Bibata/phinger).
  - Bugs trouves ET corriges : `sudo -v` non-tty dans `--all`, `run_sudo_command(cwd=)`,
    paquet `kdeconnect`->`kdeconnectd`, flatpak install systeme sans sudo,
    `amd.json` listait `mesa-vdpau-drivers-freeworld` (absent de RPM Fusion F44).
- **DECISION** : les themes ne sont plus installes par les flux "tout installer"
  (`--all` CLI et bouton "Installation complete" web) : on garde le theme par
  defaut (Breeze). L'installation de themes reste opt-in via la section Themes de
  l'UI (`/api/execute/themes_install`). Cela ecarte aussi l'`INTERNAL SCRIPT ERROR`
  d'un install.sh de theme GTK upstream observe en VM (a creuser si quelqu'un
  signale un theme manuel casse).
- **PAS ENCORE** : NVIDIA reel (compilation akmod + boot) non testable sur VM sans
  GPU NVIDIA.

## Prochaines actions (par priorite) - reprise session

1. **nodejs / npm** (WARN de l'audit conteneur) : `dnf install nodejs npm` resout via
   Provides mais `npm` a 3 fournisseurs (nodejs20/22/24-npm, ambigu). Confirmer que
   ca s'installe proprement sur F44, sinon epingler une version dans
   [configs/profiles/dev.json](../configs/profiles/dev.json).
2. **scrcpy** retire de [configs/profiles/system.json](../configs/profiles/system.json)
   (absent de Fedora/RPM Fusion) : re-sourcer via un COPR de confiance ou un Flatpak
   (mirroring Android). Decision utilisateur.
3. **Lancer `tools/container-pkg-audit.sh` regulierement** (remplace la verif
   manuelle des "paquets incertains") et idealement l'ajouter en **CI non-bloquant**
   (job avec un conteneur Fedora). Dernier run : 0 FAIL, WARN nodejs/npm.
4. **`scx-scheds`** (wizard sched-ext) : confirmer le depot officiel F44 (venait du
   repo tiers `terra` sur la Nobara de dev). Sinon -> ajouter au catalogue COPR.
5. Cosmetique : unifier le nommage `fedorakdeforge` (lockfile/backups) vs
   `fedoraforgekde` (sudoers/launcher).
6. Optionnel : wizard ROCm (calcul AMD pour l'IA, basse priorite). Kernel CachyOS :
   desormais dans le catalogue COPR (opt-in, danger boot documente) ; preferer le
   toggle sched-ext.

## Campagne VM 2026-07-04 : COPR reel + wizards async VALIDES

Sur la VM Fedora 44 (dnf5 5.4.2.1, SELinux enforcing), branche `eb2936f` :

- **COPR reel** : `POST /api/copr/enable` (atim/lazygit) -> `dnf copr enable -y`
  passe sur dnf5 **sans hang ni prompt** (12 s au total), lazygit installe.
  Le doute historique sur le `-y` dnf5 est leve.
- **Rollback COPR** : `POST /api/state/rollback/all` retire lazygit PUIS
  desactive le depot (ordre inverse respecte). Verifie par rpm -q + repolist.
- **Wizard RPM Fusion async reel** : reponse immediate (`started: true`),
  tache visible dans /api/status, depots free+nonfree actifs a la fin,
  logs SSE relayes.
- **Verrou anti-concurrence** : codecs/install et copr/enable pendant la tache
  RPM Fusion -> 409 "Tache en cours" comme prevu.
- **Fallback de port reel** : 5000 occupe par un processus tiers -> app sur
  5001 ; check Host/Origin suit le port reel (421 Host etranger, 200 Origin
  localhost:5001). Le lockfile bloque bien une 2e instance de l'app (voulu).
- **Frontend** : les 7 modules JS servis et executes dans la VM (rendu Firefox
  headless, sections et boutons presents).
- Apres les tests : **snapshot `claude-avant-tests-copr` restaure** (VM propre,
  RPM Fusion inactif, depot git a jour sur eb2936f).

## Etat VM / reprise

VM de validation : `ssh cobaye@192.168.122.200` (Fedora 44 KDE, NOPASSWD sudo,
domaine libvirt `fedora_kde_custom-clone` sur l'hote). Restauree au snapshot
propre `claude-avant-tests-copr` (2026-07-04) : RPM Fusion inactif, depot
`~/fedora_forge_kde` a jour, cle SSH de l'hote installee. Si l'acces SSH saute
(revert d'un vieux snapshot), reinjecter une cle via l'agent QEMU :
`virsh set-user-password` (l'agent est confine SELinux, guest-exec ne peut pas
ecrire dans /home) puis `ssh` avec SSH_ASKPASS pour poser la cle.
Pour piloter l'app graphiquement par SSH (navigateur sur l'ecran VM), il faut
injecter l'env de session depuis plasmashell (`/proc/<pid>/environ` :
WAYLAND_DISPLAY/DISPLAY/DBUS_SESSION_BUS_ADDRESS/XDG_RUNTIME_DIR) - les tweaks
user-level (panneau, dolphin) et le lancement du navigateur en dependent.

## Historique des PR

- PR #1 (mergee) : implementation complete + CI.
- PR #2 (ouverte) : garde RPM Fusion, catalogue COPR, wizards asynchrones,
  decoupage frontend. CI verte, campagne VM 2026-07-04 passee.

## Pieges connus / a ne pas refaire

- Nobara **n'utilise pas RPM Fusion** : depots curatos (`nobara-nvidia-production`
  avec `kmod-nvidia` precompile, `nobara-rocm`, mesa-freeworld via COPR gloriouseggroll).
  Donc l'attribution de repo sur la machine de dev Nobara n'est PAS un proxy fiable
  de la disponibilite sur Fedora vanilla. Verifier sur Fedora (VM / packages.fedoraproject.org).
- Toujours verifier RPM Fusion avant de recommander un paquet `-freeworld`, `nvidia-*`,
  ou multimedia non libre.
- SELinux reste enforcing : ne jamais ajouter de `setenforce 0`, meme avec confirmation.
