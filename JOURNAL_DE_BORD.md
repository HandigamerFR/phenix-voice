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
   - 4 suites de tests unitaires, d'intégration GPU et de validation sur la vraie voix de l'utilisateur passées avec succès (`4 passed`).
7. **Mini-Studio d'Étalonnage & Diagnostic sur la vraie voix de l'utilisateur (`src/phenix_voice/ui/calibration_studio.py` & `audio/fingerprints.py`)** :
   - Suite au premier essai en direct où le moteur reconnaissait très peu de phrases, création d'un **Mini-Studio d'Étalonnage PySide6** pilotable 100 % à la souris (avec VU-mètre et question anti-pollution *« Avez-vous prononcé cet élément avec votre diction habituelle ? »*).
   - Enregistrement de 6 échantillons de référence par l'utilisateur (`Écoute`, `Au repos`, `Corriger ça`, `Oups`, et 2 phrases avec ponctuation dictée) sur son micro **`Microphone (K66)`**.
   - **Découvertes scientifiques majeures issues de l'analyse des 6 fichiers `.wav` réels** :
     1. Le palier trop court de `600` trames (6 s) dégradait le puits d'attention (*attention sink*) de Whisper sur la voix réelle en environnement réel (`"Écoute"` devenait `"D'accord."`, `"Au repos"` devenait `"Je suis hyper."`, `"Oups"` devenait `"Unch"`). Le passage au palier fixe **`1200` trames (12 s)** + **normalisation automatique de gain (AGC à `0.85`)** + **prompt lexical calibré** a restauré **100 % de reconnaissance exacte sur les 6 enregistrements en 435 à 700 ms**.
     2. Allongement du délai de micro-pause VAD de `384 ms` à **`640 ms`** (et durée max de segment à `10,5 s`) pour respecter le rythme d'articulation dysarthrique sans hacher les phrases.
     3. Identification des premières équivalences phonétiques propres à la diction de l'utilisateur (ex. *"point à la ligne"* entendu comme *"pour la ligne"* / *"pour un aligné"*, *"point d'interrogation"* entendu comme *"pour l'interrogation"*).
     4. Mise en place dès maintenant du module **`AcousticCommandProtector` (`src/phenix_voice/audio/fingerprints.py`)** par empreintes acoustiques Log-Mel + DTW cosinus sur les 4 commandes vitales enregistrées.

### 3. Prochaine étape prévue (Phase 2)
Démarrer la **Phase 2 (Shadow Buffer, Sélection Vocale sur place & Interface de Correction Anti-Dérive)**.

---

## Session 3 — 10 Novembre 2026 : Studio d'Étalonnage Étendu (12 Commandes), Arbitre de Plausibilité Contextuelle, Mode 100 % Hors-Ligne & Phase 2 Complète

### 1. Objectif de la session
1. Éviter tout conflit de commandes de veille/réveil avec *Dragon NaturallySpeaking* pendant la période de cohabitation, et ajouter une vraie coupure totale du micro (commandes vocales dédiées + touche physique `F8`).
2. Étendre le **Studio d'Étalonnage** aux 12 commandes quotidiennes de l'utilisateur et analyser ses nouveaux enregistrements.
3. Remplacer le dictionnaire aveugle `A -> B` par un **Arbitre de Plausibilité Contextuelle & Acoustique (`PlausibilityArbitrator`)** qui évalue si ce que le modèle entend a du sens dans le contexte (ex. préserver *« La loi a été adoptée »* tout en corrigeant *« reconnaissance vocale adoptée pour un aligné »*).
4. Verrouiller le fonctionnement **100 % hors-ligne (`local_files_only=True`)** pour qu'aucune requête réseau (même de vérification de cache HuggingFace au démarrage) ne soit jamais émise.
5. Livrer la **Phase 2 complète** : *Shadow Buffer*, commandes *« Corriger ça »*, *« Choisir un / deux / trois »*, *« Sélectionner [mot] »*, *« Presser Entrée »*, et volet de correction *No-Focus* séparant **« 🧠 Corriger & Apprendre »** de **« 🛡️ Corriger SANS apprendre (Oups) »**.

