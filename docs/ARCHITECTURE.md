# Architecture Technique & Feuille de Route — Phénix Voice

## 1. Contraintes Matérielles & Principes d'Ingénierie

### 1.1 Machine de référence et cible matérielle
- **Machine de développement** :
  - **CPU** : AMD Ryzen 7 3700X (8 cœurs / 16 threads)
  - **RAM** : 16 Go
  - **GPU** : **AMD Radeon RX 5700 XT (8 Go VRAM)** sous Windows (win32)
- **Cible de diffusion** : Tout PC Windows moderne de gamme moyenne (GPU AMD, Intel ou NVIDIA, ou CPU multi-cœurs).
- **Règle d'or matérielle** : **Aucune dépendance exclusive à NVIDIA CUDA**. Toute la chaîne d'inférence et d'entraînement local doit fonctionner via **Vulkan**, **DirectML (ONNX Runtime / PyTorch-DirectML)** ou CPU optimisé (AVX2).

### 1.2 Objectifs de performance
- **Latence de transcription** : `< 400 ms` après la fin d'un souffle (micro-pause).
- **Consommation VRAM au repos/écoute** : `< 3,5 Go` de VRAM pour laisser le PC parfaitement fluide pour toutes les autres applications.

---

## 2. Pipeline de Traitement en 4 Étages

