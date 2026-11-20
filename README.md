# Phénix Voice (`phenix-voice`) 🔥🎙️

**Phénix Voice** est une solution moderne de reconnaissance vocale, de dictée universelle et de contrôle de Windows 100 % locale, pensée pour s'adapter aux voix atypiques ou dysarthriques et remplacer avantageusement *Dragon NaturallySpeaking*.

> **Statut** : en développement actif. La phase « dictée + commandes + épellation »
> est fonctionnelle et testée en conditions réelles ; le projet recherche des
> contributeurs — voir [CONTRIBUTING.md](./CONTRIBUTING.md).
>
> **Transparence** : le code a été écrit **intégralement par une IA** — je ne
> programme pas en Python aujourd'hui. J'ai toutefois été **formé au
> développement il y a une dizaine d'années** : cette base me permet de
> **superviser** le projet (cadrer l'architecture, relire la logique, valider
> les comportements en conditions réelles), sans rédiger le code ligne à
> ligne. L'ensemble est estimé à **moins de 25 % terminé** : audit,
> architecture et optimisations restent à faire, d'où l'appel à contributeurs.

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
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | Guide du contributeur : mise en place, tests, conventions de code. |
| [`LICENSE`](./LICENSE) | Licence GNU GPL v3. |

---

## Feuille de Route (Synthèse)

- [x] **Phase 0** : Cadrage des besoins, architecture, journal de bord, prompt de reprise et création du dépôt GitHub.
- [x] **Phase 1** : Socle Audio, Accélération GPU AMD (Vulkan/DirectML) & Dictée Universelle de base (POC sans boîte de dictée).
- [x] **Phase 2** : *Shadow Buffer* & Interface de Correction Anti-Dérive (Voix + Souris, *Apprendre* vs *Oups*, empreintes acoustiques des commandes).
- [x] **Phase 3** : Adaptation Immédiate (Dictionnaire de règles *« A -> B »*, vocabulaire personnel & importateur moderne de mails/documents).
- [x] **Phase 4** : Studio d'Étalonnage Dysarthrie & Fine-Tuning Local (*LoRA* + *Snapshots* de profil + profils de fatigue).
- [x] **Phase 5** : Contrôle de Windows, Souris & Macros vocales (en cours de consolidation : entraînement LoRA + export ONNX validés).
- [ ] **Phase 6** : Expérience Multi-Utilisateurs, Auto-calibration matérielle & Installeur Windows.

Le détail session par session est dans [`JOURNAL_DE_BORD.md`](./JOURNAL_DE_BORD.md).

---

## Licence

Distribué sous **[GPL-3.0-only](./LICENSE)**.

Seule exception : `src/phenix_voice/resources/lexique_accords.tsv`, dérivé du
**Lexique 383** sous licence **CC BY-SA 4.0**
([`src/phenix_voice/resources/LICENSE-CC-BY-SA-4.0.txt`](./src/phenix_voice/resources/LICENSE-CC-BY-SA-4.0.txt)).

## Contribuer

Le projet recherche des co-développeurs — voir **[CONTRIBUTING.md](./CONTRIBUTING.md)**
(mise en place, tests, conventions). Les issues étiquetées
`bonne-premiere-contribution` sont un bon point de départ.
