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
- **Correctifs (état actuel)** : champ correction éditable + sync texte + restauration focus cible avant remplacement ; fix double `?`/ponctuation dictée. **Régression d'injection « dernier caractère répété » RÉSOLUE à la racine** (11/11) : cause = pipeline d'entrée du **Bloc-notes Windows 11** (bug système connu — reproductible uniquement sur cette app, `SendInput` correct partout ailleurs : Notepad++, LibreOffice, Word, Edge/Brave/Chrome 18/18, contrôles Win32). Correctif = **double chemin automatique** dans `injector.py`/`shadow_buffer.py` : classe `Notepad` → chemin « messages » (`WM_CHAR` + `WM_KEYDOWN/UP`, repli `SendInput` auto), sinon `SendInput` ; surcharge `PHENIX_INJECTION_PATH` ; trace `send_path`/`target_class` dans `logs/injection_trace.jsonl`. Bloc-notes 24/24 avec correctif (50 % avant).
- **Traçabilité & profil** : `logs/session_trace.jsonl` + audio `user_data/session_audio/seg_*.wav` (rotation 300) ; **`logs/injection_trace.jsonl`** (journal de session par action : injections/effacements/entrées/sélections/remplacements + commandes reconnues/exécutées, états/session, horodaté avec `session_id`, fenêtre cible, corrélation segment/audio ; diagnostics par action/lot `events_requested/inserted`, `send_ok`, `batch_results`, dernier caractère injecté, **`send_path`** = `messages`|`sendinput`|`sendinput_fallback`, `target_class`) ; snapshots auto `user_data/snapshots/` (`demarrage`, `avant_correction`). **LoRA non actif** : corrections = données WAV/log dans `user_data/corrections_learned/` (2 conservées). **Banc d'essai versionné `tools/injection_bench.py`** (+ `tools/bench_web.html`) : modes `tk ed np fix fix2 npp nppw lo low wordb wordk edge chrome brave both`, relire du texte reçu, balayage des apps de test en début/fin de série (`sweep_test_apps`).
- **Prochaine tâche immédiate** :
  1. **Test utilisateur en direct du correctif** : dictée longue + corrections (« Corriger ça », choix 1/2/3, « C'était une commande ») dans le Bloc-notes et d'autres applications ; vérifier `send_path` dans `logs/injection_trace.jsonl`. Puis fiabiliser effacements successifs/ponctuation en conditions réelles.
  2. **Poursuivre le diagnostic ouvert** : segments non injectés (`dictation_empty` : `seg_20261111_145733`, `_145914`, `_150052`) et `select_word not_found` (« ça corrigez ça »).
  3. **Correction sur textes longs** : historique multi-segments + UI Automation (TextPattern/ValuePattern), occurrences, réécoute audio en correction, plus d’alternatives (jusqu’à 9).
  4. **Studio / rollback explicite** : UI/commandes snapshots (profil initial, restauration par nom), purge/reset corrections/règles, puis pipeline LoRA local DirectML avec validation avant entraînement.
### 4bis. Point de Reprise Exact (mis à jour EN COURS de tâche, pas seulement en fin de session)

> **Protocole anti-interruption** : à chaque début de tâche, je mets à jour ce bloc (« en cours ») ;
> à chaque jalon/jour, je commit+push. Si tu ouvres une session neuve, ce bloc + la dernière entrée
> de `JOURNAL_DE_BORD.md` + `git status`/`git log --oneline -5` suffisent à reprendre sans mémoire.
> Dans la même conversation, je reçois aussi l'historique (résumé de session) et je vois l'interruption.

- **Dernier état stable** : `9a1c4aa` poussé (correctif « C'était une commande »). Arbre Git : **modifs EN COURS non committées** (jalon ci-dessous, tests verts).
- **Jalon EN COURS terminé et TESTÉ (12/11)** : **formes orales des symboles + règle « rien sans validation »** :
  - Nouveau `src/phenix_voice/postprocess/symbols.py` : tables FR naturel (`CORE_SYMBOL_FORMS` ~25, `AMBIGUOUS_SYMBOL_FORMS` : euro/euros/dollar/dollars/paragraphe/degré(s)/copyright/pourcentage), index tolérants en mémoire (`command_keys`), substitution multi-mots fenêtres glissantes, typographie française contextuelle (`% : ; ! ?` espacés des deux côtés, `€ £ § ® °` espace avant, **`@` collé en contexte e-mail détecté**), `SpokenFormStore` (`user_data/spoken_forms.json`, ajout : bouton « 🔑 + Forme orale » du volet de correction → `add_spoken_form_from_correction()`), `spelling_symbol()` pour le mode épellation (« point » → `.`, « arobase » → `@`… → e-mail en épellation).
  - `punctuation.py` : champs `symbol_form/symbol_char/symbol_choices` dans `ProcessedUtterance`, appel en fin d'étape 5 (après `SPOKEN_PUNCTUATION_RULES`), `_post_process()` commun texte/variante ; `text_to_nato_spelling()` gère les symboles.
  - `main.py` : branche DICTATION → popup choix symbole (alternatives complètes `[symbole, mot]`, voix « choix un/deux »), masquage auto de la popup.
  - **Règle validée par l'utilisateur (12/11)** : **« Choisir un/deux/trois » (voix OU clic) n'INSÈRE PLUS RIEN** : l'alternative est proposée **dans le champ** de correction, insertion seulement après « Valider la correction » / [Appliquer] — l'utilisateur a toujours le droit de changer d'avis ou de se tromper. (`apply_correction_choice()` devient proposition + log `correction_choice_proposed`, `applied=False`.)
  - Tests : nouveau `tests/test_symbols.py` (10 tests) ; suite complète → **19 passed, 3 deselected**.
- **Remarques utilisateur à traiter ENSUITE (12/11)** :
  1. **9 alternatives de correction au lieu de 3** (d'où l'idée — déjà validée le 12/11 — de **fenêtres de correction SÉPARÉES** : la barre HUD 920 px est trop étroite pour 9 choix + champ). À faire : `num_alternatives` STT 4→8, `ranked_alternatives[:8]`, stockage `[:9]`, `CHOOSE_MAP` étendu à « Choisir quatre…neuf », fenêtre de correction distincte (alternatives + champ + validation + mode apprendre + « + Forme orale »).
  2. **Bouton « effacer sans apprendre » trop petit pour afficher tout son texte** (libellé coupé) — à clarifier/ériger (argeur de la barre, taille des boutons ou libellé).
- **Décisions design prises (12/11, à implémenter ensuite)** :
  1. **Fenêtres de correction SÉPARÉES** (voir remarque 1 ci-dessus).
  2. **« C'était une commande » → panneau dédié** : afficher la **liste des commandes possibles triées par proximité phonétique** (la plus proche en premier), dans la fenêtre de correction séparée.
  3. **Inspiration aide Dragon** : `C:\Program Files (x86)\Nuance\NaturallySpeaking15\Help\fra\ProfessionalIndividual` (consulter, **ne pas recopier**).
- **À faire ensuite, dans l'ordre** :
  1. Commit+push du jalon « formes orales + proposition-pré-validation » (tests 19 passed).
  2. **9 choix + fenêtre de correction séparée + taille du bouton « sans apprendre »** (remarques utilisateur 12/11).
  3. Panneau « C'était une commande » trié par proximité phonétique.
  4. Test utilisateur en direct ; puis anomalies ouvertes (`dictation_empty` : `seg_20261111_145733`, `_145914`, `_150052` ; `select_word not_found`).
  5. Correction sur textes longs (UI Automation + multi-segments) → Studio/rollback → LoRA.
- **Pièges à connaître pour la reprise** : ne pas définir `PHENIX_INJECTION_PATH` en permanence (diagnostic uniquement) ; le banc `tools/injection_bench.py` ferme les applications de test en début/fin de série (Bloc-notes compris, en force) ; le Bloc-notes Win11 restaure sa session au lancement (le banc efface le document témoin de toute façon) ; lecture du texte reçu = presse-papier vidé avant chaque copie ; quota gratuit = prendre son temps, réserver les ~6 % payants aux blocages impossibles.

### 5. Règle de Fin de Session
Avant de clore notre session (ou à chaque jalon validé), tu devras systématiquement :
1. Ajouter le compte-rendu détaillé des travaux dans `JOURNAL_DE_BORD.md`.
2. Mettre à jour la section 4 de ce fichier (`PROMPT_REPRISE.md`) pour préparer la session suivante.
3. Faire un commit et un push Git.
```
