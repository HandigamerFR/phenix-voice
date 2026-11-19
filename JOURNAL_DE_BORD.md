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
1. Tester en direct la barre Phase 2 enrichie (avec démarrage `--mute` activable par `F8`).
2. **Phase 3 & 4** : Gestionnaire de vocabulaire personnel + importateur moderne de documents/e-mails + Pipeline de consolidation **Fine-Tuning LoRA local (DirectML)** sur les échantillons du Studio et des corrections validées + Gestionnaire de **Snapshots (Points de restauration)** du profil vocal.

---

## Session 4 — 10 Novembre 2026 : Aide Vocale Contextuelle, Correction Manuelle & Démarrage 100 % Hors-Ligne

### 1. Objectif de la session
Répondre à trois besoins prioritaires identifiés en test direct : (1) savoir quelles commandes vocales sont disponibles à tout moment, (2) pouvoir corriger manuellement (au clavier/souris) un segment et préparer la correction de parties de libellé, (3) garantir qu'aucune requête réseau n'est émise au démarrage.

### 2. Travaux réalisés
1. **Panneau « Que puis-je dire ? » (`src/phenix_voice/ui/hud.py`, `main.py`, `postprocess/punctuation.py`)** :
   - Nouveau bouton **`[❓ Que puis-je dire ?]`** et commande vocale **« Que puis-je dire ? »** (avec variantes) affichant/masquant une aide contextuelle selon l'état : **Micro coupé**, **Veille**, **Écoute active** ou **Volet de correction ouvert**.
   - Rappel explicite des commandes critiques (ex. **« Couper Phénix » / « Éteindre Phénix »**, **`F8` / `F9`**, **« Phénix écoute/repos »**, **« Corriger ça »**, **« Choisir un/deux/trois »**, **« Oups »**, **« Presser Entrée »**, ponctuation dictée).
2. **Correction manuelle dans le volet de correction (`src/phenix_voice/ui/hud.py`, `main.py`)** :
   - Ajout d'un champ texte éditable pré-rempli avec le segment à corriger + bouton **`[✅ Appliquer la correction]`** (activation temporaire du focus Win32 uniquement lors de l'édition manuelle pour ne pas voler le focus en dictée normale).
   - Conservation de la re-dictée complète pendant correction ouverte et des alternatives 1/2/3, avec choix **« Corriger & Apprendre » / « SANS apprendre »**.
3. **Démarrage 100 % hors-ligne (`src/phenix_voice/stt/engine.py`)** :
   - Chargement des fichiers Whisper via cache local en priorité (`local_files_only=True` quand disponible) pour éviter toute requête réseau au démarrage (zéro octet réseau pendant la dictée, et plus de ping de vérification HuggingFace au lancement si le modèle est présent).
4. **Cahier des charges (`docs/CAHIER_DES_CHARGES.md`)** :
   - Ajout explicite de la future **correction/sélection sur textes longs** via *UI Automation (TextPattern/ValuePattern)* + historique multi-segments du *Shadow Buffer* (occurrences multiples à la Dragon), et politique de **mise à jour de modèle uniquement manuelle avec avertissement et sauvegarde anti-casse**.

### 3. Prochaine étape prévue (Phase 3 & 4)
1. Tester en direct l'aide « Que puis-je dire ? » et la correction manuelle dans le volet de correction.
2. **Correction sur texte long (priorité fonctionnelle)** : étendre le *Shadow Buffer* à l'historique multi-segments et intégrer *UI Automation* pour sélectionner/corriger n'importe quel mot/expression dans un texte long (gestion des occurrences).
3. **Phénix Studio & Apprentissage** : vocabulaire personnel, importateur documents/e-mails, snapshots de profil, et pipeline **Fine-Tuning LoRA local (DirectML)** sur échantillons validés.


---

## Session 5 — 10 Novembre 2026 : Correctif Critique Anti-Auto-Apprentissage du Volet de Correction

### 1. Problème identifié
Lorsqu'une correction était ouverte, toute nouvelle dictée était appliquée automatiquement comme remplacement du segment (et potentiellement enregistrée en « Corriger & Apprendre »), ce qui a provoqué l'enregistrement de 5 échantillons de correction erronés dans `user_data/corrections_learned/` (sessions courtes, aucun fine-tuning LoRA exécuté).