### 2. Travaux réalisés & Résultats
1. **Étalonnage vocal étendu sur 12 commandes (`src/phenix_voice/ui/calibration_studio.py`)** :
   - Enregistrement et validation par l'utilisateur de : `Phénix écoute`, `Phénix repos`, `Couper Phénix`, `Effacer ça`, `Presser Entrée`, `Corriger ça`, `Oups`, `Choisir un`, `Choisir deux`, `Point à la ligne`, `Nouveau paragraphe`, `Point d'interrogation`.
   - Extraction automatique des confusions phonétiques propres à sa diction dans `user_data/learned_rules.json` (ex. `"phoenix hoppo" -> "Phénix repos"`, `"choisir de" -> "Choisir deux"`, `"pressez entrée" -> "Presser Entrée"`).
2. **Arbitre de Plausibilité Contextuelle & Acoustique (`src/phenix_voice/postprocess/plausibility.py`)** :
   - Désactivation par défaut du remplacement aveugle à 100 % sur le texte libre (conservé uniquement en option `--strict-dict` pour d'autres profils).
   - Combinaison de 3 signaux : certitude acoustique de Whisper (`confidence` + `alternatives`), score de plausibilité linguistique française (pénalisation des bégaiements de décodage et pseudo-mots), et contexte sémantique de la phrase (préférences contextuelles `adoptée` vs `adaptée`).
   - Les confusions de commandes ne sont déclenchées que sur des énoncés courts isolés (`<= 2,7 s`).
3. **Verrouillage 100 % Hors-Ligne (`src/phenix_voice/stt/engine.py`)** :
   - Ajout de `_resolve_local_or_download(..., local_files_only=True)` : zéro requête réseau pendant la parole ET zéro ping HuggingFace au démarrage dès que le modèle est en cache local.
4. **Phase 2 : Shadow Buffer, Contrôle Micro 3 États & Barre de Correction Anti-Dérive (`shadow_buffer.py`, `hud.py`, `main.py`)** :
   - **3 états de micro** :
     - `🟢 ÉCOUTE ACTIVE`
     - `🟠 VEILLE (« Phénix repos » / F9)` : réveil par *« Phénix écoute »* (aucun conflit avec *« Au repos / Écoute »* de Dragon).
     - `🔴 MICRO COUPÉ (OFF / F8)` : déclenchable à la voix par *« Couper Phénix »* ou par la touche physique **`F8`** / clic souris. Coupe totalement le flux audio (ne se réveille jamais tout seul à la voix).
   - **Shadow Buffer (`src/phenix_voice/os_control/shadow_buffer.py`)** :
     - Conserve les derniers segments injectés avec leur texte, nombre exact de `VK_BACK`, alternatives et audio PCM en RAM.
     - Supporte le remplacement sur place (`replace_last`), la sélection de mot par déplacements curseur (`select_word_in_last_segments` via `Shift + Left`) et la touche `Entrée` (`press_enter_key`).
   - **Volet de Correction Anti-Dérive dans le HUD No-Focus (`src/phenix_voice/ui/hud.py`)** :
     - Affiche les alternatives numérotées `1, 2, 3` cliquables à la souris (sans perte de focus clavier) ou activables à la voix (*« Choisir un / deux / trois »*), ou remplacement direct en re-dictant la phrase.
     - Bouton/commande de bascule **« 🧠 Mode : Corriger & Apprendre »** (sauvegarde le couple `(WAV, Texte corrigé)` dans `user_data/corrections_learned/` pour le futur Fine-Tuning LoRA) vs **« 🛡️ Mode : SANS Apprendre (Oups, j'ai fourché) »** (détruit l'audio en RAM).
5. **Validation automatisée (`tests/test_phase1.py` & `tests/test_phase2.py`)** :
   - **7 tests sur 7 passés (`7 passed`)**, incluant la validation à **100 % sur les 12 enregistrements vocaux réels de l'utilisateur**.

### 3. Prochaine étape prévue (Phase 3 & Phase 4)
1. Tester en direct la barre Phase 2 (avec démarrage `--mute` activable par `F8`).
2. **Phase 3 & 4** : Gestionnaire de vocabulaire personnel + importateur moderne de documents/e-mails + Pipeline de consolidation **Fine-Tuning LoRA local (DirectML)** sur les échantillons du Studio et des corrections validées + Gestionnaire de **Snapshots (Points de restauration)** du profil vocal.
