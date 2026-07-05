# tools/ : outils de test VM (auto-charge par Claude Code)

Ce dossier contient le necessaire pour valider FedoraForgeKDE sur un **vrai Fedora**
sans toucher la machine de dev (qui est une Nobara, SELinux Disabled). Tout est
pilotable par SSH depuis l'hote.

## Pourquoi une VM et pas une distrobox

- **distrobox** partage le noyau de l'hote : utile UNIQUEMENT pour tester la
  resolution de paquets DNF (RPM Fusion, set de codecs). Ne teste pas SELinux,
  les sysctls, sched-ext, akmod NVIDIA (tout ce qui touche noyau/boot).
- **VM Fedora 44 KDE + snapshot** : indispensable pour le bout-en-bout (SELinux
  enforcing reel, sched-ext, NVIDIA, reboot). C'est la cible de reference.

## Workflow

```bash
# 1. DANS la VM (fraiche), en sudo : prepare SSH + NOPASSWD sudo (requis pour
#    que les 'sudo -n' des wizards marchent pilotes a distance).
sudo ./vm-enable-ssh.sh --pubkey ~/.ssh/id_ed25519.pub
#    -> note l'IP, puis fais un SNAPSHOT "clean"

# 2. SUR l'hote : verifs non destructives (ne modifie pas la VM).
./vm-test-harness.sh tester@192.168.x.x

# 3. SUR l'hote : tests reels (modifie la VM : active RPM Fusion, teste sched-ext).
./vm-test-harness.sh tester@192.168.x.x --mutate
#    -> restaure le snapshot apres si besoin
```

## vm-enable-ssh.sh (a lancer DANS la VM, en root)

Installe/active sshd, ouvre firewalld, gere SELinux (contexte `~/.ssh`, port
SELinux si != 22), configure NOPASSWD sudo (VM jetable), installe la cle publique
si fournie. Idempotent, valide le sudoers via `visudo -c`.

## vm-test-harness.sh (a lancer SUR l'hote)

Deroule en PASS/FAIL/WARN/SKIP : connectivite, identite Fedora, `sudo -n`,
SELinux enforcing, RPM Fusion, codecs (repoquery), NVIDIA (detection + dispo),
sched-ext (et avec `--mutate` : attache reellement scx_lavd ~5s puis le detache),
Flathub, et un **audit de tous les paquets `apt` des profils** (repoquery -> liste
les manquants = paquets Nobara-only/RPM Fusion/COPR a sourcer autrement).

- Non destructif par defaut ; `--mutate` pour les actions reelles (snapshot d'abord).
- Code de sortie 0 si zero FAIL (utilisable en CI plus tard).
- L'audit paquets depend des repos actifs sur la VM : le lancer **avant ET apres**
  `--mutate` pour distinguer "necessite RPM Fusion" de "introuvable partout".

## container-pkg-audit.sh (a lancer SUR l'hote, sans VM)

Audit de **resolution des paquets DNF** dans un conteneur Fedora jetable (podman) :
`./tools/container-pkg-audit.sh [--fedora N] [--no-rpmfusion]`. Attrape la classe
de bugs "paquet inexistant/renomme sur Fedora" que les tests mockes + la CI ne
voient pas (vecu : `kdeconnect`->`kdeconnectd`, `mesa-vdpau-drivers-freeworld`
absent de RPM Fusion).

- Couvre : `apt[]` de tous les profils + install.json + optional_install.json +
  paquets DNF des wizards (codecs, NVIDIA, lus par AST sans importer Flask) +
  variantes mesa freeworld.
- Toute la logique d'ensemble tourne **dans le conteneur** (locale unique, pas de
  mismatch hote/conteneur). Classe chaque manquant en **FAIL** (introuvable, echec
  install garanti) vs **WARN** (nom obsolete mais resolu via Provides, ex
  `wget`->`wget2`, `p7zip`->`7zip`).
- Exit 1 seulement sur un vrai FAIL. **Ne teste PAS** SELinux/sched-ext/akmod/
  runtime -> ca reste le boulot de la VM. C'est le filet "80% des bugs de
  packaging" a lancer avant la VM.

## Si tu pilotes toi-meme (assistant)

Demander a l'utilisateur la cible `user@ip` (et le port si != 22), puis lancer le
harnais via l'outil Bash : `./tools/vm-test-harness.sh user@ip`. Pour copier le
projet dans la VM : `rsync -a ./ user@ip:~/fedora_forge_kde/` ou `git clone`.