### 2. Correctifs appliqués
1. **Fin de l'application automatique** (`src/phenix_voice/main.py`, `src/phenix_voice/ui/hud.py`, `src/phenix_voice/postprocess/punctuation.py`) :
   - Une dictée prononcée pendant que le volet de correction est ouvert est désormais proposée dans le champ de correction **sans être appliquée**.
   - Ajout de la commande/intention **`APPLY_CORRECTION`** (« Valider la correction », « Appliquer la correction », « C'est corrigé », etc.) et validation explicite obligatoire (bouton **[Appliquer la correction]**, choix 1/2/3, ou commande vocale de validation).
   - Aide contextuelle mise à jour pour refléter ce comportement sécurisé.
2. **Retour arrière sur les mauvaises corrections apprises** :
   - Les 5 couples WAV/log enregistrés à tort ont été mis en quarantaine dans `user_data/corrections_quarantine/<horodatage>/` et `user_data/corrections_learned/corrections_log.jsonl` a été réinitialisé (le modèle acoustique n'a pas été ré-entraîné ; seules les données de futur apprentissage ont été nettoyées).

### 3. Prochaine étape prévue
1. Re-tester le flux de correction sécurisé en direct.
2. Poursuivre la correction sur texte long et Phénix Studio / pipeline LoRA (avec mécanismes de snapshots et réversibilité renforcés).


---

## Session 6 — 10 Novembre 2026 : Ponctuation non forcée, Mode Épellation NATO et commande « Annuler sans apprendre »

### 1. Objectif de la session
Appliquer avant test utilisateur trois correctifs/évolutions prioritaires du système de correction : (1) éviter la ponctuation automatique qui casse les phrases inachevées, (2) permettre l’épellation via l’alphabet radio international (NATO) pour faciliter les corrections, (3) remplacer la commande « Oups » (trop courte et facilement confondue) par une commande plus robuste.

### 2. Travaux réalisés
1. **Ponctuation automatique assouplie (`src/phenix_voice/postprocess/punctuation.py`)** :
   - La ponctuation finale auto-ajoutée par Whisper (**point/virgule**) est désormais retirée lorsque la ponctuation n’a pas été dictée explicitement, afin de ne plus forcer une syntaxe incorrecte sur un groupe de mots ou une phrase inachevée.
   - Les commandes de ponctuation/mise en forme dictées explicitement sont conservées (ex. « point à la ligne », « nouveau paragraphe », « point d’interrogation », « virgule », « points de suspension », etc.).
   - Ajustement de la logique de capitalisation de début de phrase après ponctuation de fin explicite.
2. **Mode épellation alphabet radio NATO (`src/phenix_voice/postprocess/punctuation.py`, `src/phenix_voice/main.py`, `src/phenix_voice/ui/hud.py`)** :
   - Nouvelles intentions/commandes : **« Mode épellation »** (entrée) et **« Fin épellation » / « Mode dictée »** (sortie).
   - En mode épellation, les énoncés sont convertis via l’alphabet radio (Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliett, Kilo, Lima, Mike, November, Oscar, Papa, Quebec, Romeo, Sierra, Tango, Uniform, Victor, Whiskey, X-ray, Yankee, Zulu, + variantes FR/EN courantes, « espace », lettres/chiffres isolés) et injectés comme lettres, sans mise en forme de dictée classique.
   - Fonctionne aussi pendant une correction ouverte : la proposition épelée est placée dans le champ de correction **sans application automatique** (validation explicite requise). Les commandes de contrôle/sortie restent gérées pour éviter la confusion avec des mots dictés.
3. **Remplacement de la commande « Oups » (`punctuation.py`, `main.py`, `hud.py`, `stt/engine.py`, données/tests`)** :
   - Commande principale remplacée par **« Annuler sans apprendre »** (formes reconnues : « Annuler sans apprendre », « Ne pas apprendre », « Ne retiens pas », « Sans apprendre », « Corriger sans apprendre », « J’ai fourché », « J’ai bafouillé »). Le mot court « Oups » n’est plus une commande active.
   - Mise à jour de l’interface et des messages (« Sans apprendre / Effacer », aide contextuelle, états de correction), du prompt calibré STT, des règles apprises et du manifeste de calibration (`cmd_oups` mappé vers « Annuler sans apprendre ») pour cohérence.
4. **Tests** : mise à jour de `tests/test_phase1.py` et `tests/test_phase2.py` (nouvelle commande, vérification de non-forçage du point final auto, et conversion NATO de base). Exécution ciblée : `pytest -q tests/test_phase1.py tests/test_phase2.py -k "not amd_gpu_transcription and not user_voice_calibration and not calibrated_12_commands"` → **4 passed, 3 deselected**.

### 3. Prochaine étape prévue
1. Test utilisateur en direct des trois changements (ponctuation, épellation NATO en dictée/correction, « Annuler sans apprendre ») et ajustements éventuels de robustesse phonétique.
2. Poursuivre la correction/sélection sur textes longs (historique multi-segments + UI Automation) puis Phénix Studio / pipeline LoRA avec snapshots.


---

## Session 7 — 11 Novembre 2026 : Traçage d'injection, racine de la corruption (Bloc-notes Win11) & correctif à double chemin

### 1. Outils de diagnostic (commits `b184dfb`, `5844e19`, `1b07554`)
1. **Traçage étendu** : `logs/session_trace.jsonl` + **`logs/injection_trace.jsonl`** (`InjectionTraceLogger`) journalisent désormais, avec `session_id`, horodaté mono-fenêtre et fenêtre cible : démar/fin de session, `engine_ready`, pipeline audio, état micro/sommeil (avec `source` hotkey/ui/voice), contexte curseur, commandes reconnues/exécutées, injections/remplacements/sélections (`events_requested/inserted`, `send_ok`, `batch_results`, dernier caractère), et **exceptions** (`where`, `error`, `traceback`).
2. **Crash de démarrage corrigé** : ordre d'initialisation (`injection_logger`/`_session_id`/`trace_logger`/`snapshot_manager` avant `ShadowBuffer(action_logger=…)`).

### 2. Racine de la corruption d'injection (régression « dernier caractère répété »)
- **Symptôme** : longueur du texte toujours préservée, mais la queue est remplacée par la répétition du dernier caractère du lot (` ,`→`,,`, ` ont été`→`éééééééé`), plus des pertes ponctuelles.
- **Écarter notre code** : contenu du tableau `SendInput` vérifié octet par octet (bon `wScan`, bons `dwFlags`) → **notre envoi est correct**.
- **Banc d'essai** (`tools/injection_bench.py`) : injecte via le **code PRODUCTION** puis **relit** le texte reçu (presse-papier vidé avant chaque `Ctrl+A/Ctrl+C`), mêmes séquences sur **9 cibles** :
  | Cible | Résultat (chemin production) |
  |---|---|
  | Widget tkinter | 24/24 |
  | Contrôle d'édition Win32 natif | 36/36 |
  | Notepad++ | 36/36 |
  | LibreOffice Writer | conforme (seule l'autocorrection `'`→`’`/majuscule agit) |
  | Microsoft Word | conforme (idem autocorrection) |
  | Edge / Brave / Chrome | 18/18 chacun |
  | **Bloc-notes Windows 11** | **~50 % corrompu** |
- **Cadence innocentée** : respiration 5/20/200 ms, envoi caractère par caractère, appui/relâchement séparés → **aucune variante n'élimine le défaut** (le « par caractère » est même le pire).
- **Cause racine** : **bug connu et documenté du pipeline d'entrée du Bloc-notes redessiné de Windows 11** (rapports AutoHotkey, Stack Overflow, microsoft/terminal : rafales `SendInput`/`VK_PACKET` figées ou mises en buffer, corrélation rapportée avec le correcteur orthographique du Bloc-notes). Bug système/application réceptrice : on ne le corrige pas, on le contourne proprement.

### 3. Correctif implémenté — double chemin d'envoi automatique
1. **`src/phenix_voice/os_control/injector.py`** : nouveau chemin **« messages »** :
   - `send_text_via_messages()` : `WM_CHAR` envoyé par unité UTF-16 (paires de substituts pour les emojis hors-BMP) à la fenêtre focalisée (`GetGUIThreadInfo`), `WM_KEYDOWN/UP VK_RETURN` pour les sauts de ligne (`WM_CHAR '\r'` seul est ignoré par le Bloc-notes) ;
   - `send_backspaces_via_messages()` : `WM_KEYDOWN/UP VK_BACK` (un `WM_CHAR '\b'` est ignoré) ;
   - `choose_send_path()` : **`messages` si la classe de la fenêtre active est `Notepad`, sinon `sendinput`** ; surcharge pour diagnostic via variable d'environnement **`PHENIX_INJECTION_PATH`** (`sendinput` | `messages`).
2. **`src/phenix_voice/os_control/shadow_buffer.py`** : `_send_text`, `_send_backspaces` et `press_enter_key` routent selon le chemin choisi, avec **repli automatique sur `SendInput`** si la fenêtre focalisée est indisponible ; stats enrichies de `send_path`, `target_class`, `focus_hwnd`, `messages_fallback_reason` → visibles dans `logs/injection_trace.jsonl`.
3. **Validations** : Bloc-notes **12/12 puis 24/24** avec correctif (vs ~50 % avant), saut de ligne et emoji conformes ; corruption **reproduite à volonté** avec `PHENIX_INJECTION_PATH=sendinput` (preuve que la détection corrige) ; non-régression tkinter 24/24 et contrôle Win32 24/24 ; `pytest` → **4 passed, 3 deselected** ; démarrage réel de l'application (`--mute`, 30 s) OK ; trace d'injection écrite correctement.

### 4. Banc versionné + nettoyage automatique (`tools/injection_bench.py`, `tools/bench_web.html`)
- Modes : `tk`, `ed`, `np`, `fix` (variantes de cadence), `fix2` (variantes de chemin : `batch`/`wmchar`/`paste`/`wmkey`), `npp`/`nppw`, `lo`/`low`, `wordb`/`wordk`, `edge`/`chrome`/`brave`, `both` (défaut) + nombre d'itérations en 2e argument.
- Garde-fous : aucune injection si la fenêtre témoin n'est pas au premier plan ; presse-papier vidé avant chaque copie (copie ratée = `SKIP`, pas de faux échec) ; fenêtre de test ciblée par différence avant/après lancement (pas de capture d'une fenêtre existante) ; fermeture de la fenêtre de test en fin de série.
- **`sweep_test_apps()` en début ET fin de série** (demande utilisateur pour ne pas accumuler les processus) : fermeture des pages `PHENIX_WEB_TEMOIN` et `bench_npp.txt`, du Bloc-notes (douce puis `taskkill`), et des documents **sans titre** LibreOffice/Word — force uniquement si toutes les fenêtres de l'application sont des documents sans titre (aucun travail utilisateur).

### 5. Prochaine étape prévue
1. **Test utilisateur en direct** : dictée longue dans le Bloc-notes et dans d'autres applications, corrections (« Corriger ça », choix 1/2/3), « C'était une commande » ; vérifier `send_path` dans `logs/injection_trace.jsonl` (`messages` en Bloc-notes, `sendinput` ailleurs).
2. Suites du diagnostic ouvertes : segments reconnus mais non injectés (`dictation_empty` : `seg_20261111_145733`, `_145914`, `_150052`) et `select_word not_found` sur « ça corrigez ça ».
3. Correction sur textes longs (UI Automation/TextPattern + historique multi-segments, jusqu'à 9 alternatives), outils de rollback/purge, puis pipeline LoRA local DirectML.


---

## Session 8 — 11/12 Novembre 2026 (soirée & nuit) : « C'était une commande », formes orales des symboles, fenêtre de correction à 9 choix & fenêtre d'épellation séparée

### 1. Correctif « C'était une commande » (commit `9a1c4aa`)
- Les commandes à apostrophe (notamment **« C'était une commande »**) n'étaient reconnues que si le STT rendait l'apostrophe droite : la clé de comparaison dérivée (`command_keys`) ignore désormais apostrophes droites/typographiques et accents **sans jamais modifier les tables en français naturel** (règle de design confirmée : tolérance en mémoire uniquement, jamais persistée ni affichée).
- Tests : formes naturelles, dégradées, casse et ponctuation toutes acceptées.

### 2. Formes orales des symboles + règle « rien sans validation » (commit `ae44eb2`)
1. **Nouveau `src/phenix_voice/postprocess/symbols.py`** : tables FR naturelles (~25 formes cœur : virgule, point, point-virgule, deux-points, parenthèses, guillemets, tiret, espace insécable…) + formes **ambiguës** (euro, dollar, paragraphe, degré, copyright, pourcentage) ; index tolérants en mémoire ; substitution multi-mots à fenêtre glissante ; **typographie française contextuelle** (`% : ; ! ?` espacés des deux côtés, `€ £ § ® °` espace avant, `@` collé en contexte e-mail détecté) ; `SpokenFormStore` (`user_data/spoken_forms.json`) alimenté par le bouton **« 🔑 + Forme orale »** ; `spelling_symbol()` pour le mode épellation.
2. **Règle validée par l'utilisateur** : **« Choisir un/deux/trois » (voix OU clic) n'insère plus rien** — l'alternative est proposée **dans le champ** de correction, insertion seulement après **« Valider la correction »** / **[Appliquer la correction]** (l'utilisateur a toujours le droit de changer d'avis ou de se tromper). `apply_correction_choice()` est devenu une proposition loguée (`applied=False`).
3. `tests/test_symbols.py` (10 tests) → suite **19 passed, 3 deselected**.

### 3. Fenêtre de correction SÉPARÉE à 9 alternatives + barre 1240 px (commit `b8930a7`)
1. **9 alternatives** : STT `num_alternatives` 4→8 (second choix du runner-up, gratuit), arbitre `ranked_alternatives` plafonné à **9**, stockage `[:9]` (7 sites), `CHOOSE_MAP` étendu **« Choisir quatre…neuf »** (variantes « choix X / numéro X / choisir N »).
2. **Nouvelle classe `CorrectionWindow`** (`ui/hud.py`) : fenêtre Tool always-on-top sans vol de focus (`WA_ShowWithoutActivating`), grille **3×3** de boutons libellés échelonnés + infobulle texte complet, champ éditable, **[Appliquer la correction]**, 🔑 + Forme orale, bascule 🧠/🛡️ ; **✕ = annuler sans rien insérer** (`closeEvent` → `on_close` → `_close_correction_bar`). L'ancien volet embarqué dans la barre a été supprimé (moins de code, plus d'espace).
3. **Barre HUD 920→1240 px** : libellé **« 🛡️ Sans apprendre / Effacer »** entier (demande utilisateur), transcription affichée 85→110 car.
4. Tests + smoke offscreen (9 boutons, pré-rempli, callback de fermeture) → **22 passed, 3 deselected**.

### 4. Fenêtre d'ÉPELLATION séparée (commit `477f5d5`, demande validée le 12/11)
1. **Nouvelle classe `SpellingWindow`** (`ui/hud.py`, miroir de `CorrectionWindow`) + signaux HUD dédiés (`spelling_opened/closed/text_set/text_append`, tous thread-safe) :
   - **Depuis la correction** (« Mode épellation » ou nouveau bouton **[🔤 Épellation]** de la fenêtre de correction) : champ **pré-rempli avec le texte du souffle corrigé et modifiable**, lettres dictées **ajoutées** au texte (append, pas remplacement), **rien inséré dans l'éditeur avant validation** ; boutons [🗑 Vider] et [✅ Appliquer la correction].
   - **Hors correction** : accessible à tout moment, champ en **miroir lecture seule**, texte épelé inséré **directement dans l'éditeur cible** jusqu'à la sortie.
2. **Commandes restreintes** : garde de routage dans `_stt_worker_loop` — en mode épellation seules passent `DICTATION` (convertie alphabet radio), `EXIT_SPELLING`, `APPLY_CORRECTION` (si correction ouverte) et la sécurité (`MUTE/SLEEP/WAKE/HELP`) ; **toute autre commande est ignorée et journalisée** (`spelling_command_ignored`) — pas d'effet de bord caché.
3. **Sortie** : « Fin épellation », **« Passer en mode dictée »** / « Retour en mode dictée » (nouvelles formes dans `SPELLING_EXIT_COMMANDS`), ✕ de la fenêtre, veille vocale (F9/« Phénix repos ») et arrêt de l'application. **Décision** : la coupure micro (F8/« Couper Phénix ») **ne referme pas** la fenêtre — elle sert de pause et le mode reprend au réveil du micro.
4. **Clôture liée** : appliquer ou annuler la correction ferme aussi la fenêtre d'épellation ouverte depuis celle-ci (`_close_correction_bar` → `_exit_spelling_mode`).
5. Aide contextuelle mise à jour (dictée, correction, état épellation : liste des seules commandes écoutées).

### 5. Validations (12/11, nuit)
- `pytest -q tests/test_symbols.py tests/test_phase1.py tests/test_phase2.py tests/test_command_matching.py -k "not amd_gpu_transcription and not user_voice_calibration and not calibrated_12_commands"` → **25 passed, 3 deselected** (+3 tests : formes de sortie épellation, formes d'entrée, intentions autorisées en mode épellation).
- Smoke offscreen `smoke_hud.py` : 9 alternatives, pré-rempli, barre 1240, callbacks de fermeture, **fenêtre d'épellation** (pré-remplissage, édition, miroir lecture seule, append, sortie) → **OK**.
- Banc d'injection `tools/injection_bench.py` → **36/36 conformes, aucune corruption** (tk 24/24, Bloc-notes 12/12), balayage de début/fin de série OK.

### 6. Recherche « N souffles précédents » dans l'aide Dragon (consultation seule, 12/11 nuit)
- Source : `C:\Program Files (x86)\Nuance\NaturallySpeaking15\Help\fra\ProfessionalIndividual\Content` (pages HTML extraites, aucune copie de code — recueil de mécanique uniquement).
- **Réponse : Dragon ne compte pas en « souffles » mais en unités de texte, plafonné à 20.** Formes relevées : **« Sélectionner les <1-20> mots précédents »** (idem caractères / lignes / paragraphes ; variantes « arrière », « derniers »), **« Effacer les <2-20> mots précédents »**, « Effacer le dernier mot », « Sélectionner le dernier mot » ; « Effacer ça » / « Annuler ça » pour le dernier texte dicté.
- Correction ciblée : « Corriger ça », **« Corriger <texte> »**, **« Corriger de <texte> à <texte> »** (France), « Sélectionner ça » / « Sélectionner de X à Y », **« Epeler ça »** → fenêtre d'épellation.
- **Convergence** : l'option Dragon « Les commandes "Corriger" affichent la fenêtre d'épellation » valide notre implémentation du jour (fenêtre d'épellation ouverte depuis la correction).
- **Proposition Phénix (à valider)** : « Corriger les <N> souffles précédents » (N en mots 1…9, plafond 25 = capacité réelle du `deque` du `ShadowBuffer`) → texte des N derniers segments concaténé dans la fenêtre de correction ; validation → remplacement du bloc + fusion des segments. Reporté après le panneau « C'était une commande ».

### 7. Prochaine étape prévue
1. **Extension « N souffles précédents »** (correction aussi, pas seulement l'épellation) : se renseigner sur la mécanique Dragon via son **aide locale** (`C:\Program Files (x86)\Nuance\NaturallySpeaking15\Help\fra\ProfessionalIndividual`, consultation seule, aucune copie).
2. Panneau **« C'était une commande »** : liste des commandes triée par **proximité phonétique** dans la fenêtre de correction.
3. Test utilisateur en direct de la fenêtre d'épellation ; puis anomalies ouvertes (`dictation_empty` : `seg_20261111_145733`, `_145914`, `_150052` ; `select_word not_found`).
4. Correction sur textes longs (UI Automation + multi-segments) → Phénix Studio/rollback → pipeline LoRA local DirectML.

---

## Session 9 - 13 Novembre 2026 : Analyse forensique de la session du 12/11 soir, Étape 1 (cohérence : ponctuation auto + casse + classification texte/acoustique) & génération des 9 choix

### 1. Analyse forensique de la session de test du 12/11 soir (demande prioritaire de l'utilisateur — TERMINÉE)
- **Périmètre réel** : blocs 22h (47) + 23h (46) = **93 souffles** (le bloc « 21h » au format `fp` vient du **10/11**, exclu). Scripts dans `C:\Users\camille\AppData\Local\Temp\opencode\` (`scope_2223.py` + `analyze_*.py`), sources = `logs/dictation_debug.jsonl`, `logs/injection_trace.jsonl`, `logs/session_trace.jsonl`.
- **Dysfonctionnements confirmés** (rapport rendu à l'utilisateur) :
  1. **9 alternatives jamais atteintes** : distribution 1→12, 2→23, **3→50**, 4→5, 5→2, 6→1 (générateur = substitutions unitaires seules, seuil 0.04 → plafond ~3) ;
  2. **aucun signal « moins de 9 »** (grille de boutons `---` sans explication) ;
  3. **4 échecs d'épellation 23:32:13–24** : STT brut `"Veilk !"`, `"Make."`, `"Bank."` ×2 → prononciations NATO non transcrites en mots NATO (`text_to_nato_spelling` jette les mots inconnus) → `dictation_empty` ;
  4. **« Mode épellation, mode épellation. » raté (23:35:09)** : énoncé doublé → appariement exact cassé → classé `dictation` et **injecté comme texte** ;
  5. **`select_word not_found` ×2 (23:26:56)** : « Corriger ça, Corriger ça. » → même cause (énoncé doublé) ;
  6. **latence** : médiane **498 ms**, p90 673, max 969 ; 26/133 > 600 ms (souffles longs 6–7 s) ;
  7. **commandes ratées** : 22:36:30 « Écoute, » dictée ; 22:48:28 « A la ligne… » injectée comme texte (conf 0.52) ; 23:13:14–22 deux souffles vides ; 22:47:27 « Oups, c'est le fourger. » classée dictée.
  - **Sain** : 0 exception, 0 envoi partiel, bench Notepad 12/12, `revise_cmd` OK.
- **Report** : ces anomalies ouvrent le diagnostic de l'étape 2 (§ 5 ci-dessous).

### 2. Étape 1 — nouvelle couche `postprocess/coherence.py` (non suivie)
- **`strip_auto_punctuation`** : retire **TOUTE** ponctuation/symbole auto-ajouté par le modèle (séparateurs de chiffres `[.,:/]` protégés via placeholders `\x01`) ; seules les formes dictées (« virgule », « point »…) sont écrites. Fini « Comment vas-tu ? » → « ? » parasite et « ? ? ».
- **`adapt_chunk_to_context`** : casse intelligente — majuscule **uniquement** au début du texte, après retour à la ligne et après `. ! ? …` ; minuscule sinon ; espace de liaison ajouté seulement s'il manque (fin du « chaque souffle en majuscule » et du « mot.Nouveau »).
- **`is_textual_only_correction`** : classe une correction en **règle de texte** (ponctuation/casse/espace égaux après normalisation, `\W_` retiré + `casefold`, accents significatifs, vide → False) vs **erreur acoustique**.
- **Refactor `punctuation.py`** : `_format_core(mapped)` (cœur sans mutation d'état), `format_dictation(mapped, previous_text)` (contexte + mémorisation `_last_produced`), `format_alternatives(alts, previous_text, chosen_text)` (mêmes règles, choix retenu exclu, dédoublonnage `casefold`, **aucune mutation**) ; `process()` étape-5 délègue à `format_dictation`.
- **`main.py`** : `previous_text=recent_ctx` transmis au routeur ; nettoyage des alternatives juste après l'arbitrage via `dataclasses.replace` + `format_alternatives` (couvre les 3 sites `[:9]` en aval) ; classification des corrections : `kind="textual"` jsonl **sans WAV** + tag « ✏️ Corrigé — règle texte (pas d'apprentissage audio) » / « 🛡️ Corrigé SANS apprendre (règle texte) », acoustique inchangé (`kind="acoustic"`, snapshot + WAV).

### 3. 9 alternatives réellement atteintes + signal explicite
- **`stt/engine.py`** : nouveau helper **`build_alternatives(generated_tokens, runner_up_candidates, decode, main_text, num_alternatives)`** — substitutions unitaires d'abord (ratio décroissant), puis **combinaisons de DEUX substitutions** pour remplir la grille 3×3 ; dédoublonnage `casefold` ; `decode` injecté (testable sans GPU). Seuil runner-up **0.04 → 0.01**. Quota `num_alternatives` 8 → **9** (la grille fait 3×3).
- **`ui/hud.py`** : nouveau **`alt_count_label`** dans `CorrectionWindow` — **✅ 9/9 choix disponibles** (vert) / **⚠️ X/9 choix seulement — le système n'a pas trouvé plus d'alternatives pour ce souffle** (ambre) / **❌ 0/9 choix — aucune alternative trouvée : modifiez le champ à la main ou re-dictez la phrase** (rouge). Exigence « signaler quand il y a moins de 9 » donc satisfaite.

### 4. Validations (13/11)
- **`pytest -q tests/ -k "not amd_gpu_transcription and not user_voice_calibration and not calibrated_12_commands"` → 47 passed, 3 deselected** (+10 nouveaux : `tests/test_alternatives.py` ×5 sur `build_alternatives` — unitaires puis paires, quota 9, dédoublonnage/exclusion du principal, sans seconds choix, paires seulement si insuffisant ; `tests/test_coherence.py` +5 — `format_dictation` == sortie `process`, mêmes règles pour les alternatives, exclusion/dédoublonnage, pas de mutation du contexte, adaptation en milieu de phrase ; `test_phase1.py` r2 mis à jour → `" Je teste Phénix Voice.\n"`).
- **Smoke offscreen** : import `phenix_voice.main` + `is_textual_only_correction` + `build_alternatives` OK ; **`CorrectionWindow` réelle** : 3 alts → ⚠️ 3/9, 10 alts → ✅ 9/9 (plafonné), 0 alt → ❌ 0/9.

### 5. Roadmap validée par l'utilisateur (Option 1) & prochaine étape
1. ✅ **Étape 1** (ponctuation auto retirée + casse intelligente + classification texte/acoustique) — **ci-dessus**.
2. **Étape 2** : diagnostic d'épellation NATO (transcrire les 4 WAV `seg_20261112_233213/17/20/24.wav`, étendre les variantes NATO, prompt STT du mode épellation), fix énoncés doublés (« Mode épellation » ×2, « Corriger ça » ×2) + **commandes de navigation/correction en mode épellation** (curseur gauche/droite, suppr caractère — nouvelles intentions + injection de touches).
3. **Étape 3** : cohérence inter-souffles v1 complète (accords au 2ᵉ passage).
4. **Étape 4** : panneau « C'était une commande » trié par proximité phonétique.
5. **Étape 5** : corpus phonèmes / LoRA.
- Reporté : banc Tk à relancer avec l'accord de l'utilisateur (fenêtre témoin minimisée par erreur — SendInput exige le premier plan, ce n'est pas un bug).

### 6. Étape 2 engagée (13/11, suite) — diagnostic NATO + correctifs rapides (`8dbecbc`)
- **Diagnostic sur les 4 essais « Mike » (23:32:13/17/20/24)** : transcriptions `Veilk`/`Make.`/`Bank.`×2 (conf 0.15–0.55). **Hypothèse « décodage anglais » testée puis REJETÉE** : `language="en"` ne corrige rien (`Make.` reste `Make.`) et l'utilisateur rappelle que son accent français rendrait ce décodage non viable pour d'autres utilisateurs francophones. Décision : **rester en FR ; le vrai fix = étalonnage acoustique de SA prononciation (studio 26 lettres + LoRA étape 5)**. Le paramètre `language` reste dans `engine.py` (expérimental, documenté).
- **Les 2 commandes ratées n'étaient PAS des échecs STT** : `Mode épellation, mode épellation.` et `Corriger ça, Corriger ça.` transcrits **parfaitement** (conf 0.73/0.77) — c'est le **doublon** qui cassait l'appariement exact → texte envoyé en dictée / `select_word not_found`.
- **Correctifs implémentés + testés (59 passed, 3 deselected)** :
  1. **`collapse_repeated_utterance`** (`rules.py`, en mémoire, matching seul — texte dicté intact) : replie la répétition d'une séquence de mots (comparaison aussi sans accents) — répare « Mode épellation ×2 », « Corriger ça ×2 », « C'était une commande ×2 », « Fin épellation ×2 ».
  2. **Filtre « n'écouter que ce qui est utile »** : `spelling_from_result(raw, alternatives)` (`punctuation.py`) → conversion directe, puis recherche dans les **alternatives du STT** (ex. `M.` parmi les hypothèses de `Make.`), sinon **rejet explicite** affiché (`❌ Épellation non reconnue : « Bank. »` + log `spelling_rejected`) — **fini le silence `dictation_empty`**.
  3. **Tolérance phonétique NATO** : `_nato_fuzzy` (écart ≤ 1, mots ≥ 3 lettres, table restant en français naturel) — « Make. » → `m` ; « Bank. »/« Veil. » restent rejetés (écart trop grand → l'étalonnage tranchera).
- **Design validé (réponses utilisateur 13/11)** : « Rapides puis calibration » — prochaine pièce = **studio d'étalonnage des 26 lettres NATO avec la voix de l'utilisateur** (empreintes DTW, réutilise la mécanique de `AcousticCommandProtector`).
- **Contrainte de design ajoutée (utilisateur)** : le système ne doit JAMAIS dépendre d'un anglais sans accent ; cible = Francophones d'abord (dysarthriques ou non) → **tuning du modèle (LoRA) = fondement**, pistes alternatives à comparer à l'étape 5 (prompting FR+NATO, classifieur 26 lettres).

### 7. Recherche documentaire (13/11) — prosodie + méthodo d'entraînement, avant tout code
- **Demande utilisateur** : « utilise tes connaissances mais surtout fait des recherches sur Internet sur la prosodie et comment on entraîne un modèle vocal avant de coder quoi que ce soit ». **Zéro code écrit** pendant cette phase.
- **Vision d'entraînement validée par l'utilisateur** : corpus = **textes/phrases naturels dictés** (jamais une liste de phonèmes isolés — ergonomie + prosodie réelle), chaque texte contenant **plusieurs occurrences de chaque phonème** → alignement forcé puis **moyenne des occurrences** pour affiner le modèle. Alimente l'étape 5.
- **Sources clés consultées** :
  - **arXiv 2606.31722** (Adapting Foundation ASR to Dysarthric Speech, 08/2026) : locuteur unique, 92h + 8.8h corrections ; WER 128.4% → 15.8% (1.4h) → 10.7% (22.5h) → 9.7% (tout) ; **full FT > LoRA rank 8** ; Whisper > Qwen3-ASR ; outil de collecte **TEQST** ; corrections continues via app déployée.
  - **CBA-Whisper** (Interspeech 2025, tan90xx/CBA-whisper) : curriculum learning + AdaLoRA sur datasets dysarthriques.
  - **Diagnosis-aware fine-tuning** (Speech Communication 2026, S0167639326000415) : modèles par pathologie > pooling (−18.34 pts CER).
  - **Augmentation** : Bhat 2025 two-stage (speed/pitch/tempo/volume + « Dysarthric SpecAugment », S0010482525003051) ; TTS-aug Hermann Interspeech 2023 ; arXiv 2406.08568 ; Mengke 2026 (spec+speed toujours compétitif).
  - **LoRA bas-déf** : MDPI 15/24/13090 (LoRA > full FT en faible ressource, 3 langues) ; CbaLoRA (S0167639326000567).
  - **Alignement forcé FR** : **MFA 3.x** (montreal-forced-aligner.readthedocs.io, dictionnaires IPA FR dispo — mfa-models, WikiPron) ; état de l'art 2026 arXiv 2606.18466.
  - **Whisper fine-tuning best practices** : HF blog ; gel encoder bas + fine-tune couches hautes + decoder (Liu 2024) — mais geler le bas **dégrade** sur les petits modèles (6 couches) ; arXiv 2604.06507.
  - **Prosodie** : Speech Prosody 2026 (mai 2026) ; ponctuation pilotée par la prosodie (cho22b Interspeech 2022, Balalaika arXiv 2507.13563) ; prosodie réduite dysarthrie = marqueur de sévérité (ASHA, PMC11427746).
  - **Entraînement AMD** : **ROCm Windows preview natif** (AMD PyTorch Preview 25.20.01.14) → GPU training envisageable sur RX 5700 XT ; DirectML inference OK mais **training DirectML non fiable** ; ROCm Linux = alternative.
- **Choix d'architecture VALIDÉS par l'utilisateur (question 13/11)** :
  1. **Pipeline étape 5 = LoRA Whisper FR + MFA + augmentation** (gel encoder bas, couches hautes + decoder ; augmentation vitesse/hauteur/SpecAugment ; full-FT réévalué si corpus > ~10-20h).
  2. **Filet DTW 26 mots NATO conservé** : session studio = vos 26 mots NATO naturels (filet immédiat épellation) + textes naturels (corpus LoRA) — rien n'est perdu.
  3. **Validation ROCm Windows preview en premier** pour l'entraînement local (repli CPU/Colab si instable).
- **Rappel technique** : la « moyenne des occurrences » est réalisée par l'entraînement lui-même après **alignement forcé (MFA en local)** — pas de calcul manuel nécessaire.

---

## Session 10 - 14 Novembre 2026 : Studio mixte (prompts OTAN + corpus), filet acoustique d'épellation, commandes de casse & variantes d'accord via Lexique383

### 1. Recherche « comment font les systèmes existants ? » (demande utilisateur, avant code)
- **Demande** : « il faut peut-être importer un dictionnaire… renseigne-toi sur comment les systèmes de reconnaissance vocale existants font, on n'a pas besoin de réinventer la roue ».
- **Constat documenté** : les erreurs d'accord représentent **~11 % des erreurs de transcription ASR en français** (homophones « est/estes », « terminé/terminées ») — littérature ASR française (LREC 2008/2014, ESTER) : les systèmes traitent ça avec un **lexique morphologique forme → lemme → formes fléchies** (type FLEMM, Lexique, Lefff) pour rescorer/resynchroniser les hypothèses. Notre boîte « Corriger ça » fait la même chose, côté proposition plutôt que rescoring.
- **Choix validés par l'utilisateur (question 14/11)** :
  1. **Lexique = Lexique383** (base standard FR, ~140 000 formes fléchies + lemmes + genre/nombre + fréquences, licence **CC BY-SA 4.0**) plutôt que Lefff (plus lourd, sans fréquences) ;
  2. **Étendue = TOUS les mots inflectables** de la phrase, une seule substitution par proposition, classés depuis la fin, 9 max.
- **Limite GitHub rappelée à l'utilisateur** : 100 Mo/fichier (recommandé < 50), ~5 Go/dépôt — mais la vraie raison de ne pas importer le zip de 27 Mo : il contient 34 colonnes dont 4 utiles → **compilation**.

### 2. Lexique compilé dans le dépôt (172 Ko gzip / 713 Ko brut)
- **`tools/build_lexicon_accords.py`** : lit `Lexique383.tsv` (téléchargé depuis lexique.org, hors dépôt) et écrit **`src/phenix_voice/resources/lexique_accords.tsv`** : une ligne = une **famille d'accord** = formes réelles partageant (lemme, tronc d'accord retirant suffixes `ées/és/ée/é/es/eaux/aux→ail/x/s/e`, statut accentué du suffixe), classées par fréquence décroissante (`freqlivres+freqfilms2`), familles à une seule forme écartées. **28 776 familles**.
- **Validation par construction** : seules les formes RÉELLES du lexique sont proposées (« terminées » → terminé/terminée/terminés/terminées ; « cafée » n'existe pas → jamais proposé ; « année/années » groupe correct ; règle de statut accentué écarte « parle » quand le mot est « parlé »).
- **Attribution/licence** : `resources/README_Lexique383.txt` (source, auteurs, citations, recette de recompilation) + `resources/LICENSE-CC-BY-SA-4.0.txt` (texte intégral CC BY-SA 4.0, obligation de partage pour le compilat).

### 3. Nouveau module `postprocess/agreement.py` — variantes d'accord dans « Corriger ça »
- **Règle validée par l'utilisateur** : le texte dicté reste **correct par défaut** ; la boîte propose en PLUS **toutes les variantes d'accord réelles** du texte, même grammaticalement fautives au contexte près (« les conversations sont terminées » → terminé / terminée / terminés + « conversation » au singulier).
- `agreement_variants(text, max_variants=9)` : mots traités **depuis la fin**, **une substitution** par proposition, casse du mot d'origine conservée (`Terminées` → `Terminé`), préfixes d'apostrophe préservés (`d'accord` → `d'accords`), texte d'origine jamais redéclaré.
- `merge_agreement_alternatives(text, alts, max_total=9)` : variantes d'accord **en tête**, puis hypothèses STT, dédoublonnées, plafond 9.
- **Intégration `main.py`** (branche `DICTATION`, hors épellation, hors popup symbole) : `seg_alternatives = merge_agreement_alternatives(inject_text, …)` avant `inject_and_record` → `last.alternatives` alimente `open_correction_for_last` / `apply_correction_choice` sans autre changement.

### 4. `spelling_with_acoustic_net()` — le filet acoustique branché (code réparé)
- **`main.py`** : la fonction appelée depuis la branche épellation était **définie nulle part** (arbre cassé) — maintenant définie : `(protector, segment, raw_text, alternatives) → (texte, rejet, nato_hit)`. Ordre : **STT direct + alternatives** → **filet `protector.match_nato_letter`** (26 mots OTAN du studio) → **rejet explicite**. `nato_hit=(mot, distance)` journalisé en `spelling_acoustic_match`.
- **`audio/fingerprints.py`** (déjà édité dans l'arbre) : `nato_templates` séparé de `templates` (`cmd_*`), `match_nato_letter(audio)` (durée 0,2–2,5 s, seuil 0.16) + `_best_template_match` partagé.
- **`ui/calibration_studio.py`** (déjà édité) : `NATO_VOCABULARY` (26 mots → ids `nato_*`), `CORPUS_TEXTS` (12 phrases FR → `corpus_01..12`), `ENRICHED_PROMPTS` = **50 prompts** ; démarrage au **premier prompt non enregistré** (`_first_missing_index`) + bouton **« ⬅️ Précédent »** (`_prev_current`, désactivé au premier).

### 5. Commandes de casse en mode épellation (orthographe naturelle, « s » muet)
- **`punctuation.py`** : table `_CASING_COMMANDS` + `spelling_casing_command(raw, alternatives)` → `upper_next` (« Majuscule »), `lower_next` (« Minuscule »), `upper_all` / `lower_all` (« Tout en majuscules/minuscules »), `reset` (« Fin majuscules/minuscules », « Fin des … »). **Formes singulier ET pluriel listées explicitement** (décision 13/11 : le « s » est muet, aucune dépendance à l'orthographe du STT) ; normalisation casse + ponctuation de fin (`Majuscules !`), alternatives du STT vérifiées aussi.
- **`SpellingCasingState`** (même fichier) : commande ponctuelle appliquée à la **prochaine production contenant une lettre** (espace/chiffre ne la consomme pas), mode persistant jusqu'à « Fin … »/sortie, la ponctuelle prime sur le persistant, entrée/sortie du mode remettent à zéro.
- **`main.py`** : état `self._spelling_casing`, détection **avant** la conversion NATO (les commandes de casse ne produisent aucun texte : log `spelling_casing_command` + accusé affiché + `continue`), application sur le texte épellé, **aide** du mode épellation enrichie (ligne « Casse »).

### 6. Validations (14/11)
- **Suite complète : `101 passed, 3 deselected`** (avant = 63) — +38 tests :
  - `tests/test_agreement_variants.py` ×10 (exemple utilisateur exact, ordre depuis la fin, casse, aucun mot inventé, apostrophes, plafonds, merge) ;
  - `tests/test_spelling_casing.py` ×11 (singulier/pluriel, min/max symétriques, sortie, alternatives, machine à états) ;
  - `tests/test_spelling_recognition.py` +5 (`spelling_with_acoustic_net` : priorité STT sans solliciter le filet, repli OTAN, rejet, silence, rattrapage STT vide) ;
  - `tests/test_nato_acoustic_net.py` ×5 (routage `nato_`/`cmd_`/`corpus_`, match auto-sur-même-voix + conversion `Mike`→`m`, durées hors fenêtre) ;
  - `tests/test_calibration_studio.py` ×6 (26 + 12 + 50 prompts uniques, premier manquant, navigation précédent).
  - Échec révélé puis corrigé au passage : une alternative STT contenant une **lettre isolée** (« d » de « d'utile ») est acceptée à raison (comportement voulu pour « M. ») — données de test ajustées.
- **Smoke offscreen** (`smoke_casse_accords.py`) : variantes de l'exemple exact, commandes de casse, **`CorrectionWindow` réelle ouverte avec 6 propositions** (4 accord + 2 STT, libellé ⚠️ 6/9), `SpellingWindow` append miroir → **SMOKE OK**.
- **Rappel** : pour que le filet OTAN fonctionne en conditions réelles, il faut **enregistrer les 26 prompts `nato_*`** dans le studio (manifest `user_data/calibration/` — actuellement aucun `nato_`/`corpus_`).

### 7. Prochaine étape prévue
1. **Étape 2 (reste)** : enregistrement studio par l'utilisateur (26 mots OTAN + 12 phrases) ; **commandes de navigation en mode épellation** (curseur gauche/droite, suppr caractère — nouvelles intentions + injection de touches).
2. **Étape 3** : cohérence inter-souffles v1 complète (accords au 2ᵉ passage) + prosodie → ponctuation.
3. **Étape 4** : panneau « C'était une commande » trié par proximité phonétique.
4. **Étape 5** : MFA + LoRA (choix validés 13/11), ROCm Windows preview en premier.

---

## Session 11 - 14 Novembre 2026 (après-midi) : Test complet utilisateur, purges, analyse forensique & 5 correctifs (`79149e1`)

### 1. Test complet de l'utilisateur (12:15–13:00, Notepad++)
- **Texte dicté reconstruit** depuis `logs/injection_trace.jsonl` (script `$TEMP/opencode/reconstruct_dictation.py`) : retour d'expérience détaillé avec artefacts STT (« goiches ch'il », « Pizdir », « Véronique. » pour « au repos »…).
- **Précisions recueillies via l'outil `question`** (5 défauts clarifiés, cf. §3) ; vérifié : « Corriger ça » = 12 reconnaissances/exécutions dans la session (y compris déformé « Grégale ça »), le mode épellation rejette explicitement, le filet OTAN absent faute d'enregistrement `nato_*`.

### 2. Purges demandées par l'utilisateur (remise à zéro avant nouveau système)
- **`user_data/corrections_learned/` vidé** (8 WAV + `corrections_log.jsonl`) : l'utilisateur repart à zéro avec le nouveau système de correction (variantes d'accord, casse, 9 choix) ; la matière première LoRA des anciennes « Corriger & Apprendre » est abandonnée volontairement.
- **Conservés** : `user_data/learned_rules.json` (formes orales de commandes) et `user_data/snapshots/` (copies de sauvegarde) — demandes explicites non incluses.
- Clarifié avec l'utilisateur : **aucun entraînement n'est possible aujourd'hui** (étape 5 non implémentée : ni MFA, ni LoRA, ni script ; corpus trop maigre de toute façon) — le studio ne fait qu'enregistrer.

### 3. Analyse forensique → 5 causes racines (exploration en sous-agent, rapport `ses_e26008fe…`)
| # | Symptôme remonté | Cause racine localisée |
|---|---|---|
| 1 | Espace avant la virgule (` ,il y a…`) | `shadow_buffer.replace_last` réajoutait l'espace initial **sans tester** `NO_SPACE_BEFORE` (constante déjà existante dans `coherence.py`) |
| 2 | Épellation toujours insérée en fin (clic au milieu ignoré) | `SpellingWindow.append_text` = concaténation + `setText` ; aucun `cursorPosition()`/`insert()` côté UI, `main.py` réécrivait tout `proposed` en fin |
| 3 | « espace » non reconnu + espace manuel ajouté entre 2 mots épelés supprimé au souffle suivant | (a) `NATO_SPACE_TOKENS` en correspondance **exacte** sans tolérance (contraire aux 26 lettres) ; (b) chaîne de 4 `.strip()` destructeurs (`main.py` ×3, `hud.py` ×1) puis réécriture totale du champ |
| 4 | 🔑 « Forme orale » ne fait rien (log `spoken_form_added ok:false` ×2 pour « Birgule, ») | `SpokenFormStore.add` refuse tout texte sans clé alphanumérique : `command_keys(",")` = `[]` (ponctuation réduite à des espaces dans `rules.py`) |
| 5 | « Couper Phénix » → STT `Coupé Phoenix` injecté en dictée alors que l'empreinte DTW `cmd_couper_phenix` matchait | `plausibility.py` : override DTW conditionné à `acoustic_confidence < 0.45` — la confiance STT (0.8) primait sur la voix enregistrée |

### 4. Décision utilisateur : filet DTW = priorité absolue
- Validé par `question` : **si `acoustic_fp_match is not None`, le DTW gagne toujours** (le seuil de distance DTW de `match_command` filtre déjà les faux positifs ; segments 0,25–1,85 s, distance ≤ 0,16).

### 5. Implémentation en 3 sous-agents parallèles (fichiers strictement découplés)
- **Agent A (défauts 1 + 4)** : `shadow_buffer.py` import `NO_SPACE_BEFORE` + test `formatted_new[:1]` (pas d'`IndexError`) ; `rules.py` `command_keys` : la branche de repli accepte un signe non vide comme clé (round-trip add→`_build_index`→`_substitute` vérifié sur tous les usages — `punctuation.py`/`symbols.py` non impactés, entrées de tables = phrases FR). Messages HUD existants déjà exacts (succès/refus).
- **Agent B (défauts 2 + 3)** : `hud.py` +118/−23 — `spell_edit.insert(chunk)` sous drapeau programmatique, positions de curseur **maintenues en thread GUI** (le worker STT ne lit que des `int`, `active_insert_position()`), signaux `Signal(str, int)` avec sentinelle `-1` = conserver ; fonction pure `insert_chunk_at_cursor()` testable sans contrôleur ; les 4 `.strip()` du flux épellation/correction → `strip("\r\n")` (les strips d'application vers le document et `coherence.py` **conservés** — dictée normale inchangée) ; bonus `_nato_space_fuzzy` (famille « espace »/« space » seule : écart ≤ 1 ou pluriel à racine exacte — **découverte : `distance("espas","espace") = 2`**, d'où le 2ᵉ critère ; normalisation « es pace » → « espace »). Piège PySide6 : `cursorPositionChanged` transmet **(ancienne, nouvelle)**.
- **Agent C (défaut 5)** : `plausibility.py` — bloc DTW **court-circuit en tête** d'`arbitrate()` (avant confusions phonétiques, alternatives, énoncé court), condition réduite à `acoustic_fp_match is not None` ; `adaptation_reason` DTW conservé ; commentaire documentant le risque dictée longue (écarté par le filtre durée/distance).
- **Non traité (signalé)** : STT rendu **vide** + match DTW → toujours ignoré (`return empty` avant le bloc DTW, comportement inchangé) — à décider.

### 6. Validations
- **Suite : `131 passed, 3 deselected`** (101 → 131, +30 tests : `test_shadow_spacing` ×4, `test_symbols` +2, `test_spelling_cursor` ×14, `test_space_token_fuzzy` ×6, `test_phase2` +4) — relancée par la session parente après intégration des 3 agents.
- **Smoke offscreen `smoke_fix5.py`** : insertion au milieu `aXbc`, espace final conservé, forme orale `,` acceptée, arbitre DTW avec conf 0.85 → « Couper Phénix », `CorrectionWindow` réelle → **SMOKE OK**.
- **Commit `79149e1` poussé** (11 fichiers, +706/−46).

### 7. En parallèle : inventaire de l'aide Dragon (sous-agent en cours)
- CHM extraits dans `$TEMP/opencode/dragon_help/` (`cmd_browser.chm` = navigateur de commandes + `tagent_fra.chm` = aide FR, 224 pages) via 7-Zip → rapport `[DÉJÀ]/[PARTIEL]/[ABSENT]` en attente, servira de base à la discussion **lexique multi-langues / SQLite** ouverte par l'utilisateur (ma position : inutile pour le lexique d'accords chargé en mémoire, pertinent probablement à l'étape 5 — phonétique/fréquences/écritures concurrentes).

### 8. Prochaine étape prévue
1. Rapport inventaire Dragon → discussion fonctionnalités + lexique/langues (choix utilisateur).
2. **Étape 2 (reste)** : enregistrement studio (26 `nato_*` + 12 `corpus_*`) ; navigation en mode épellation (curseur/suppr — le clic-au-curseur est fait, il manque les commandes vocales de navigation).
3. Étapes 3 → 4 → 5 (LoRA).

---

## Session 12 - 15 Novembre 2026 : Inventaire complet de l'aide Dragon 15 (rapport `docs/INVENTAIRE_DRAGON_15.md`)

### 1. Contenu du rapport
- **210 fonctionnalités** de Dragon NaturallySpeaking 15 Pro (FR) inventoriées sur **8 thèmes** (Dictée/transcription 23 · Correction/sélection 22 · Contrôle Windows/souris/clavier 50 · Mise en forme 19 · Applications métier & Web 34 · Vocabulaire/apprentissage 20 · Commandes personnalisées/Explorateur 24 · Ergonomie/barre/aide 18), chacune notée `[DÉJÀ]` / `[PARTIEL]` / `[ABSENT]` avec commande exacte + 1 ligne de description + 1 ligne d'état Phénix.
- **Sous-section dédiée « Correction/sélection par citation de texte »** : mécanisme de fond sans OCR (Contrôle total du texte = modules compatibilité `dgn*.dll`/`web_ie.dll` + **MSAA/Active Accessibility**), recherche du fragment dans le texte réel à partir du curseur, **plafond 70 caractères**, options sens de recherche / menu↔épellation, numérotation des instances, et confirmation que **Google Docs/Word Online sans module = `« Corriger <mot> »` impossible** → dépendance UIA avérée.
- **Top 14** des fonctionnalités absentes désirées + 2 absences **volontaires** (Boîte de dictée, mode caché).
- Sources : aide FR installée (291 `.htm` / 288 exploités) + CHM extraits `$TEMP/opencode/dragon_help/` (224 `.htm`, 158 stubs) ; 943 formes de commandes indexées. **Consultation seule, tout reformulé — aucun texte Nuance recopié.**

### 2. Priorités qui sortent du rapport
1. **Citation de texte via UIA (`« Corriger <texte> »` / `« Sélectionner <texte> »`)** — le cahier la promet (Module 1), la couverture `TextPattern`/`ValuePattern` n'est **pas confirmée** : priorité n°1.
2. **« Corriger N segments précédents » (« N souffles »)** — Dragon n'a aucune équivalence (uniquement unités de texte) : innovation Phénix **à valider avec l'utilisateur** avant implémentation.
3. **Étape 2 studio (enregistrement 26 `nato_*` + 12 `corpus_*`) reste le bloqueur** du filet acoustique — rien de nouveau sur ce point.

### 3. Note de positionnement
- Le journal est resté en l'état : cette entrée est placée **en toute fin de fichier** (après Session 10, physiquement dernière), conformément à la consigne « à la fin du fichier ».

---

## Session 13 - 15 Novembre 2026 (après-midi) : Diagnostic forensique des 2 échecs du test, fixes « fragment » + « curseur partagé », remontée de l'étape 5

### 1. Diagnostic forensique — session `session_20261115_114624` (11:46–12:13)
Deux échecs répertoriés par l'utilisateur, diagnostic mené sur `logs/injection_trace.jsonl` + `logs/dictation_debug.jsonl` (croisement chronologique par `clock`/`ts` ; scripts `$TEMP/opencode/diag_15*.py`).

**Échec A — formes orales ajoutées mais jamais appliquées :**
- `spoken_form_added ok:True ×2` (11:49:59 / 11:50:04) : `heard` = **la phrase entière** « Je teste une fois de plus mon application Bergune. » / `written` = la même phrase **sans le dernier mot** (l'utilisateur avait supprimé le mot).
- La phrase n'a **jamais été rejouée** à l'identique ensuite (vérifié dans tous les logs) ; tentative « Berghine, » à 12:02:59 **détournée en « Au repos »** (faux positif DTW, conf 0.43 acceptée) ; « Virgule, » → « virgule ».
- **Cause = granularité** : la clé était la phrase entière → déclenchement impossible en pratique (l'utilisateur attend le déclenchement sur le FRAGMENT).

**Échec B — clics/curseur ignorés :**
- Chronologie : 11:59:34 entrée épellation (curseur en fin du pré-rempli), 11:59:42 clics Correction **puis** Épellation, 11:59:46 insertion du « d » dicté **en fin** (« …Davidine » → « Davidined »), 12:00:07-09 **4 clics** sur Épellation → 12:00:24 « Davidinedd » encore en fin.
- **Repro QTest hors écran** (`$TEMP/opencode/repro_click.py`) : le clic dans `spell_edit` **est** bien suivi (curseur tracké), mais le clic dans `correction_edit` **pendant que l'épellation est ouverte** était **ignoré** (`active_insert_position()` ne lit que le champ épellation).
- **Géométrie** : champ `spell_edit` = bande de **30 px sur 192 px** (titre 52 px, instructions 52 px) ; fenêtre Épellation posée **juste sous** la fenêtre Correction (gap 13 px) → clics probables ratés sur le titre/labels. Limite du diagnostic : `target_window` dans les logs = fenêtre **active** au moment du clic (`profile/snapshot.py`), jamais le widget visé.
- Anomalies constatées au passage : espaces surnuméraires **confirmés corrigés** par l'utilisateur ; `replace_last` positionné correctement dans les traces.

### 2. Fixes implémentés (2 sous-agents parallèles, fichiers découplés)
**Fix A — forme orale = fragment par diff** (`postprocess/symbols.py`, `main.py`, `tests/test_symbols.py`) :
- `split_spoken_fragment(heard, written)` : alignement jeton à jeton (préfixe puis suffixe communs, comparaison normalisée via `command_keys` par jeton) → ne garde que la partie qui change : « … application Bergune. » / « … application Berghine » → (`Bergune.`, `Berghine`).
- `SpokenFormStore.add` : candidats ordonnés **[fragment, phrase entière]** (repli si fragment non exploitable, ex. suppression pure du mot = cas du 15/11), gardes inchangées, nouvel attribut `last_recorded`.
- `add_spoken_form_from_correction` : message HUD + log `spoken_form_added` enrichis de `form_heard`/`form_written` (le fragment **réellement enseigné** est affiché).
- +5 tests → `test_symbols.py` = **17 passed**.

**Fix B — curseur partagé + champ agrandi + log des clics** (`ui/hud.py`, `main.py`, `tests/test_spelling_cursor.py`) :
- `_shared_insert_pos` : posé par **tout** `cursorPositionChanged` des deux champs (clic OU réécriture programmatique) → `active_insert_position()` le retourne en priorité = **le dernier champ touché fait foi** (les deux champs sont des miroirs du même texte en attente) ; le clic dans la fenêtre Correction n'est plus ignoré.
- Nouveau `eventFilter` du HUD installé sur `spell_edit`, `correction_edit` et les 2 fenêtres → signal `edit_field_clicked(field, cursor)` → log `edit_field_clicked` (`epellation`/`correction`/`fenetre_epellation`/`fenetre_correction`) = diagnostic de clic à distance pour la prochaine session.
- `SpellingWindow._build_ui` : `spell_edit` remonté en **indice 0** du layout + `setMinimumHeight(60)` (30 → 60 px, décision « champ agrandi ») ; champ Correction intact.
- +5 tests → `test_spelling_cursor.py` = **19 passed**.

### 3. Décisions utilisateur (questions 15/11)
1. **Formes orales = « un MOT isolé »** (option 1 validée) + grande idée exprimée : pouvoir **sélectionner des parties de souffle (ou des mots de deux souffles différents)** pour corriger exactement ce qu'on veut → exige un système de **reconnaissance d'un texte même s'il n'a pas été dicté** (hors fragments) → **chantier à part, indexé avec la citation UIA** (ne change pas le travail immédiat).
2. **Curseur = « les deux champs + champ agrandi »** (option validée) — implémenté intégralement.
3. **« Corriger ça » Dragon-like** : si une **sélection existe dans le document** (même sans rapport avec le dernier souffle) → « ça » = la sélection ; sinon « ça » = le dernier souffle. **« Corriger \<texte\> »** (nommer un texte n'importe où + **gestion des occurrences** si plusieurs) = nécessite la reconnaissance de texte hors limites → **UIA TextPattern**.
4. **Priorité** : « Corriger \<texte\> » placé **APRÈS l'entraînement** (l'utilisateur a demandé la remontée de l'étape 5 en raison de la fatigue → reconnaissance dégradée).

### 4. Nouvel ordre de roadmap (validé)
1. ~~Fixes des 2 échecs du 15/11~~ → **FAIT (cette session)**.
2. **Étape 5 — entraînement du modèle (REMONTÉE en tête des tâches restantes)** : validation ROCm Windows preview → alignement forcé MFA → corpus de textes naturels dictés → LoRA Whisper FR.
3. **Étape 2 (reste)** : enregistrement studio (26 `nato_*` + 12 `corpus_*`) + navigation vocale en mode épellation — *les sessions d'enregistrement peuvent être regroupées avec celles du corpus d'entraînement*.
4. **« Corriger ça » (sélection sinon dernier souffle) + « Corriger \<texte\> » (citation UIA, occurrences)** — après l'entraînement, conformément au choix 15/11.
5. Étapes 3 → 4.

### 5. Validations
- **Suite complète : `141 passed, 3 deselected`, exit 0** (baseline 131 → +10 tests des 2 fixes).
- **Repro clic après fix** : champ `spell_edit` à `y=8, h=60` ; clic dans le champ Correction avec épellation ouverte → position active = **43** (au lieu de 6 avant) ; insertion au bon endroit.
- **Smoke `smoke_fix5.py` offscreen : SMOKE 5 CORRECTIFS OK** (exit 0).
- Aucune régression des 5 correctifs du matin (`79149e1`).
- **Commits** : code+tests = **`cc2c4e5`** ; docs (ce journal + `PROMPT_REPRISE.md` §4/§4bis roadmap réordonnée) = commit suivant ; push des deux en fin de session.

### 6. Anomalies ouvertes / restes signalés
- **DTW faux positif** : « Berghine, » → « Au repos » (conf 0.43) — à surveiller (le filet DTW reste prioritaire par design, décision 14/11).
- **Reste non traité du matin** : STT rendu **vide** + match DTW toujours ignoré (`return empty` avant le bloc DTW) — **décision utilisateur en attente**.
- Erreurs STT du 15/11 à resouler par l'étape 5 : « Bergune », « Tasha à fer », « ma diction… », latence médiane 498 ms / p90 673.

### 7. Validation ROCm Windows sur la RX 5700 XT (étape 5, premier bloqueur) — **SUCCÈS**
- **Installation isolée** (le `.venv` DirectML d'inférence **n'a pas été touché**) : venv uv séparé `%TEMP%\opencode\venv-rocm` (Python 3.11.9) + `uv pip install --index-url https://stable.repo.amd.com/rocm/whl-next/ --index-strategy unsafe-best-match "torch[device-gfx1010]==2.14.0+rocm10.1.0"` → `torch 2.14.0+rocm10.1.0`, `rocm-sdk-core/device-gfx1010/libraries 10.1.0` (~1,5 Go). Le pin `+rocm10.1.0` force le bon wheel (l'index AMD héberge aussi torchvision/torchaudio si besoin).
- **Support officiel** : la RX 5700 XT (RDNA1, `gfx1010`) est dans les wheels **multi-arch AMD** depuis ROCm 7.13 → **ROCm 10.1.0 stable (10/2026) la couvre nativement** ; aucun `HSA_OVERRIDE_GFX_VERSION` nécessaire ; pilote Adrenalin `32.0.21045.16010` compatible.
- **Résultats du banc (`$TEMP/opencode/test_rocm.py`, exit 0)** :
  - `torch.cuda.is_available() = True`, **HIP 7.16.26385**, GPU = AMD Radeon RX 5700 XT, arch `gfx1010:xnack-`, **VRAM 8.6 Go**, **bf16 = supporté** ;
  - matmul **fp16** 4096² : 35,81 ms (**3,84 TFLOPS**) ;
  - **SDPA + backward** : OK (grads alimentés) ;
  - **AdamW × 20** (proxy pas LoRA) : 12,3 ms/step, pic mémoire **0,33 Go** ;
  - **bloc Transformer type Whisper** (d_model 1024, fp16, 1500 jetons = fenêtre 30 s) + backward : **429 ms, pic 1,05 Go**.
- **Verdict** : la carte est **apte à l'entraînement LoRA** prévu au 13/11 (gel encoder bas, couches hautes + decoder) — le LoRA sur Whisper Large-v3-Turbo (809 M) tient dans 8,6 Go ; le full fine-tuning des ~3 B reste hors budget (confirmé). L'utilisateur notait « carte graphique moyenne » : le plan validé (LoRA + augmentation légères) est précisément dimensionné pour ça.
- **Reprise exacte** : `venv-rocm\Scripts\python.exe $TEMP/opencode/test_rocm.py` ; prochain jalon = banc LoRA réel (`transformers` + `peft` + `accelerate` dans `venv-rocm`) puis corpus MFA.

### 7bis. Banc LoRA de bout en bout (`tools/lora_bench.py`) — **SUCCÈS**
- **Stack installée dans `venv-rocm`** (venv d'inférence `.venv` intact) : `transformers 5.23.0`, `peft 0.21.3`, `accelerate 1.15.0`, `numpy`, `tiktoken`, `safetensors`.
- **Poids PyTorch téléchargés une fois** : `openai/whisper-large-v3-turbo` safetensors (~1,6 Go, cache HF `models--openai--whisper-large-v3-turbo`). Réponse à la question de l'utilisateur : les formats **ONNX déjà présents** (`models/cache/…encoder_fp16_dynamic.onnx` 1,2 Go + cache `onnx-community`) restent **le chemin d'inférence DirectML de l'app** — un export ONNX est un graphe figé, sans différentiation, donc **inutilisable pour entraîner** ; le safetensors est la matière première du LoRA (téléchargement unique, réutilisé pour tout l'entraînement). À l'issue de l'entraînement, l'adaptateur sera fusionné puis **ré-exporté en ONNX** pour remplacer le fichier d'inférence.
- **Forme du modèle** : 808 878 080 params au total ; **128 bandes mel** (large-v3, pas 80 — erreur corrigée) ; vocab 51 865 ; batch synthétique `input_features (1, 128, 3000)` (Whisper impose 3000 trames = 30 s, tout segment réel est paddé → coût par pas constant) + `labels randint(0, 51865, (1, 44))`.
- **Bug PEFT 0.21 ↔ transformers 5.23 (corrigé par shim)** : `PeftModelForSeq2SeqLM.forward` transmet toujours `input_ids=None`/`inputs_embeds=None` alors que `WhisperForConditionalGeneration.forward` est en `input_features` → les valeurs tombent dans `**kwargs` jusqu'à l'appel du décodeur (`modeling_whisper.py` l.962-971) qui reçoit déjà `input_ids=` en nommé → `TypeError: got multiple values for keyword argument 'input_ids'` (**ni le checkpointing ni son absence ne changent rien** — vérifié). Shim dans `tools/lora_bench.py` : wrapper sur `model.get_base_model().forward` qui poppe ces deux clés si `None` (commenté « à supprimer dès que l'amont corrige »).
- **Résultats (exit 0, 5 pas chronométrés après 1 pas de chauffe)** :
  - modèle chargé en 2-4 s (cache local) ; LoRA `q_proj/v_proj` r=16 α=32 : **3 276 800 params = 0,40 %** entraînables, le reste gelé ;
  - **fp32 + checkpointing : 9,19 s/step, pic 11,39 Go** ; sans checkpointing : 9,14 s / 11,39 Go (le checkpointing ne change rien ici — mémoire dominée par les poids/allocateur ROCm, pas les activations) ;
  - **poids gelés en bf16 (`--bf16-weights`) : 6,46 s/step (−30 %), pic 10,12 Go / réservé 10,54 Go** — configuration de référence fenêtre 30 s ;
  - perte synthétique décroissante (12,6 → 11,2 sur 5 pas), normes de grad ~10-12 (clip 1.0 actif).
- **Patch variable-length (`--frames < 3000`) — levier décisif (mesuré 16/11)** : Whisper impose 3000 trames (check strict `modeling_whisper.py` l.609-613) et calcule les positions pour 1500 jetons (l.619) ; le banc assouplit les 2 points (conv1 s=1, conv2 s=2 → jetons = trames/2, trames paires). **Les utterances réelles font 3-10 s, pas 30 s** — sans ce patch tout segment serait paddé à 3000 et coûterait le prix d'une fenêtre pleine :
  - **500 trames (5 s) batch 1 : 0,44 s/step, pic 2,33 Go** (vs 6,46 s / 10,12 Go en 30 s) → **×15** ;
  - **500 trames batch 8 : 2,21 s/step, pic 6,31 Go, ~13 019 segments/heure** — **meilleure config mesurée** ;
  - 500 trames batch 12 : 4,66 s/step (9 265/h) ; batch 16 : 7,89 s (7 299/h) — au-delà de 8 la parallélisation recule ;
  - 1000 trames (10 s) batch 4 : 2,51 s/step (5 747/h) ; batch 8 : 10,59 s (2 720/h, OOM en fin de run) ;
  - **batch > 1 en 30 s padde = OOM** (batch 2 : 14,04 Go alloués, `torch.OutOfMemoryError`) — la WDDM autorise un débordement en mémoire partagée mais impose une limite dure (~13-14 Go déclarés) ;
  - **projection corrigée : 2 000 segments de ~5 s ≈ 9 min/époque** (batch 8, 13 019 seg/h) au lieu des 3,6 h en fenêtre 30 s padée — un entraînement de quelques heures couvre plusieurs époques sur corpus réel.
- **Limite connue** : l'allocateur ROCm déclare 10-11 Go sur 8,6 Go de VRAM physiques en fenêtre 30 s (débordement mémoire partagée WDDM — la pilote affiche 8,6 Go occupés / 0 libres, la doc AMD avertit que les process peuvent utiliser la mémoire système au-delà de la VRAM). Aucun OOM ni ralentissement observé en 30 s ; en segments 5-10 s on reste à 2,3-6,3 Go, largement dans les clous. **Config retenue pour l'entraînement réel : bf16 + frames ~500-1000 + batch 8**.
- **Reprise exacte** : `$env:PYTHONIOENCODING='utf-8'; & "$env:TEMP\opencode\venv-rocm\Scripts\python.exe" tools\lora_bench.py --steps 4 --bf16-weights --frames 500 --batch 8` ; options : `--steps N`, `--frames <pair>`, `--batch N`, `--bf16-weights`, `--no-checkpointing`.
- **Prochain jalon étape 5** : corpus de textes naturels dictés → alignement MFA local → script d'entraînement LoRA réel (réutiliser le shim + patch variable-length + config bf16/batch 8 du banc) → fusion + ré-export ONNX.

### 8. Décisions produit 16/11 : exigence de manuel (lecture initiale + adaptation ≤ 1 h/1 h 30) + adaptation « au fil de l'eau » en phase 2
- **Exigence validée par l'utilisateur — contenu du MANUEL (pas un objectif interne)** : le manuel doit **prévenir l'utilisateur** qu'avant de pouvoir utiliser correctement le produit il devra : (1) effectuer une **lecture initiale** — durée à estimer plus tard — puis (2) **laisser le système s'adapter à sa voix**. **Contrainte forte : ce temps d'adaptation, surtout, ne doit pas dépasser 1 heure (1 h 30 au maximum)** — « on ne doit pas demander à l'utilisateur d'immobiliser son poste pendant trop longtemps ». Reformulations de l'utilisateur le 16/11 : d'abord « le mieux possible » (et non « le moins possible »), puis clarification du statut (contenu du manuel, pas objectif chiffré) et de la borne (1 h, 1 h 30 max sur l'immobilisation du poste).
- **Faisabilité chiffrée (borne de 1 h/1 h 30)** : 20 min de dictée ≈ 1 200 s de parole ≈ 240 segments de 5 s → au débit mesuré (13 019 seg/h, config bf16 + batch 8) = **~1 min par époque** ; même avec MFA, augmentation et plusieurs époques, le total reste très en dessous de l'heure — la contrainte d'immobilisation est large.
- **Phase 2 — adaptation au fil de l'eau (demande utilisateur)** : consommer en continu les échantillons déjà collectés par la correction « Corriger & Apprendre » (Action A → `user_data/corrections_learned/` : WAV + `corrections_log.jsonl`, `main.py::_save_learned_correction_sample`) pour réentraîner périodiquement l'adaptateur LoRA (fin de session ou après N corrections), avec les snapshots existants (`snapshot_manager.create_snapshot("avant_correction")`) comme garde-fous anti-dérive.
- **État exact du « déjà fait »** : la **collecte** des échantillons d'apprentissage est **en place et testée** (séparateur texte/acoustique `is_textual_only_correction` — une correction de ponctuation/casse ne pollue jamais l'apprentissage audio) ; la **boucle d'entraînement qui consomme cette collecte n'a jamais existé** (le LoRA réel n'était pas fait — c'est l'étape 5 en cours). Le cahier des charges (Module 3) et la roadmap (`PROMPT_REPRISE` §4) ont été mis à jour en conséquence.

### 9. Corpus d'étalonnage créé (sous-agent linguiste-phonéticien/orthophoniste) — 16/11
- **Demande utilisateur** : créer un corpus de phrases naturelles couvrant tous les phonèmes FR, utile aux voix atypiques (pas seulement dysarthriques) sans dégrader la voix standard. Sous-agent `general` lancé en rôle **linguiste-phonéticien spécialiste en orthophonie/troubles de la parole** → **livré, validé**.
- **Livrables** (non commités au moment de la demande, puis validés) :
  - `docs/CORPUS_ETALONNAGE.md` (~700 lignes) : rationale complète (naturalité, couverture, tableau phonème→occurrences→n° de phrases, contrastes, compatibilité MFA, dimensionnement, split éval, besoins complémentaires) ;
  - `corpus/etalonnage.txt` : **384 phrases, une par ligne, format lisible MFA/Whisper**.
- **Conception** : 100 % phrases naturelles parlables (listes interdites, choix 13/11) ; **20 blocs thématiques** ; **bloc de contrastes quasi-minimaux en contexte** (n° 215-235 : b/p, d/t, g/k, v/f, z/s, ʃ/s, ʃ/ʒ, triple nasale, e/ɛ, o/ɔ, u/y, a/ɑ, œ/ø, ɥ, l/r) ; nasales très denses (`ɑ̃` 329, `ɔ̃` 196, `ɛ̃` 117, `œ̃` 63 — distorsion majeure de la dysarthrie) ; phrases courtes « fatigue » (3-13 mots, médiane 8) ; **les 12 phrases studio `corpus_*` existantes réutilisées telles quelles** (n° 34-45) pour rester cohérent avec le manifest.
- **Couverture** (G2P automatisé, indicatif ±10 %) : **les 35 unités phonémiques du FR présentes**, toutes ≥ 50 occurrences sauf `ɑ` (8, allophone de `a`, justifié) ; `ɲ` 50, `ɥ` 65, `w` 92, `ø` 52, `œ` 69, `ə` 540, `ʃ` 115, `ʒ` 144. Vocabulaire : 3 092 mots / 1 175 formes uniques, ~92 % en haut de fréquence Lexique383 → la voix standard n'est pas « tirée » vers un lexique exotique.
- **Dimensionnement** : **≈ 19,3 min @160 mots/min, ≈ 21,3 min @145** (lecteur fatigable) → **cible ~20 min de lecture tenue**, compatible avec le budget manuel « adaptation ≤ 1 h/1 h 30 » (§8). Split éval proposé : phrases n° multiples de 10 (38 phrases, 10 %).
- **Points d'attention pour la suite** : (1) comptage phonémique indicatif — **vérité terrain = dictionnaire MFA**, lancer `mfa validate-dictionary` avant l'alignement ; (2) OOV possibles à préparer en IPA : *Zoé* `/zɔe/`, *Lyon* `/ljɔ̃/` + mots composés à vérifier ; (3) `œ̃/ɛ̃` fusionne à l'oral chez beaucoup de locuteurs (notés séparément pour MFA) ; (4) besoins complémentaires listés §7 du doc mais non produits : vocabulaire personnel, chiffres/symboles oraux, commandes vocales, NATO, prosodie/ponctuation, lexique applicatif ; (5) aucun anglais, aucun doublon (vérifié).
- **Prochaine étape inchangée** : MFA local (installation + dictionnaire FR + `validate-dictionary` sur ce corpus) → script d'entraînement LoRA réel.

### 10. MFA local installé + dictionnaire/acoustique/G2P `french_mfa` + OOV du corpus — 16/11
- **Échec initial (pip)** : `montreal-forced-aligner` installé via pip/uv (`venv-mfa`) **ne fonctionne pas** — le paquet PyPI n'inclut ni ne déclare `kalpy` (bindings pybind11 de Kaldi, le cœur de calcul de MFA 3.x) ; `ModuleNotFoundError: No module named '_kalpy'` à chaque commande. kalpy n'existe pas sur PyPI (que `kalpy-kaldi`, qui exige une compilation de Kaldi → `KALDI_ROOT`) ; la voie officielle est **conda-forge**.
- **Installation réussie via micromamba (Conda léger, isolé)** : `micromamba.exe` + environnement **`%TEMP%\opencode\mfa-conda`** (Python 3.13, `montreal-forced-aligner 3.4.3`, `kalpy 0.10.5`, `kaldi 5.5.1172`, pynini…) depuis conda-forge ; **`mfa version` = 3.4.3, exit 0**. `.venv` et `venv-rocm` jamais touchés. (Ancien `venv-mfa` pip = abandonné.)
- **3 pièges Windows résolus** (à retenir pour le packaging public) : (1) **`MAX_PATH` = 260 caractères** — le fichier `.../scikit-learn/.../__pycache__/test_monotonic_constraints.cpython-313.pyc` dépassait de 262 → extraction ratée, `remove_all: Le répertoire n'est pas vide` en boucle → **cache déplacé vers `%TEMP%\mfa-root`** (chemin final 249 caractères) ; (2) verrous de fichiers (attributs lecture seule) sur le cache → `attrib -r -s -h` + `rmdir` ; (3) **`libsndfile.dll` invisible sans activation Conda** → PREFIXER le PATH (`<prefix>\Library\bin` + `<prefix>\Scripts`) avant chaque appel `mfa`.
- **Modèles téléchargés** : `mfa model download dictionary french_mfa` + `acoustic french_mfa` + `g2p french_mfa` (exit 0) → `Documents\MFA\pretrained_models\` (`french_mfa.dict` 4,6 Mo, 105 731 entrées).
- **OOV du corpus** (script maison contre `french_mfa.dict`) : **21 mots uniques sur 2 965 tokens seulement** (0,7 %) — *Zoé* et *Lyon*, annoncés possibles, sont en fait **dans le dictionnaire**. Les 21 : citron(×2), achetons, aiguisé, mijote, coassent, bondé, klaxonnant, fêtons, quoiqu'il, fournée, croustillantes, filante, rafraîchit, vibre, broutent, ondule, sauvage, scanne, enseignons, ramassons, termines — surtout des formes verbales inflectées rares pour MFA.
- **G2P terminé (16/11)** : 1re tentative **échouée** — passer un *fichier* à `mfa g2p` active le mode « liste de mots » et **ignore `--dictionary_path`** (le filtre OOV n'existe que pour une entrée en *dossier*) → MFA a traité les phrases entières comme des « mots », planté au 1er élément (`min() iterable argument is empty` dans `generator.py:695` — aucune prononciation pour une phrase) et laissé **3 workers G2P orphelins en boucle** (CPU 100 %, à tuer manuellement). **Correction** : `corpus/oov_words.txt` (21 mots, un par ligne) → `mfa g2p corpus/oov_words.txt french_mfa corpus/oov_extra.dict --num_pronunciations 1` = **21/21 en 8,9 s, exit 0**. Prononciations IPA validées (ex. `citron → s i t ʁ ɔ̃`, `rafraîchit → ʁ a f ʁ ɛ ʃ i`, `klaxonnant → k l a k s ɔ n ɑ̃`).
- **Dictionnaire étendu construit** : `corpus/french_mfa_ext.dict` = `french_mfa.dict` (107 172 lignes — format `mot <4 probas optionnelles> phonèmes`, plusieurs prononciations par mot) + `oov_extra.dict` (21) = **107 193 lignes, sans BOM** ; regénérable en une commande (artefact dérivé, non commité, à mettre en .gitignore). Le parseur MFA (`utils.py::parse_dictionary_file`) traite les colonnes numériques comme **optionnelles** → nos lignes G2P au format `mot\tphonèmes` (natif d'export G2P) sont acceptées telles quelles.
- **Prochaine étape** : `mfa validate` sur le corpus (dès que l'audio de lecture existera) → script d'entraînement LoRA réel.
- **Exigence livraison (demande utilisateur 16/11)** : la version publique doit offrir **le même degré d'adaptation** ; **tout embarquer dans l'installateur pas obligatoire** - téléchargement au **premier démarrage** acceptable, mais **l'aide/manuel doit décrire le rôle de chaque téléchargement et prévenir de ce que l'installateur est en train de faire** (quoi/quoi/pourquoi/durée) ; aucune installation externe (Conda/pip) demandée à l'utilisateur. Inscrit au CAHIER_DES_CHARGES Module 3 + PROMPT_REPRISE §4.

### 11. Script d'entraînement LoRA réel `tools/lora_train.py` + smoke test OK — 16/11
- **Écrit** : manifeste JSONL en entrée (`{"audio": ..., "text": ...}`) → `soundfile` + `soxr` (16 kHz, mono, troncature `--max-frames`…) → `WhisperFeatureExtractor(padding=False)` mel **variable-length** (patch du banc) → labels `tokenizer(text)` → **collate padding par batch** (jamais à 3000 trames) → AdamW lr 1e-4, clip norm 1.0, autocast bf16 sur poids gelés + adaptateurs q/v r=16 fp32 → logs `training_log.jsonl` + `run_config.json` → `save_pretrained` (adaptateur PEFT). Réutilise à l'identique le **shim PEFT 0.21 ↔ transformers 5.23** et le **patch variable-length** du banc.
- **Terminologie** (question utilisateur 16/11) : « epoch » traduit « époque » = **calque fautif** — en français on dit **« passage »** (un passage = un tour complet sur tous les segments du corpus ; 3 passages = le modèle voit chaque phrase 3 fois). Tous les affichages/flags du script corrigés (`--passages`, logs).
- **Smoke test OK (exit 0)** : mini-manifeste synthétique 6 WAV 16 kHz (3-7 s, `%TEMP%\opencode\smoke_lora`) → `--passages 1 --steps 3 --batch 2 --max-frames 600` → **perte 7,41 → 6,96**, 0,7-1,7 s/pas, adaptateur **13,1 Mo** + `run_config.json` + log JSONL sauvegardés. Labels vérifiés : **SOT `50258` en tête, EOT `50257` en fin** (format seq2seq correct). Avertissement `float(loss)` corrigé (`loss.detach()`).
- **Dépendances ajoutées à `venv-rocm`** : `soundfile 0.14.0` + `soxr 1.1.0` (ni scipy ni librosa — feature extractor Whisper pur torch). Avertissements MIOpen gfx1010 (CK grouped conv absent) = **inoffensifs**, le kernel HIP reste utilisé.
- **Débit mesuré sur ce smoke** : ~4 878 seg/h (batch 2, 600 trames) — le batch 8/500 trames du banc reste la config visée (~13 000 seg/h).
- **Prochaine étape** : `mfa validate` (dès audio de lecture) → alignement MFA → **manifeste réel** (384 phrases) → entraînement complet → fusion LoRA + ré-export ONNX.

### 12. Studio enrichi (434 prompts, 384 phrases corpus) + 3 exigences de réutilisation — 16/11
- **Studio enrichi (`cc11f80`)** : `calibration_studio.py` charge désormais `corpus/etalonnage.txt` au démarrage → **384 prompts `utt0001`..`utt0384`** (mappés sur `etalonnage_mfa.txt` pour le jumelage WAV MFA) en plus des 50 existants = **434 prompts** ; si le fichier est absent (installation publique), seuls les 50 intégrés restent. Test mis à jour : **6/6 OK**. Studio **lancé** pour l'enregistrement (démarrage = premier manquant = `nato_alpha` ; 26 OTAN + 12 `corpus_*` restent avant les 384 utt).
- **3 exigences utilisateur (16/11), consignées CAHIER Module 3 + PROMPT_REPRISE §4** : **(1)** relancer le **Studio depuis l'application principale** à volonté (refaire/compléter tout le corpus) ; **(2)** depuis « Corriger ça », après adaptation du texte, **enregistrer aussitôt l'audio de la reformulation** (Studio en mode « correction → prompt ») ; **(3)** bouton **« Écouter le segment »** dans l'interface de correction pour décider si corriger ou jeter — **l'audio existe déjà** (`ShadowSegment.audio_pcm`, 25 derniers souffles dans `shadow_buffer`) : pas de nouveau collecteur, juste un bouton de lecture + accès à la `CorrectionWindow`.
- **Suite immédiate** : enregistrement du corpus par l'utilisateur (20 min) → `mfa validate` + alignement → manifeste réel → entraînement complet.

### 13. Studio : arrêt automatique VAD + accès depuis l'app ; diagnostic/réparation F8-F9 — 17/11
- **Arrêt automatique du segment (fini le clic « Arrêter »)** : `BreathSegmenter` (VAD Silero existant, `silence_pause_ms=800`, `min_speech_ms=224`, `max_segment_s=60`) branché dans le callback audio du Studio ; le flag posé dans le thread audio est consommé par `_update_meter` (thread GUI) → `_stop_recording()` (méthode extraite de `_toggle_recording`). Le bouton affiche « 🎙️ Parlez… l'arrêt est AUTOMATIQUE après la fin de votre phrase ». **Aucune hésitation attendue en studio** : l'utilisateur jette les segments dégradés (🔄) plutôt que de chercher le point d'arrêt.
- **Enchaînement automatique (déjà en place `1330eff`)** : 500 ms après ✅ Valider ou 🔄, l'enregistrement suivant démarre seul. Seul clic restant : ✅ ou 🔄 par segment.
- **Accès au Studio depuis l'application (exigence « vraiment besoin » 16/11)** : bouton **[🎙️ Studio]** du HUD + commande vocale **« Ouvrir le studio »** (intent `OPEN_STUDIO`, 6 formes testées, bloqué en mode épellation) → `open_calibration_studio()` : fenêtre unique réutilisée, reprise au premier prompt manquant, **dictée mise en veille** (`toggle_sleep("studio")`) pour ne pas faire deux flux micro sur le même device, **réveil automatique à la fermeture** (`closeEvent` → `on_close` → `_on_studio_closed`). La commande vocale (thread STT) passe par le signal `HUDSignals.studio_requested` (ouvrir une fenêtre depuis le thread STT n'est pas sûr) ; le clic bouton appelle le callback directement. Bug attrapé au lancement : `NameError: on_open_studio` dans `_build_ui` (paramètre `__init__` au lieu de `self.`) — corrigé.
- **Diagnostic F8/F9 « ça ne fonctionne pas » (hypothèse focus de l'utilisateur — FAUSSE)** : `pynput` est un **hook global Windows** (`SetWindowsHookEx`), le focus n'entre pas en jeu — confirmé en live : F8/F9 injectés depuis un autre processus alors que « Program Manager » est au premier plan → reçus. **Cause réelle : le listener clavier de l'app était muet** alors que le listener souris du même `GlobalInputMonitor` fonctionnait (`cursor_context_cleared` encore journalisés). Le hook isolé (même pynput, même config) voyait les touches → problème dans l'app, pas dans pynput/Dragon (F8 ne fait rien sur Dragon, vérifié).
- **Réparation (`e117040`)** : (1) `_on_key_press` enveloppé dans try/except — **une exception non interceptée dans un callback pynput tue silencieusement le thread du listener = plus aucun raccourci**, avec journal `hotkey_error` ; (2) trace `hotkey_seen` pour F8/F9 (preuve de réception) branchée sur `injection_logger` via `on_debug` ; (3) **le moniteur démarre désormais AVANT le chargement du moteur** (avant : F8/F9 inertes pendant plusieurs secondes de chargement, et muets si le chargement échouait) — `toggle_mute`/`toggle_sleep` ignorent proprement (`engine_not_ready`) tant que le moteur n'est pas prêt.
- **Preuve live** : `hotkey_seen` → `mic_state_changed` (F8 ×2) et `hotkey_seen` → `sleep_state_changed` (F9) dans la foulée, quel que soit le focus. **Tests ajoutés (`tests/test_hotkeys.py`, 4 tests)** : dispatch F8/F9, survie du callback à une exception (+ journal), touches inconnues ignorées, pas de journal si `on_debug=None`.
- **Suite complète : 151 passed, 3 deselected** (143 avant + 4 studio/commandes déjà verts + 4 hotkeys). Commit + push `e117040`.
- **Note venv (question utilisateur 17/11)** : l'utilisateur veut à terme tout installer sur son Python système (production) et supprimer le venv — **conservé pour l'instant** (filet de dev, rien à voir avec la livraison) ; « sortir du venv » = sujet du packaging production (installateur + téléchargement au 1er démarrage, §10).
- **Retour utilisateur 17/11 (exigence 4, CAHIER Module 3 + PROMPT §4bis)** : l'enregistrement prompt par prompt est **« extrêmement long »** (retour à 70/434 en cours de session) — **pour le futur du produit**, prévoir un mode **« lecture longue »** (bloc de phrases lu d'une traite, 1 clic par bloc, découpage VAD + segments/manifeste produits par l'alignement MFA, rejet individuel du seul segment fautif) ou la **dictée naturelle continue** (l'utilisateur lit le corpus dans son éditeur, l'app capture les segments — zéro clic). Rien ne change au Studio tant que l'utilisateur enregistre (choix explicite « ne change rien pour moi »).
- **Suite immédiate** : **enregistrement du corpus EN COURS par l'utilisateur** (Studio lancé 17/11, auto-stop VAD + enchaînement actifs ; retour à 70/434) → `mfa validate` + alignement → manifeste → entraînement complet.

### 14. Mode « Lecture guidée » zéro clic dans le Studio (`f70cfcc`) — 17/11
- **Retour utilisateur** : l'enregistrement prompt par prompt est « extrêmement long » (70/434) ; demande de trouver autre chose, en conservant la capacité de dire « j'ai fourché ». Référence : **wizard d'entraînement Windows Speech Recognition / SAPI** (lecture continue, avancement automatique, pause si incompris) — étudié le 17/11 — mais **sans sa dérive** (Windows garde tout et fait la moyenne après 2 essais ratés = profil pollué).
- **Décision (question 17/11, validée par l'utilisateur)** : appliquer le principe au Studio actuel **sans toucher aux 78 segments déjà enregistrés** (manifeste conservé à l'identique, testé).
- **Fonctionnement (bouton 🚀 « Lecture guidée : ON » par défaut, OFF = validation manuelle ✅/🔄 d'avant)** :
  1. **Avancement sans clic** : fin de phrase détectée par VAD (déjà en place) → transcription STT → **similarité texte** (Levenshtein normalisé, accents/ponctuation/apostrophes ignorés) :
     - **≥ 70 %** → ✅ validation automatique + phrase suivante **seule** ;
     - **45-70 %** → conservé mais marqué **`review`** (⚠️ file de révision, **une seule passe** — anti-boucle `_visited_reviews`) ;
     - **< 45 %** → **audio abandonné** (jamais de moyenne) + **même phrase relue** automatiquement ; **3 essais max** puis dernier essai conservé + marqué `review` ;
  2. **Commande vocale « J'ai fourché »** (ou « Oups », détection fuzzy sur la transcription) :
     - dite **pendant la phrase suivante** (décalage naturel) → **rejette la dernière phrase validée** (`_last_validated_index`), son entrée est retirée du manifeste et elle redevient la phrase à relire ;
     - dite **pendant la lecture de la phrase** (ou phrase lue + commande dans le même segment) → rejet du **segment en cours** ;
  3. **Bouton ⚠️ Réviser (N)** en en-tête : écoute l'audio existant (chargé depuis le WAV) → ✅ garder ou 🔄 refaire ; une seule passe (le flag `review` reste dans le manifeste pour information) ;
  4. **Navigation guidée** : saute les prompts déjà enregistrés, enchaîne les non-enregistrés puis la file de révision, ferme à la fin.
- **Points d'implémentation** : fonctions pures `text_similarity()` / `is_stutter_command()` / `_normalize_for_match()` (module-level, testables) ; `_guided_decide()` prend la décision dans `_stop_recording` (mode guidé) ; navigation `auto=True` préserve la référence « dernier validé » même en cas de saut d'index (les clics ⬅️/⏭ manuels la réinitialisent) ; sans moteur STT chargé → repli sur la validation manuelle (message « moteur pas encore chargé »).
- **Tests : +7 → 158 passed, 3 deselected** (similarité/accents, détection commande, auto-validation sans clic, échec → reprise du même prompt, 3 essais → révision, « j'ai fourché » → rejet du validé, **conservation du manifeste existant**).
- **Suite immédiate** : relancer le Studio pour l'utilisateur (🚀 ON par défaut, un seul clic ▶ au début) → fin d'enregistrement → `mfa validate` + alignement → manifeste → entraînement complet.

### 15. Entraînement LoRA complet OK + surveillance thermique ADL + fusion/export ONNX finetuné branché dans l'app — 18/11
- **Entraînement complet TERMINÉ avec succès (18/11, feu vert utilisateur obtenu la veille)** : `adapters/lora_full` (`adapter_model.safetensors` 12,5 Mo + `adapter_config.json` + `run_config.json` + `training_log.jsonl`) — **540 pas / 10 passages / batch 8**, perte **3,0454 → 0,0032**, 1681 s hors pauses (2,52 s/pas, ~11 422 seg/h) → `RESULTAT: OK`, `TRAIN_EXIT=0`. LoRA q/v r=16 (0,40 %) sur `openai/whisper-large-v3-turbo`.
- **Surveillance thermique écrite + validée en conditions réelles (30 pauses)** : `tools/thermal_guard.py` (`AdlGpuMonitor` via API ADL `atiadlxx.dll` — `ADL2_New_QueryPMLogData_Get`, capteurs EDGE=8/HOTSPOT=27/ACTIVITY=19/POWER=23 — + `CpuMonitor` + `ThermalGuard`) intégré à `tools/lora_train.py` (args `--max-temp/--resume-temp/--max-cpu-temp/--resume-cpu-temp/--thermal-every/--no-thermal`). **Pause GPU 80 °C / reprise 70 °C** ; pause = **arrêt en cours de route dans la RAM** (pas de checkpoint/reprise, choix utilisateur « solution 1 ») ; événement `thermal_pause` journalisé, pauses déduites du temps actif (champs `active_sec`/`thermal_pauses`/`thermal_pause_sec` dans `run_config.json`) — **30 pauses / 320 s** sur la session. Capteur CPU **introuvable sur la machine** (3 voies testées) → ignoré silencieusement (règle « capteur absent = ignoré »). Tests logique de pause (fake) + `py_compile` + `--help` OK.
- **Choix outillage export** : `optimum` absent partout ; `optimum-onnx` exige `transformers<4.58` (venv-rocm = 5.23) → **venv dédié `%TEMP%\opencode\venv-onnx`** (torch 2.15 CPU + transformers 4.57.6 + peft 0.21.3 + optimum 2.x + onnxconverter-common).
- **`tools/export_onnx.py` (nouveau, pipeline complet)** : (1) fusion `merge_and_unload` base + adapter → checkpoint HF ; (2) export ONNX via `optimum.main_export` **`task="automatic-speech-recognition-with-past"`** (sans `-with-past`, `decoder_with_past` n'est PAS exporté) en **fp32 d'abord** — le kwarg `dtype="fp16"` d'optimum 2.x ne convertit que les entrées dummy et produit un graphe mixte `LayerNormalization` refusé par ORT ; (3) conversion fp16 maison (`convert_float_to_float16(keep_io_types=True)`) : **poids internes f16 + IO graph f32, comme la référence onnx-community** ; (4) suppression de `decoder_model_merged` (jamais utilisée par l'app) ; (5) renommage convention `*_fp16.onnx` ; (6) patch dynamique encodeur.
- **3 pièges de conversion fp16 diagnostiqués + corrigés (intégrés dans `_repair_keep_io_artifacts`)** : **(a)** l'encodeur fp32 pèse ~2,4 Go → `infer_shapes` (serialisation protobuf) échoue au-delà de 2 Go → inférence **sans les données externes** puis rechargement dans le proto ; `convert_float_to_float16_model_path` échoue aussi (`NamedTemporaryFile` verrouillé sous Windows) ; **(b)** casts `to=f32` devenus obsolètes (value_info devenues f16, attribut non suivi) → conflit de type ORT ; **(c)** consommateurs internes d'une sortie de graphe laissés sur la tenseur f32 du cast → `MatMul` f16/f32 → rebranchement sur l'entrée f16 du cast ; puis purge + ré-inférence des value_info.
- **Patch encodeur dynamique EXTRAIT en module partagé** : `src/phenix_voice/stt/onnx_dynamic_encoder.py` (`make_encoder_dynamic`/`build_dynamic_encoder_file`) — repris de `engine.py` mais **générique : cibles trouvées par structure** (consommateur de `embed_positions.weight`, constantes Reshape 1D `[-1,1500,...]` → `[0,-1,...]`, découpe `Slice` dynamique des positions) plutôt que par nom de nœud → valide pour le graphe onnx-community **et** pour un export optimum. **Validation : delta max 0.00000** vs patch historique sur 1200 et 3000 trames (même mel, DML). Bug corrigé au passage : constantes Reshape **1D** (`arr.ndim == 1`, pas `>= 2`).
- **`engine.py` branché sur le finetuné** : nouvel arg `finetuned_dir=Path("models/finetuned")` + `_resolve_model_paths()` — les 3 graphes sont pris **en priorité s'ils sont complets**, sinon repli cache HF onnx-community ; encodeur dynamique partagé (suppression du patch codé en dur dans `build_or_get_dynamic_encoder`).
- **Test de transcription comparatif (base vs LoRA, wav réels)** : `cmd_corriger_ca` → base « Corriger ça, » / LoRA « Corriger ça » ; `corpus_01` identique ; `corpus_02` → **« sœur » avec œ** (LoRA plus correct que la base) ; inférence 0,29-0,30 s (pas de régression).
- **Suite complète : 158 passed, 3 deselected** (rien de cassé). Artefacts MFA régénérables ajoutés au `.gitignore` (`corpus/mfa_in/`, `corpus/mfa_aligned/`).
- **Suite immédiate** : commit + push ; l'app/Studio n'ayant pas tourné pendant l'export, **validation terrain à froid** (démarrage app → dictée réelle) avant de considérer l'étape 5 comme close.

### 16. Bug « mute vocal puis F8 ne rallume pas le micro » — cause racine trouvée et corrigée (19/11)
- **Symptôme** : « Couper Phénix » coupe bien le micro, mais F8 ne le rallume plus (et F9 était concerné à l'identique). Le journal montrait `hotkey_seen` bien reçu mais **zéro** `mic_state_changed` en `source=hotkey` (137 entrées en `source=ui` seulement) + une exception `stt_worker_loop` le 19:36:23.
- **Cause racine (3 défauts enchaînés, prouvés par le journal + un test Python isolé)** :
  1. **`hotkeys.py` appelle `on_toggle_mute(source="hotkey", key="F8")`** mais le paramètre de `toggle_mute` s'appelle `source_or_checked` → le `source="hotkey"` atterrit dans `**details` → `log_action(..., source=source, **details)` reçoit `source` **en double** → `TypeError: got multiple values for keyword argument 'source'` (reproductible hors app).
  2. Ce `TypeError` survient **après** la bascule (`is_muted` déjà inversé), et le **repli `except TypeError: on_toggle_mute()`** de `hotkeys.py` rappelait le callback **sans argument** → **seconde bascule qui annulait la première** → F8 ne changeait jamais l'état. Le seul `mic_state_changed` journalisé venait du repli (`source=ui`) — d'où l'absence totale de `source=hotkey`.
  3. **`mute_mic_completely` envoyait `action="mute_completely"`** alors que `log_action(action, ...)` reçoit déjà `action` en positionnel → `TypeError` (l'exception du 19:36:23) : le mute s'appliquait (états posés avant le log) mais le tour de boucle STT était tué et `command_executed` jamais journalisé.
- **Corrections** :
  - `main.py::toggle_mute` / `toggle_sleep` : `details.pop("source", source_or_checked)` — le `source` venant de `hotkeys.py` est désormais absorbé **et journalisé correctement** (`source=hotkey` au lieu de `ui`) ;
  - `main.py::mute_mic_completely` : kwarg en collision renommé `action=` → `via="voice_command"` ;
  - `hotkeys.py` : **suppression des replis `except TypeError`** (mute/sleep/nav/souris) — ils étaient la cause de la double bascule ; tous les callbacks acceptent `**details`, et `_on_key_press` journalise déjà toute exception (`hotkey_error`) sans tuer le listener.
- **Tests : +3 → `tests/test_hotkeys.py` = 7 tests** : (1) un callback qui plante en `TypeError` n'est appelé **qu'une fois** (régression directe), (2) `toggle_mute`/`toggle_sleep` avec `source="hotkey"` basculent **une seule fois** et journalisent `source=hotkey`, (3) `mute_mic_completely` ne lève plus d'exception et journalise `via=voice_command`.
- **Validation** : `test_hotkeys.py` + `test_command_matching.py` = **25 passed** ; suite complète = **163 passed, 1 failed** — l'échec `test_phase1.py::test_user_voice_calibration_samples_if_present` **reproduit sur l'arbre propre (stash)** = régression **préexistante** (échantillons `cmd_oups`), sans rapport avec ce fix.
- **Suite immédiate** : commit + push, validation terrain (mute vocal « Couper Phénix » → F8 doit rallumer), puis reprendre les **2 fixes DTW validés** (garde-fou « commande valide » + seuil 0,11).

### 17. Fix F8 validé au terrain + garde-fou DTW « Virgule » → « Au repos » (19/11)
- **Fix F8 validé par l'utilisateur en conditions réelles** (« j'ai fait le test manuellement, ça fonctionne ») → commit `16bf23c` close la boucle du §16.
- **Reste : « , » rend toujours « Au repos »** → les 2 fixes DTW validés ont été implémentés (commit `a41117f`) :
  1. **Garde-fou « commande valide »** : `is_phenix_command(text)` dans `postprocess/punctuation.py` (union de tous les index `*_KEYS` + `command_keys()`), appelé par le court-circuit `acoustic_fp_match` de `plausibility.arbitrate` — un template qui n'est pas une commande Phénix reconnue est **ignoré** (le texte du STT est préservé). Vérifié : « Au repos » → KO, « Écoute » → KO, toutes les vraies commandes (`Couper Phénix`, `Phénix repos`, `Choisir un`…) → OK.
  2. **Seuil DTW 0,16 → 0,11** (`audio/fingerprints.py`) : vrais matches OTAN ≈ 0,107 acceptés, faux positifs (≥ 0,136) rejetés.
- **Vérification directe** : `arbitrate(raw='Virgule', fp=('Au repos', 0.14))` → best_text `'Virgule'`, `was_adapted=False` ; `fp=('Couper Phénix', 0.1)` → reste prioritaire.
- **Tests** : +1 `test_arbitrator_rejects_dtw_template_that_is_not_a_phenix_command` → ciblé 9 passed ; suite complète **163 passed + 1 nouveau = 164**, 1 échec préexistant `test_phase1` (cmd_oups, hors sujet, déjà constaté sur arbre propre).
- **Note** : la suppression du wav `cmd_au_repos` au studio n'est **plus nécessaire** (le garde-fou le rend inerte), mais reste possible pour alléger le manifeste.
- **Suite immédiate** : **discussion de l'ouverture au développement communautaire** (messages forums, revue de code, lignes mortes/optimisations) — consigne utilisateur : en parler AVANT tout travail de préparation.

### 18. Ouverture au développement communautaire — préparatifs (19/11)
- **Démarche discutée avec l'utilisateur (outil `question`) puis validée** :
  1. **Mode** : appel à contributeurs (dépôt ouvert + issues « bonne première contribution » + messages forums pour recruter 2-3 co-développeurs ; l'auteur garde la main sur le merge).
  2. **Canaux** : forums francophones + Tech for Good (FR), Reddit/HN en option (EN).
  3. **Ordre** : audience d'abord (LICENSE/CONTRIBUTING/README → audit code → issues → messages).
  4. **Licence** : **GNU GPLv3** (`LICENSE` officiel téléchargé, `pyproject.toml` MIT → `GPL-3.0-only`).
  5. **Transparence exigée par l'utilisateur dans TOUS les messages** : développement **100 % IA, sans revue de code de sa part** (il ne maîtrise pas Python, résultats satisfaisants quand même), projet estimé à **moins de 25 % terminé**, appel explicite à des collaborateurs pour **auditer/architecturer**.
- **Fait (commits `f20d21f` puis `38bb6df`, dépôt passé PUBLIC via `gh repo edit`)** :
  - `LICENSE` (GPL-3.0) + `CONTRIBUTING.md` (mise en place `.venv`, ~160 tests, conventions : commits ASCII, code en français, zéro réseau, note Lexique 383 = CC BY-SA 4.0) ;
  - README : statut, avertissement transparence IA, phases 1-5 marquées terminées (roadmap avant périmée), sections Licence/Contribuer ;
  - `docs/APPEL_CONTRIBUTEURS.md` : 4 messages prêts (Tech for Good FR, Reddit r/opensource EN, forum FR technique, message court) + checklist de publication.
- **Audit de confidentialité** : aucun `user_data/`, `logs/`, `.wav` ni manifeste d'étalonnage dans l'historique git ✅ ; **prénom anonymisé** (« laure » → « camille » fictif) dans `main.py`, `symbols.py`, `test_symbols.py`, les outils `build_mfa_corpus.py`/`textgrid_to_manifest.py` et le JOURNAL (chemin `C:\Users\...`). Tests vérifiés après remplacement (**35 passed** sur `test_symbols` + `test_command_matching`).
- **Extension OpenCode Browse** : la notification d'installation suggérée par OpenCode a été identifiée (extension Chrome officielle permettant à l'agent d'utiliser le vrai navigateur avec les sessions de l'utilisateur) — utile pour publier les messages forums automatiquement ; à installer depuis le Chrome Web Store si l'utilisateur le souhaite.
- **En cours** : sous-agent d'**audit du code** (code mort, doublons, optimisations, dette technique) → produira les premières issues GitHub (`bonne-premiere-contribution`, `optimisation`, `dette-technique`).
- **Reste** : créer les issues à partir de l'audit → publier les messages (l'utilisateur, ou via Browse si installé).
