# Phénix Voice (`phenix-voice`) 🔥🎙️

**Phénix Voice** est une solution moderne de reconnaissance vocale, de dictée universelle et de contrôle de Windows 100 % locale, pensée pour s'adapter aux voix atypiques ou dysarthriques et remplacer avantageusement *Dragon NaturallySpeaking*.

## Pourquoi Phénix Voice ?

1. **Adapté à la dysarthrie et aux voix atypiques** :
   - Apprentissage souple par étalonnage guidé (phonèmes, syllabes, mots, phrases) avec validation utilisateur.
   - Dictionnaire de règles déterministes prioritaires (*« Si tu entends A, écris B »*).
   - **Protection stricte contre la dérive du profil vocal** : séparation entre *« Corriger + Apprendre »* (erreur du logiciel) et *« Corriger SANS apprendre / Oups »* (bafouillage ou fatigue passagère de l'utilisateur), complétée par des points de restauration (*Snapshots*) du profil.
   - **Commandes vitales infaillibles** : les commandes de correction elles-mêmes sont personnalisables et protégées par reconnaissance d'empreinte acoustique directe.

2. **Dictée universelle (« Zéro Boîte de Dictée »)** :
   - Injection directe du texte dans 100 % des fenêtres Windows (navigateurs, applications Electron, terminaux, messageries web) grâce à un tampon mémoire synchronisé (*Shadow Buffer*) permettant de sélectionner et corriger à la voix ou à la souris directement sur place.

3. **100 % Local & Multi-GPU (AMD, Intel, NVIDIA)** :
   - Conçu pour tourner rapidement (< 500 ms) sur des configurations de milieu de gamme sans nécessiter de carte NVIDIA (support natif **Vulkan / DirectML / ONNX** pour les GPU AMD Radeon et Intel).

---

## Documentation du Projet

| Fichier | Rôle |
| :--- | :--- |
| [`PROMPT_REPRISE.md`](./PROMPT_REPRISE.md) | **Prompt de reprise concis** à fournir à un agent IA au début d'une nouvelle session pour reprendre le développement immédiatement. |
| [`JOURNAL_DE_BORD.md`](./JOURNAL_DE_BORD.md) | **Journal de développement exhaustif** consigné session après session (historique, décisions, avancement). |
| [`docs/CAHIER_DES_CHARGES.md`](./docs/CAHIER_DES_CHARGES.md) | Expression complète des besoins fonctionnels et ergonomiques (5 modules). |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Architecture technique (pipeline en 4 étages, stack multi-GPU) et feuille de route en 6 phases. |
| [`AGENTS.md`](./AGENTS.md) | Instructions automatiques pour les agents de code (OpenCode, etc.). |

---

## Feuille de Route (Synthèse)

- [x] **Phase 0** : Cadrage des besoins, architecture, journal de bord, prompt de reprise et création du dépôt GitHub.
- [ ] **Phase 1** : Socle Audio, Accélération GPU AMD (Vulkan/DirectML) & Dictée Universelle de base (POC sans boîte de dictée).
- [ ] **Phase 2** : *Shadow Buffer* & Interface de Correction Anti-Dérive (Voix + Souris, *Apprendre* vs *Oups*, empreintes acoustiques des commandes).
- [ ] **Phase 3** : Adaptation Immédiate (Dictionnaire de règles *« A -> B »*, vocabulaire personnel & importateur moderne de mails/documents).
- [ ] **Phase 4** : Studio d'Étalonnage Dysarthrie & Fine-Tuning Local (*LoRA* + *Snapshots* de profil + profils de fatigue).
- [ ] **Phase 5** : Contrôle de Windows, Souris & Macros vocales.
- [ ] **Phase 6** : Expérience Multi-Utilisateurs, Auto-calibration matérielle & Installeur Windows.
