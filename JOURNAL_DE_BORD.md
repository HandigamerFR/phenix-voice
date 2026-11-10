# Journal de Bord du Développement — Phénix Voice (`phenix-voice`)

> **Règle d'utilisation pour les agents IA** : Ce fichier est la mémoire chronologique complète du projet. À la fin de chaque session (ou à chaque étape clé franchie), ajoutez une nouvelle entrée datée détaillant : ce qui a été fait, les choix techniques ou ergonomiques retenus, les difficultés rencontrées/résolues et l'état exact laissé pour la session suivante. Mettez également à jour [`PROMPT_REPRISE.md`](./PROMPT_REPRISE.md) pour qu'il reflète le nouvel état courant.

---

## Session 1 — 10 Novembre 2026 : Cadrage, Cahier des Charges, Architecture & Initialisation

### 1. Objectif de la session
Débroussailler le projet à partir de zéro avec l'utilisateur, recueillir ses besoins précis liés à son usage quotidien de *Dragon NaturallySpeaking* et à sa situation de handicap moteur avec diction légèrement dysarthrique, concevoir une architecture technique locale adaptée à son matériel, planifier le développement et initialiser le dépôt GitHub.

### 2. Recueil des besoins & Décisions fonctionnelles clés
- **Profil utilisateur** :
  - Utilisateur expert de *Dragon NaturallySpeaking Professional Individual*, handicapé moteur avec une diction légèrement dysarthrique.
  - Utilise un périphérique de pointage/clic de manière fluide (ce qui permet des interfaces hybrides Voix + Souris très efficaces).
  - Possède des compétences en développement logiciel et développe par l'intermédiaire d'agents IA.
- **Points de douleur majeurs identifiés sur Dragon et solutions retenues** :
  1. **Suppression totale de la « Boîte de dictée »** : Obligation d'écrire directement dans 100 % des fenêtres (y compris Electron, OpenCode, navigateurs, terminaux) via un *Shadow Buffer* (tampon mémoire synchronisé) combiné à `SendInput` et `Windows UI Automation`.
  2. **Protection des commandes de correction elles-mêmes** : Si la reconnaissance dérive et que l'utilisateur ne peut plus dire *« Corriger ça »*, il est bloqué. Les commandes de correction doivent donc être personnalisables ET reconnaissables par **empreinte acoustique directe** (indépendamment de la transcription textuelle).
  3. **Lutte contre la dérive du profil vocal (*Profile Drift*)** : Lors d'une correction, il faut pouvoir distinguer deux cas :
     - *Erreur du logiciel* (prononciation habituelle mal reconnue) $\rightarrow$ **Corriger & Apprendre**.
     - *Bafouillage / Toux / Fourche de l'utilisateur* $\rightarrow$ **Corriger SANS apprendre** (commande dédiée type *« Oups / J'ai fourché »* qui corrige le texte mais jette l'audio pour ne jamais polluer le profil), complété par des **Snapshots** (points de restauration) du profil.
  4. **Apprentissage souple de la dysarthrie** :
     - Studio d'étalonnage initial et continu (phonèmes, syllabes, mots, phrases) avec question de validation : *« Avez-vous prononcé normalement sans erreur ? »*.
     - Dictionnaire déterministe prioritaire : *« Si tu entends A, écris toujours B »*.
     - Support de profils selon la fatigue vocale (pour l'utilisateur ou pour l'ouverture du logiciel à d'autres personnes handicapées).
  5. **Modernisation de l'apprentissage du vocabulaire** : Remplacement du connecteur mail obsolète de Dragon par un importateur moderne de documents et d'e-mails envoyés (`.mbox`, `.eml`, IMAP/OAuth, collage) + adaptation au contexte de l'application active.
  6. **Contrôle complet de Windows** : Clics souris vocaux, déplacement souris vocal (*MouseGrid* / UI Automation), gestion des fenêtres et macros vocales, dans l'optique d'un logiciel ouvert et accessible à tous sur des machines moyennes.

### 3. Audit matériel & Décisions architecturales
- **Matériel inspecté sur le PC de développement** :
  - **CPU** : AMD Ryzen 7 3700X (8 cœurs / 16 threads)
  - **RAM** : 16 Go
  - **GPU** : **AMD Radeon RX 5700 XT (8 Go VRAM)**
- **Conséquence architecturale critique** :
  - Pas de GPU NVIDIA $\rightarrow$ Interdiction d'utiliser des bibliothèques dépendant exclusivement de CUDA.
  - Choix d'une stack multi-GPU **Vulkan / DirectML / ONNX** (`whisper.cpp` avec backend Vulkan ou `onnxruntime-directml` pour l'inférence < 400 ms, et `torch-directml` + `PEFT/LoRA` pour le ré-entraînement local sur carte AMD Radeon).

### 4. Nommage et livrables créés lors de cette session
- **Nom choisi pour le projet** : **Phénix Voice** (dépôt GitHub privé : `phenix-voice` sur le compte `HandigamerFR`).
- **Fichiers créés** :
  - `README.md` : Présentation générale et navigation dans la documentation.
  - `docs/CAHIER_DES_CHARGES.md` : Spécifications fonctionnelles complètes (5 modules).
  - `docs/ARCHITECTURE.md` : Architecture technique en 4 étages, stack AMD Vulkan/DirectML, arborescence cible et feuille de route en 6 phases.
  - `JOURNAL_DE_BORD.md` : Ce journal de développement.
  - `PROMPT_REPRISE.md` : Prompt de reprise synthétique prêt à l'emploi pour initialiser les futures sessions IA.
  - `AGENTS.md` : Fichier lu automatiquement par OpenCode pour charger le contexte dès l'ouverture du dossier.
  - `.gitignore` : Exclusion des modèles lourds, environnements virtuels et données vocales privées.

### 5. Prochaine étape prévue (Session 2)
Démarrer la **Phase 1 (Socle Audio, Accélération GPU AMD & Dictée Universelle de base)** :
1. Mettre en place l'environnement Python (`pyproject.toml` / `.venv`).
2. Tester et valider le moteur de transcription local accéléré par la carte **AMD Radeon RX 5700 XT** (mesurer la vitesse de transcription en millisecondes en français).
3. Implémenter la capture microphone avec détection de souffle (*Silero VAD*) et une première dictée directe universelle (`SendInput`) sans boîte de dictée.