```
[ Entrée Microphone (16 kHz Mono PCM) ]
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ ÉTAGE 1 : Capture, VAD & Court-Circuit d'Empreintes Acoustiques │
│ • Silero VAD (ONNX) : détecte la parole et les micro-pauses     │
│ • Empreintes Acoustiques (DTW / Audio Embeddings) : intercepte  │
│   en priorité les commandes vitales ("Corriger ça", "Oups",     │
│   "Au repos") même si la prononciation dérive.                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Segment audio validé
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ ÉTAGE 2 : Moteur Acoustique Adaptatif Local                     │
│ • Moteur d'inférence : whisper.cpp (Vulkan) / ONNX DirectML     │
│ • Modèle : Whisper Large-v3-Turbo (ou Medium) quantifié         │
│   + Poids d'adaptation personnels (LoRA fusionné)               │
│ • Sortie : Texte principal + Top-5 des hypothèses alternatives  │
│   + Scores de confiance par mot                                 │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Hypothèses brutes
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ ÉTAGE 3 : Post-Processeur, Règles "A -> B" & Contexte           │
│ • Dictionnaire déterministe ("Si tu entends A, écris B")        │
│ • Biaising du vocabulaire personnel et de l'application active  │
│ • Interprétation hybride de la ponctuation et mise en forme     │
│ • Routeur d'intention : Commande système / Macro vs Texte dicté │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Action ou Texte finalisé
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ ÉTAGE 4 : Exécuteur Windows & Shadow Buffer ("Zéro Boîte")      │
│ • Injection clavier directe (Win32 SendInput Unicode)           │
│ • Synchronisation Windows UI Automation (suivi du curseur)      │
│ • Enregistrement dans le Shadow Buffer circulaire en RAM :      │
│   [Mots injectés, Position, Audio WAV source, Alternatives]     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Détail des Briques Technologiques

### 3.1 Langage et Environnement
- **Python 3.11 / 3.12 (64-bit)** sous Windows.
- Gestionnaire d'environnement rapide : `uv` ou `venv` standard.

### 3.2 Briques Audio & IA
1. **Capture & Découpage (VAD)** :
   - `sounddevice` (PortAudio faible latence WASAPI) + `silero-vad` via `onnxruntime`.
2. **Reconnaissance d'empreintes de commandes vitales** :
   - Extraction de vecteurs acoustiques (MFCC / Mel-spectrogrammes + *Dynamic Time Warping* rapide ou petit encodeur audio ONNX) comparés aux enregistrements de référence de l'utilisateur pour les commandes système critiques.
3. **Transcription Speech-to-Text (STT)** :
   - **Option principale d'inférence rapide sur GPU AMD** : `whisper.cpp` compilé avec support **Vulkan** (via bindings Python ou serveur local léger en mémoire partagée / HTTP local ultra-rapide) ou `onnxruntime-directml`.
   - Permet d'utiliser *Whisper Large-v3-Turbo* en `q5_0` / `fp16` avec moins de 2,5 Go de VRAM sur la Radeon RX 5700 XT et une vitesse 10x à 20x supérieure au temps réel.
4. **Adaptation à la dysarthrie & Fine-Tuning Local** :
   - **Couche 1 (Instantanée, sans ré-entraînement lourd)** :
     - Dictionnaire d'équivalences phonétiques/textuelles ($A \rightarrow B$).
     - *Initial Prompt* dynamique injecté dans Whisper contenant les mots propres à l'utilisateur et les termes de l'application active.
     - Banque d'empreintes acoustiques de mots/commandes spécifiques.
   - **Couche 2 (Consolidation périodique du modèle acoustique)** :
     - Utilisation de `torch-directml` + `transformers` + `peft` (LoRA) pour affiner l'encodeur/décodeur Whisper sur les enregistrements validés par l'utilisateur (Studio d'étalonnage + Corrections de type "Corriger & Apprendre"), puis conversion du modèle adapté vers le format d'inférence rapide (GGUF / ONNX).

### 3.3 Intégration Windows, UI & Stockage
- **Injection Texte & Contrôle Windows** :
  - `ctypes.windll.user32.SendInput` (injection Unicode rapide et fiable partout).
  - `uiautomation` (lecture optionnelle du champ texte cible, détection de la fenêtre active et des boutons).
  - `pynput` / hooks bas niveau pour détecter les clics souris ou déplacements manuels du curseur qui réinitialisent ou déplacent le *Shadow Buffer*.
- **Interface Utilisateur (UI)** :
  - **PySide6 (Qt6)** :
    - *HUD / Barre flottante* : Fenêtre `Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus` (permet de cliquer sur les boutons de correction à la souris **sans jamais retirer le focus clavier de l'application où l'on dicte**).
    - *Phénix Studio* : Fenêtre principale pour l'étalonnage vocal, le dictionnaire $A \rightarrow B$, le vocabulaire, l'import de mails, les macros et la gestion des *Snapshots* du profil.
- **Stockage Local** :
  - Base **SQLite** locale (`user_data/profile.db`) + stockage structuré des extraits audio validés (`user_data/samples/*.wav`) et des snapshots de profil (`user_data/snapshots/`).

---

## 4. Structure Cible du Dépôt

```
phenix-voice/
├── README.md
├── PROMPT_REPRISE.md          # Prompt concis pour démarrer une nouvelle session IA
├── JOURNAL_DE_BORD.md         # Historique détaillé des sessions et décisions
├── AGENTS.md                  # Instructions automatiques pour OpenCode
├── pyproject.toml             # Dépendances et configuration du projet Python
├── docs/
│   ├── CAHIER_DES_CHARGES.md
│   └── ARCHITECTURE.md
├── src/
│   └── phenix_voice/
│       ├── __init__.py
│       ├── main.py            # Point d'entrée de l'application
│       ├── audio/             # Capture micro, Silero VAD, empreintes acoustiques
│       ├── stt/               # Moteur Whisper (Vulkan/ONNX) & gestionnaire LoRA
│       ├── postprocess/       # Règles A->B, ponctuation hybride, routeur commandes
│       ├── os_control/        # SendInput, Shadow Buffer, UIAutomation, Souris/Macros
│       ├── storage/           # Base SQLite, profils, snapshots, importateur mails/docs
│       └── ui/                # Barre flottante No-Focus & Phénix Studio (PySide6)
└── tests/                     # Tests unitaires et scripts de benchmark matériel
```

---

## 5. Planification de l'Exécution (6 Phases)

### Phase 1 : Socle Audio, Accélération GPU AMD & Dictée Universelle (POC)
1. Initialisation de l'environnement Python et validation du benchmark GPU sur l'AMD Radeon RX 5700 XT (Vulkan / DirectML).
2. Implémentation de la capture audio temps réel + découpage par souffle (*Silero VAD*).
3. Intégration du moteur de transcription local + ponctuation hybride de base.
4. Injection directe universelle du texte (`SendInput`) dans n'importe quelle fenêtre + contrôle du micro (raccourci physique + commandes vocales *Écoute / Au repos*).
5. Mini-indicateur visuel d'état du micro (Actif / Veille / Transcription en cours).

### Phase 2 : Shadow Buffer & Interface de Correction Anti-Dérive
1. Création du *Shadow Buffer* suivant les mots injectés et conservant les segments audio des dernières phrases.
2. Commandes vocales *« Sélectionner [mot] »*, *« Corriger ça »*, *« Corriger [mot] »* fonctionnant directement dans la fenêtre cible sans boîte de dictée.
3. Barre flottante *No-Focus* affichant les alternatives cliquables ou sélectionnables à la voix (*« Choisir 1, 2... »*).
4. Séparation **« Corriger & Apprendre »** vs **« Corriger SANS apprendre (Oups / J'ai fourché) »**.
5. Personnalisation des commandes de correction et protection par **empreinte acoustique directe**.

### Phase 3 : Adaptation Immédiate (Règles « A -> B » & Vocabulaire Moderne)
1. Moteur de règles déterministes prioritaires (*« Si tu entends A, écris B »*) avec interface d'ajout rapide depuis la barre de correction.
2. Gestionnaire de vocabulaire personnel avec enregistrement audio des mots spécifiques.
3. Outil d'importation moderne de documents locaux et d'e-mails envoyés (`.mbox`, `.eml`, collage, IMAP) pour extraire le lexique de l'utilisateur.
4. Détection de la fenêtre active pour adapter le contexte lexical.

### Phase 4 : Studio d'Étalonnage Dysarthrie & Fine-Tuning Local
1. Interface d'étalonnage guidé (listes de phonèmes, paires minimales, mots et phrases) avec validation *« Prononciation habituelle : Oui / Non »*.
2. Pipeline de consolidation locale (*Fine-Tuning LoRA* via DirectML) sur les échantillons validés.
3. Gestionnaire de **Snapshots (Points de restauration)** du profil vocal et gestion des profils de fatigue.

### Phase 5 : Contrôle de Windows, Souris & Macros
1. Commandes de clics souris, molette et gestion des fenêtres Windows.
2. Éditeur de macros vocales (insertion de texte, raccourcis clavier, séquences d'actions).
3. Grille souris vocale (*MouseGrid*) et numérotation des contrôles d'interface (*UI Automation*).

### Phase 6 : Ouverture Multi-Utilisateurs & Packaging
1. Assistant de premier lancement (*Onboarding*) et détection automatique des capacités matérielles du PC.
2. Packaging en exécutable / installeur Windows autonome.
