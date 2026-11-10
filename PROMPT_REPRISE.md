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
  - [x] **Phase 0** : Cadrage, Cahier des charges, Architecture, Journal de bord, Prompt de reprise et création du dépôt GitHub privé `phenix-voice`.
  - [x] **Phase 1** : Socle Audio (*Silero VAD* calibré, AGC), Moteur GPU AMD *Whisper Large-v3-Turbo FP16* optimisé, Studio d'étalonnage vocal, Empreintes acoustiques DTW, Dictée directe `SendInput` et barre *No-Focus* (`WS_EX_NOACTIVATE`).
  - [x] **Phase 2 (+ itérations)** : *Shadow Buffer* (dernier segment), **Arbitre de Plausibilité Contextuelle & Acoustique**, Contrôle Micro 3 États sans conflit Dragon (`Phénix écoute`, `Phénix repos`, `Couper Phénix` + `F8`/`F9`), Correction Anti-Dérive (**« Corriger & Apprendre »** vs **« Annuler sans apprendre »**, validation explicite), **Aide « Que puis-je dire ? »**, correction manuelle, démarrage **100 % hors-ligne**, **ponctuation finale non forcée** (point/virgule auto retirés si non dictés), et **Mode épellation (alphabet radio NATO)**.
- **Phase en cours** : **Phase 3 & 4 — Correction sur Texte Long, Vocabulaire, Fine-Tuning LoRA (AMD DirectML) & Snapshots**
- **Prochaine tâche immédiate à réaliser** :
  1. Valider en direct : ponctuation non forcée sur phrases inachevées, **Mode épellation** (`Mode épellation` / `Fin épellation`, Alpha Bravo Charlie…), nouvelle commande **« Annuler sans apprendre »** (remplace « Oups »), et flux de correction sécurisé.
  2. Implémenter la **correction & sélection sur textes longs** : historique multi-segments du *Shadow Buffer* + lecture/sélection via *Windows UI Automation (TextPattern/ValuePattern)* avec gestion des occurrences multiples (« sélectionner/corriger [mot] », choix d'occurrence).
  3. Construire **Phénix Studio** (vocabulaire, import `.mbox`/`.eml`/docs, **mises à jour de modèle manuelles avec avertissement + sauvegarde anti-casse**, snapshots/restauration profil, préparation **Fine-Tuning LoRA local** DirectML avec réversibilité).
### 5. Règle de Fin de Session
Avant de clore notre session (ou à chaque jalon validé), tu devras systématiquement :
1. Ajouter le compte-rendu détaillé des travaux dans `JOURNAL_DE_BORD.md`.
2. Mettre à jour la section 4 de ce fichier (`PROMPT_REPRISE.md`) pour préparer la session suivante.
3. Faire un commit et un push Git.
```
