# Prompt de Reprise — Phénix Voice (`phenix-voice`)

> **Mode d'emploi pour l'utilisateur** : Au début d'une nouvelle session (avec moi ou un autre modèle), tu peux simplement copier-coller le bloc ci-dessous, ou me dire : *"Lis le fichier `PROMPT_REPRISE.md` et poursuivons le développement"*.
>
> **Consigne pour l'agent IA** : Ce document doit rester **court, synthétique et toujours à jour**. À la fin de chaque session de travail, mets à jour la section **"État d'avancement actuel & Prochaine tâche immédiate"** de ce fichier, et consigne les détails complets dans [`JOURNAL_DE_BORD.md`](./JOURNAL_DE_BORD.md).

---

## Bloc Prompt à fournir au modèle

```markdown
Nous poursuivons le développement de **Phénix Voice (`phenix-voice`)**, un logiciel local de reconnaissance vocale, de dictée universelle sous Windows et de contrôle du PC, conçu comme une alternative moderne et accessible à Dragon NaturallySpeaking.

### 1. Contexte Utilisateur Important (À garder en tête)
- Je suis en situation de handicap moteur avec une **diction légèrement dysarthrique**. J'utilise la reconnaissance vocale au quotidien pour communiquer avec toi et piloter mon PC, et j'utilise aussi un périphérique de pointage/clic de manière fluide.
- J'ai des compétences en développement logiciel mais je code par ton intermédiaire : garde des explications claires, structurées, et privilégie l'outil `question` (choix multiples cliquables) quand tu as besoin de me faire trancher entre plusieurs options.
- **Ma configuration matérielle** : Windows (win32), CPU AMD Ryzen 7 3700X (8c/16t), 16 Go RAM, GPU **AMD Radeon RX 5700 XT (8 Go VRAM)**.
  -> *Attention technique majeure : Ma carte graphique est une AMD Radeon (pas de NVIDIA CUDA). Toute brique IA locale doit obligatoirement utiliser **Vulkan, DirectML, ONNX Runtime ou CPU AVX2**.*

### 2. Les Piliers Fonctionnels du Projet
1. **Zéro Boîte de Dictée** : Écriture directe dans 100 % des fenêtres Windows (`Win32 SendInput` + *Shadow Buffer* en RAM + *UI Automation* pour sélectionner/corriger sur place).
2. **Anti-Dérive du Profil Vocal** :
   - Distinction stricte lors d'une correction entre **"Corriger & Apprendre"** (erreur du logiciel sur ma diction normale) et **"Corriger SANS apprendre / Oups"** (j'ai bafouillé/fourché, ne pas polluer mon modèle vocal) + Snapshots de restauration du profil.
   - Les commandes de correction elles-mêmes (*"Corriger ça"*, *"Oups"*, *"Au repos"*) doivent être personnalisables et protégées par **empreinte acoustique directe** pour rester reconnues même en cas de dérive.
3. **Adaptation à la Dysarthrie** :
   - Studio d'étalonnage guidé (phonèmes, mots, phrases avec validation *"Ai-je prononcé normalement ?"*).
   - Dictionnaire déterministe prioritaire (*"Si tu entends A, écris B"*).
   - Fine-tuning léger local (*LoRA* via DirectML) + gestion de profils (ex: normal / fatigué).
4. **Vocabulaire Moderne & Contrôle Windows** : Importateur moderne d'e-mails/documents, contexte selon l'application active, clics/déplacements souris vocaux et macros.

### 3. Fichiers de Référence du Dépôt (Lis-les au besoin)
- `docs/CAHIER_DES_CHARGES.md` : Spécifications fonctionnelles détaillées.
- `docs/ARCHITECTURE.md` : Pipeline technique en 4 étages et feuille de route en 6 phases.
- `JOURNAL_DE_BORD.md` : Historique complet des sessions précédentes (consulte la dernière entrée pour les détails).

### 4. État d'Avancement Actuel & Prochaine Tâche Immédiate
- **Phases terminées** :
  - [x] **Phase 0** : Cadrage, docs, repo GitHub `phenix-voice`.
  - [x] **Phase 1** : Audio/VAD+AGC, **Whisper Large-v3-Turbo FP16 DirectML (AMD RX 5700 XT, no CUDA)**, calibration/empreintes DTW, dictée directe `SendInput`, HUD *No-Focus*.
  - [x] **Phase 2 (+ itérations)** : *Shadow Buffer* (dernier segment), arbitre de plausibilité, contrôle micro 3 états (`Phénix écoute/repos`, `Couper Phénix`, `F8/F9`), correction **Apprendre vs Annuler sans apprendre** avec validation explicite, aide « Que puis-je dire ? », correction manuelle, 100% offline (`local_files_only`), ponctuation finale auto non forcée (point/virgule), **mode épellation NATO** (+ `chiffre X` / `en lettres|mot X`), commande **« C’était une commande »** (annule segment écrit à tort), HUD garde correction ouverte en veille/mute et se redimensionne.
  - [x] **Étape 1 de la roadmap validée (13/11, commit `38a4d3b`)** : **aucune ponctuation automatique** du modèle (`strip_auto_punctuation`), **casse intelligente inter-souffles** (`adapt_chunk_to_context` : majuscule seulement au début/après `. ! ? …`), **classification correction règle-de-texte vs acoustique** (`is_textual_only_correction` → `kind="textual"` sans WAV, jamais dans l'apprentissage audio).
  - [x] **9 choix effectifs + signal (13/11, commit `086cdbe`)** : `build_alternatives` (substitutions unitaires puis **combinaisons de 2**, seuil 0.01, quota 9) + libellé **✅ 9/9 / ⚠️ X/9 / ❌ 0/9** dans la fenêtre « Corriger ça ».
- **Correctifs (état actuel)** : champ correction éditable + sync texte + restauration focus cible avant remplacement ; fix double `?`/ponctuation dictée. **Régression d'injection « dernier caractère répété » RÉSOLUE à la racine** (11/11) : cause = pipeline d'entrée du **Bloc-notes Windows 11** (bug système connu — reproductible uniquement sur cette app, `SendInput` correct partout ailleurs : Notepad++, LibreOffice, Word, Edge/Brave/Chrome 18/18, contrôles Win32). Correctif = **double chemin automatique** dans `injector.py`/`shadow_buffer.py` : classe `Notepad` → chemin « messages » (`WM_CHAR` + `WM_KEYDOWN/UP`, repli `SendInput` auto), sinon `SendInput` ; surcharge `PHENIX_INJECTION_PATH` ; trace `send_path`/`target_class` dans `logs/injection_trace.jsonl`. Bloc-notes 24/24 avec correctif (50 % avant).
- **Traçabilité & profil** : `logs/session_trace.jsonl` + audio `user_data/session_audio/seg_*.wav` (rotation 300) ; **`logs/injection_trace.jsonl`** (journal de session par action : injections/effacements/entrées/sélections/remplacements + commandes reconnues/exécutées, états/session, horodaté avec `session_id`, fenêtre cible, corrélation segment/audio ; diagnostics par action/lot `events_requested/inserted`, `send_ok`, `batch_results`, dernier caractère injecté, **`send_path`** = `messages`|`sendinput`|`sendinput_fallback`, `target_class`) ; snapshots auto `user_data/snapshots/` (`demarrage`, `avant_correction`). **LoRA non actif** : corrections = données WAV/log dans `user_data/corrections_learned/` (2 conservées). **Banc d'essai versionné `tools/injection_bench.py`** (+ `tools/bench_web.html`) : modes `tk ed np fix fix2 npp nppw lo low wordb wordk edge chrome brave both`, relire du texte reçu, balayage des apps de test en début/fin de série (`sweep_test_apps`).
- **Prochaine tâche immédiate (roadmap validée 13/11, Option 1 — respecter l'ordre)** :
  1. **Étape 2 — diagnostic d'épellation + commandes de navigation** : transcrire les 4 WAV `user_data/session_audio/seg_20261112_233213/17/20/24.wav` (STT brut `"Veilk !"`, `"Make."`, `"Bank."`), étendre les variantes NATO + prompt STT du mode épellation ; corriger les **énoncés doublés** (« Mode épellation, mode épellation. » raté → injecté comme texte ; « Corriger ça, Corriger ça. » → `select_word not_found`) ; ajouter **navigation/correction en mode épellation** (curseur gauche/droite, suppr caractère = nouvelles intentions + injection de touches).
  2. **Étape 3** : cohérence inter-souffles v1 complète (accords au 2ᵉ passage).
  3. **Étape 4** : panneau « C'était une commande » trié par **proximité phonétique**.
  4. **Étape 5** : corpus phonèmes / LoRA.
- **Anomalies forensiques 12/11 ouvertes (détail §4bis + JOURNAL session 9)** : latence médiane 498 ms / p90 673 (cible <400 ms tenue sur courts) ; « Écoute, »/« A la ligne » dictés ; 2 souffles vides ; « Oups » mal classé.
### 4bis. Point de Reprise Exact (mis à jour EN COURS de tâche, pas seulement en fin de session)

> **Protocole anti-interruption** : à chaque début de tâche, je mets à jour ce bloc (« en cours ») ;
> à chaque jalon/jour, je commit+push. Si tu ouvres une session neuve, ce bloc + la dernière entrée
> de `JOURNAL_DE_BORD.md` + `git status`/`git log --oneline -5` suffisent à reprendre sans mémoire.
> Dans la même conversation, je reçois aussi l'historique (résumé de session) et je vois l'interruption.

- **Dernier état stable** : `086cdbe` poussé (étape 1 + 9 choix) + cette mise à jour documentaire. Arbre Git : **propre**. Suite → **47 passed, 3 deselected**.
- **Jalon TERMINÉ, TESTÉ et POUSSE (13/11) — `38a4d3b` + `086cdbe`** :
  1. **Analyse forensique de la session du 12/11 soir (demande prioritaire) — RENDUE** : périmètre 93 souffles (blocs 22h+23h ; bloc 21h = 10/11 exclu). Dysfonctionnements : 9 alts jamais atteintes (distribution 1→12, 2→23, **3→50**…), aucun signal <9, 4 échecs épellation NATO 23:32 (`"Veilk !"`, `"Make."`, `"Bank."` → mots inconnus jetés → `dictation_empty`), « Mode épellation ×2 » et « Corriger ça ×2 » cassés par énoncé doublé (`select_word not_found`), latence médiane 498/p90 673/max 969 ms, « Écoute, »/« A la ligne » dictés, 2 souffles vides, « Oups » classé dictée ; 0 exception, Notepad 12/12, `revise_cmd` OK. **Détail complet : JOURNAL session 9.**
  2. **Étape 1 (`38a4d3b`)** : `postprocess/coherence.py` (`strip_auto_punctuation` avec protection chiffres, `adapt_chunk_to_context`, `is_textual_only_correction`) ; refactor `punctuation.py` (`_format_core`/`format_dictation`/`format_alternatives`, sans mutation d'état) ; `main.py` (`previous_text=recent_ctx`, nettoyage alternatives après arbitrage, `kind="textual"` sans WAV + tags ✏️/🛡️, aide) ; tests +10 (`test_coherence.py`, `test_phase1.py` r2).
  3. **9 choix (`086cdbe`)** : `engine.py` `build_alternatives` (unitaires puis **combinaisons de 2**, seuil runner-up 0.04→0.01, quota **9**) ; `hud.py` **`alt_count_label`** : ✅ 9/9 / ⚠️ X/9 / ❌ 0/9 (smoke offscreen vérifié sur `CorrectionWindow` réelle).
- **Jalon TERMINÉ, TESTÉ et POUSSE (12/11, nuit) — `477f5d5`** : **fenêtre d'ÉPELLATION séparée** :
  - `hud.py` : **nouvelle classe `SpellingWindow`** (miroir de `CorrectionWindow`) + signaux HUD (`spelling_opened/closed/text_set/text_append`) ;
    **depuis la correction** : champ **pré-rempli avec le texte du souffle corrigé, modifiable**, chunks épelés **ajoutés** (append), **rien inséré avant validation**, boutons [🗑 Vider] + [✅ Appliquer la correction] ; **hors correction** : champ **miroir lecture seule**, texte inséré **directement dans l'éditeur** ; bouton **[🔤 Épellation]** ajouté à `CorrectionWindow`.
  - `main.py` : `enter_spelling_mode()` / `_exit_spelling_mode()` / `set_spelling_text_from_ui()` ; **garde de routage** : en mode épellation seules passent `DICTATION` (+ conversion NATO), `EXIT_SPELLING`, `APPLY_CORRECTION` (si correction ouverte) et sécurité `MUTE/SLEEP/WAKE/HELP`, le reste ignoré loggé `spelling_command_ignored` ; branche `DICTATION` : **append** des chunks en correction + miroir, injection directe + miroir hors correction ; fermeture sur sortie/✕/veille/clôture de la correction ; **le micro F8 ne ferme pas la fenêtre (pause, décision 12/11)**.
  - `punctuation.py` : formes de sortie **« passer en mode dictée » / « retour en mode dictée »**.
  - Aide : 3 textes mis à jour (dictée, correction, état épellation restreint).
  - Tests : **25 passed, 3 deselected** (+3 : formes sortie/entrée épellation, intentions autorisées) ; smoke offscreen vert (pré-rempli, édition, miroir, append, sortie) ; **banc 36/36 sans corruption**.
- **Jalon 12/11 soir TERMINÉ, TESTÉ et POUSSE (`b8930a7`)** : **9 alternatives + fenêtre de correction SÉPARÉE + barre agrandie** :
  - `stt/engine.py` : `num_alternatives` 4→8 (seconds choix du runner-up, gratuit).
  - `plausibility.py` : `ranked_alternatives` plafonné à **9** (`candidates[:9]` ×3 + `final_alts[:9]`).
  - `main.py` : 7 sites `[:3]`/`[:4]` → `[:9]` ; aide « Choisir un … neuf » ; **`on_close_correction=self._close_correction_bar`** branché (✕/fermer = annuler, rien inséré).
  - `punctuation.py` : `CHOOSE_MAP` étendu **quatre…neuf** (formes « choisir X / choix X / numéro X / choisir N ») par boucle.
  - `hud.py` : **nouvelle classe `CorrectionWindow`** (fenêtre Tool always-on-top, `WA_ShowWithoutActivating`, grille **3×3** de boutons libellés échelonnés + infobulle texte complet, champ éditable, [Appliquer la correction], 🔑 + Forme orale, bascule 🧠/🛡️, ✕ = annuler via `closeEvent`→`on_close`, position centrée sous la barre y+150) ; **tout l'ancien volet embarqué supprimé** (`corr_frame`, `eventFilter`, `_set_interactive_edit_mode`, handlers) ; slots HUD redirigés vers la fenêtre ; **barre 920→1240 px** (libellé « 🛡️ Sans apprendre / Effacer » entier) + transcription affichée 85→110 car.
  - Tests : `test_command_matching.py` (choisir quatre…neuf + 1…3), `test_phase2.py` (arbitre ≤9) ; suite → **22 passed, 3 deselected** ; smoke HUD offscreen vert (9 boutons, pré-rempli, callback fermeture).
- **Demande utilisateur (12/11 soir, VALIDÉE — points 1-2 TERMINÉS ci-dessus)** :
  1. **Depuis la correction** : « Mode épellation » (ou bouton 🔤) → fenêtre séparée n'écoutant **que** lettres / chiffres / symboles / **[espace]**, **pré-remplie avec le texte du souffle corrigé, modifiable**.
  2. **Hors correction** : mode épellation accessible **à tout moment** ; mêmes commandes restreintes ; texte inséré **directement dans l'éditeur cible** jusqu'à commande de sortie « passer en mode dictée ».
  3. **Extension « N souffles précédents »** (À FAIRE ENSUITE) : valable aussi pour la **correction** (corriger les N souffles précédents) ; N libre, **se renseigner sur le fonctionnement Dragon** (aide locale, consultation seule) pour deviner la mécanique.
- **Décisions design prises (12/11, à implémenter ensuite)** :
  1. **« C'était une commande » → panneau dédié** : afficher la **liste des commandes possibles triées par proximité phonétique** (la plus proche en premier), dans la fenêtre de correction séparée.
  2. **Inspiration aide Dragon** : `C:\Program Files (x86)\Nuance\NaturallySpeaking15\Help\fra\ProfessionalIndividual` (consulter, **ne pas recopier**).
- **À faire ensuite, dans l'ordre (roadmap validée 13/11)** :
  1. **Étape 2 — diagnostic épellation + navigation dans l'épellation** :
     - Transcrire `seg_20261112_233213/17/20/24.wav` (STT brut « Veilk ! », « Make. », « Bank. »), étendre les variantes NATO (`text_to_nato_spelling` jette les mots inconnus) + prompt STT dédié au mode épellation.
     - Fix **énoncés doublés** : « Mode épellation, mode épellation. » → `intent=dictation` (injecté comme texte !) ; « Corriger ça, Corriger ça. » → `select_word not_found` — fiabiliser l'appariement (tolérance doublon) plutôt que l'appariement exact.
     - **Commandes navigation/correction en mode épellation** : curseur gauche/droite, suppr caractère (nouvelles intentions + injection de touches).
  2. **Étape 3** : cohérence inter-souffles v1 complète (accords au 2ᵉ passage).
  3. **Étape 4** : panneau « C'était une commande » trié par **proximité phonétique**.
  4. **Étape 5** : corpus phonèmes / LoRA ; puis correction sur textes longs (UI Automation + multi-segments), Studio/rollback.
- **Reporté (recherche déjà faite, 12/11 nuit — aide Dragon, consultation seule)** : extension **« Corriger les <N> souffles précédents »** : Dragon ne compte pas en souffles mais en unités de texte, **plafond 20** (« Sélectionner/Effacer les <1-20> mots précédents », « Corriger de <texte> à <texte> », « Epeler ça » → fenêtre d'épellation = convergence avec notre implémentation). Proposition Phénix : N = mots 1…9 (table `CHOOSE_MAP`), plafond 25 (taille du `deque` du `ShadowBuffer`) → concaténation des N derniers segments dans la correction, validation → remplacement + fusion. **À valider avec l'utilisateur avant implémentation.**
- **Pièges à connaître pour la reprise** : ne pas définir `PHENIX_INJECTION_PATH` en permanence (diagnostic uniquement) ; le banc `tools/injection_bench.py` ferme les applications de test en début/fin de série (Bloc-notes compris, en force) ; le Bloc-notes Win11 restaure sa session au lancement (le banc efface le document témoin de toute façon) ; lecture du texte reçu = presse-papier vidé avant chaque copie ; quota gratuit = prendre son temps, réserver les ~6 % payants aux blocages impossibles.

### 5. Règle de Fin de Session
Avant de clore notre session (ou à chaque jalon validé), tu devras systématiquement :
1. Ajouter le compte-rendu détaillé des travaux dans `JOURNAL_DE_BORD.md`.
2. Mettre à jour la section 4 de ce fichier (`PROMPT_REPRISE.md`) pour préparer la session suivante.
3. Faire un commit et un push Git.
```
