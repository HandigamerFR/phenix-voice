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

---

## Session 2 — 10 Novembre 2026 : Réalisation et Validation de la Phase 1 (Socle Audio, GPU AMD DirectML < 250 ms & Dictée Universelle)

### 1. Objectif de la session
Construire et valider l'intégralité de la **Phase 1** : initialisation du projet Python, mise au point et optimisation du moteur de transcription local *Whisper Large-v3-Turbo (FP16)* sur la carte graphique **AMD Radeon RX 5700 XT** pour passer sous la barre des `< 400 ms` de latence, découpage par souffle (*Silero VAD*), ponctuation hybride, injection clavier universelle (`SendInput`) et barre flottante *No-Focus* PySide6.

### 2. Travaux réalisés & Optimisations techniques majeures sur le GPU AMD Radeon RX 5700 XT
1. **Environnement Python (`pyproject.toml` & `.venv` sous Python 3.11 64-bit via `uv`)** :
   - Installation de `onnxruntime-directml` (`DmlExecutionProvider` actif sur la Radeon RX 5700 XT), `sounddevice` (microphone détecté : `Microphone (K66)`), `PySide6`, `pynput`, `uiautomation`, `tokenizers`, `onnx`.
   - Correction de l'encodage du fichier `.pth` editable dans `.venv` pour supporter les chemins Windows contenant des caractères accentués (`reconnaissance vocale adaptée`).
2. **Optimisation majeure du moteur GPU AMD (`src/phenix_voice/stt/engine.py` & `mel.py`)** :
   - Modèle retenu : **Whisper Large-v3-Turbo en FP16** (`onnx-community/whisper-large-v3-turbo`, encodeur 32 couches + décodeur 4 couches).
   - **Problème identifié lors du benchmark initial** : Le graphe ONNX standard de l'encodeur Whisper fige la fenêtre d'entrée à **30 secondes fixes (`3000` trames / `1500` tokens)** et copie le cache KV entre CPU et GPU à chaque token décodé, donnant une latence initiale de `~1479 ms`.
   - **Triple optimisation mise en place** :
     1. **Patch dynamique du graphe ONNX de l'encodeur (`build_or_get_dynamic_encoder`)** : Remplacement automatique des cibles `Reshape` figées `[-1, 1500, ...]` par `[0, -1, ...]` dans les 32 couches d'attention et découpage dynamique (`Slice`) de `embed_positions.weight` à la longueur réelle du palier.
     2. **Palier fixe rapide pré-chauffé (`600` trames = 6,0 secondes)** : DirectML conserve en cache le plan d'exécution DirectX12 compilé tant que la forme d'entrée reste constante. Comme 98 % des souffles de dictée durent moins de 5,4 secondes, fixer le palier rapide à `600` trames élimine toute recompilation de shaders entre les phrases.
     3. **Zero-Copy GPU IOBinding (`dml`, device 0)** : Les états cachés de l'encodeur (`last_hidden_state`) et tout le cache KV (`past_key_values` encodeur et décodeur) restent à 100 % dans la VRAM de la Radeon RX 5700 XT d'un bout à l'autre du décodage.
   - **Résultat du benchmark sur l'AMD Radeon RX 5700 XT** :
     - Commande / souffle court (`1,75 s`, ex. *« Corriger ça. »*) : **197 ms** de bout en bout.
     - Phrase complète (`4,30 s`, ex. *« Bonjour, je dicte directement dans la fenêtre active. »*) : **251 ms** de bout en bout (soit un gain de **6x** par rapport aux `1479 ms` initiaux, largement sous la cible `< 400 ms`).
   - Extraction simultanée des **alternatives proches** (`TranscriptionResult.alternatives`) dès le décodage pour préparer la barre de correction de la Phase 2.
3. **Capture Microphone & Découpage par souffle (`src/phenix_voice/audio/vad.py` & `capture.py`)** :
   - Intégration de **Silero VAD v5 ONNX** (`< 0,2 ms` par bloc de 32 ms) et du découpeur `BreathSegmenter` avec pré-tampon de `288 ms` (pour ne jamais couper la première consonne) et détection de micro-pause à `384 ms`.
4. **Post-Processeur de Ponctuation Hybride & Routeur (`src/phenix_voice/postprocess/punctuation.py`)** :
   - Prise en charge de la ponctuation parlée française (*« point »*, *« virgule »*, *« point à la ligne »*, *« nouveau paragraphe »*, *« point d'interrogation »*, *« point d'exclamation »*, *« deux-points »*, *« ouvrir/fermer les guillemets »*...) combinée à la ponctuation automatique de Whisper et à la gestion de l'espacement inter-souffles.
   - Commandes vocales système de base : *« Au repos »* (mise en veille), *« Écoute »* (sortie de veille), *« Oups / Effacer ça / Rayez ça »* (effacement immédiat du dernier souffle).
5. **Injection Directe Universelle & Barre Flottante No-Focus (`src/phenix_voice/os_control/` & `ui/hud.py`)** :
   - `DirectTextInjector` : Injection clavier Unicode directe via `Win32 SendInput` par lots + pile d'annulation du dernier souffle (`VK_BACK`).
   - `PhenixHUD` : Barre flottante PySide6 avec style étendu Win32 `WS_EX_NOACTIVATE | WS_EX_TOPMOST` permettant de cliquer à la souris sur *[Pause / Actif (F8)]* ou *[⌫ Effacer souffle (« Oups »)]* **sans jamais voler le focus clavier de la fenêtre cible**.
6. **Tests automatisés (`tests/test_phase1.py`)** :
   - 3 suites de tests unitaires et d'intégration GPU passées avec succès (`3 passed`).

### 3. Prochaine étape prévue (Phase 2)
Démarrer la **Phase 2 (Shadow Buffer, Sélection Vocale sur place & Interface de Correction Anti-Dérive)** :
1. Implémenter le *Shadow Buffer* complet en RAM conservant les derniers segments dictés avec leur texte, position relative, alternatives phonétiques et extrait audio `.wav` en mémoire.
2. Implémenter les commandes vocales *« Sélectionner [mot] »*, *« Corriger ça »* et *« Corriger [mot] »* directement dans la fenêtre active (`Shift + Flèches` / `UI Automation`).
3. Enrichir le HUD No-Focus avec le volet de correction hybride (alternatives numérotées *« Choisir 1, 2, 3... »* ou cliquables à la souris) et les deux boutons/commandes distincts : **« Corriger & Apprendre »** vs **« Corriger SANS apprendre (Oups / J'ai fourché) »**.
4. Ajouter la protection par **empreinte acoustique directe** (MFCC + DTW) des commandes vitales (*« Corriger ça »*, *« Oups »*, *« Au repos »*).
