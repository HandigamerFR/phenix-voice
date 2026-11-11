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
- **Correctifs (état actuel)** : champ correction éditable + sync texte + restauration focus cible avant remplacement ; fix double `?`/ponctuation dictée. **Régression injection persistante signalée** malgré revert `95ac384` (texte/touches incorrects à l’injection) : diagnostic en cours via nouveau `logs/injection_trace.jsonl` (actions envoyées vs dit/reconnu/injecté). Invalidation curseur et délais lots `SendInput` restent retirés.
- **Traçabilité & profil** : `logs/session_trace.jsonl` + audio `user_data/session_audio/seg_*.wav` (rotation 300) ; **`logs/injection_trace.jsonl`** (journal de session par action : injections/effacements/entrées/sélections/remplacements + commandes reconnues/exécutées, états/session, horodaté avec `session_id`, fenêtre cible, corrélation segment/audio ; diagnostics `SendInput` par action/lot `events_requested/inserted`, `send_ok`, `batch_results`, dernier caractère injecté) ; snapshots auto `user_data/snapshots/` (`demarrage`, `avant_correction`). **LoRA non actif** : corrections = données WAV/log dans `user_data/corrections_learned/` (2 conservées).
- **Prochaine tâche immédiate** :
  1. **Tester/fiabiliser correction & effacement** : application réelle dans l’éditeur, effacements successifs sans bouger curseur, cas ponctuation/commandes (« C’était une commande », épellation en correction). Si échec, s’appuyer sur `session_trace`.
  2. **Correction sur textes longs** : historique multi-segments + UI Automation (TextPattern/ValuePattern), occurrences, réécoute audio en correction, plus d’alternatives (jusqu’à 9).
  3. **Studio / rollback explicite** : UI/commandes snapshots (profil initial, restauration par nom), purge/reset corrections/règles, puis pipeline LoRA local DirectML avec validation avant entraînement.
### 5. Règle de Fin de Session
Avant de clore notre session (ou à chaque jalon validé), tu devras systématiquement :
1. Ajouter le compte-rendu détaillé des travaux dans `JOURNAL_DE_BORD.md`.
2. Mettre à jour la section 4 de ce fichier (`PROMPT_REPRISE.md`) pour préparer la session suivante.
3. Faire un commit et un push Git.
```
