# Inventaire des fonctionnalités — Dragon NaturallySpeaking 15 (Professional Individual, FR)

> **Comparatif fonctionnel face à Phénix Voice (`phenix-voice`)**

| | |
|---|---|
| **Date** | 15/11/2026 |
| **Objet** | Inventaire complet des fonctionnalités de Dragon 15 Pro (édition française), notées `[DÉJÀ]` / `[PARTIEL]` / `[ABSENT]` par rapport à Phénix Voice |
| **Sources** | (1) Aide FR installée : `C:\Program Files (x86)\Nuance\NaturallySpeaking15\Help\fra\ProfessionalIndividual` — (2) CHM extraits dans `$TEMP\opencode\dragon_help\` (`cmd_browser\` + `tagent\`) |
| **Artefacts d'extraction** | `$TEMP\opencode\dragon_fra_text\` (288 `.txt`), `dragon_fra_dump.txt` (849 989 car.), `dragon_help_dump.txt` (280 014 car.), `dragon_cited_commands.txt` (**943 formes de commandes**), scripts `extract_fra.py` / `extract_fra2.py` / `extract_dragon.py` |
| **Contexte Phénix** | `docs/CAHIER_DES_CHARGES.md` + `PROMPT_REPRISE.md` (§4 / §4bis) |
| **Nature du document** | **Consultation seule.** Tout est **reformulé** — aucun texte d'aide Nuance n'est recopié. |

---

## Table des matières

1. [Méthodologie : pages dépouillées et zones non couvertes](#1-méthodologie--pages-dépouillées-et-zones-non-couvertes)
2. [Thème 1 — Dictée, transcription et formatage](#2-thème-1--dictée-transcription-et-formatage)
3. [Thème 2 — Correction, sélection et révision (vue d'ensemble)](#3-thème-2--correction-sélection-et-révision-vue-densemble)
4. [**Sous-section dédiée — Correction et sélection par citation de texte (mécanisme UIA)**](#4-sous-section-dédiée--correction-et-sélection-par-citation-de-texte-mécanisme-uia)
5. [Thème 3 — Contrôle de Windows, souris et clavier](#5-thème-3--contrôle-de-windows-souris-et-clavier)
6. [Thème 4 — Mise en forme](#6-thème-4--mise-en-forme)
7. [Thème 5 — Applications métier et Web](#7-thème-5--applications-métier-et-web)
8. [Thème 6 — Vocabulaire et apprentissage](#8-thème-6--vocabulaire-et-apprentissage)
9. [Thème 7 — Commandes personnalisées et Explorateur de commandes](#9-thème-7--commandes-personnalisées-et-explorateur-de-commandes)
10. [Thème 8 — Ergonomie, Barre Dragon et aide](#10-thème-8--ergonomie-barre-dragon-et-aide)
11. [Top 14 — Fonctionnalités absentes probablement désirées](#11-top-14--fonctionnalités-absentes-probablement-désirées)
12. [Synthèse des compteurs](#12-synthèse-des-compteurs)

---

## 1. Méthodologie — pages dépouillées et zones non couvertes

### 1.1 Volumes

| Source | Fichiers | Exploités |
|---|---|---|
| Aide FR `...\Help\fra\ProfessionalIndividual` | **291** `.htm` | **288** (3 redirections sans contenu) |
| CHM extraits `$TEMP\opencode\dragon_help\` | **224** `.htm` (`cmd_browser` 122 + `tagent` 102) | **66** utiles |
| Index des commandes citées | **943** formes uniques | — |

- Les deux CHM se recouvrent à ~90 % ; leurs pages quasi-doublons ont été fusionnées.
- **158 des 224 pages CHM sont des stubs de navigation** (`navigational\*_nav.htm`, 79 × 2) sans aucun contenu fonctionnel.
- **≈ 354 pages de contenu réellement dépouillées.**
- Méthode : extraction texte → index des commandes entre guillemets → lecture ciblée intégrale des pages fonctionnelles (GettingStarted, Correction, Spelling, Commands, Dictation, WorkingWithText, CommandandControl, Vocabulary, Accuracy, Audio, DictationSources, DragonBar, DragonPad, Web, Users, MyCommands, CmdBrowser, WhatsNew, Help, tshoot + ~110 pages `DialogBoxes\` dont toutes les onglets Options).

### 1.2 Zones NON couvertes

- **Images et captures d'écran** : non lisibles dans l'extraction texte. Les aides-mémoire affichés uniquement en image (menus graphiques, certaines listes de l'Explorateur de commandes) sont absents de l'inventaire.
- **Référence de script VB** (`scriptref`) et **aide `nsadmin`** : hébergées sur le site Nuance, hors machine.
- **3 pages fra sans texte exploitable** + les **158 stubs** `navigational\*`.
- **Éditions Legal / Medical** et **Dragon Anywhere mobile** : non installées sur la machine.
- **Pages de dépannage** (`tshoot`, `DialogBoxes\problems`, `gsw`, `upgrade`, `subscriptions`) dépouillées **à titre indicatif seulement** : ce sont des procédures de réparation (registre `regsvr32`, Bluetooth, carte son, corruption de profil, connexion Nuance), pas des fonctionnalités à reconstruire.
- **Hors périmètre** : tout ce qui relève de la licence, de l'abonnement, de la distribution entreprise (`nsadmin`, Serveur de gestion Nuance).

### 1.3 Convention d'état

| État | Signification |
|---|---|
| **`[DÉJÀ]`** | Fonctionnalité **opérationnelle** dans Phénix (constatée dans `PROMPT_REPRISE.md` / `JOURNAL_DE_BORD.md`). |
| **`[PARTIEL]`** | Prévue au `CAHIER_DES_CHARGES.md` **mais non ou partiellement implémentée**, *ou* implémentée avec un périmètre réduit. |
| **`[ABSENT]`** | Ni dans le code ni au cahier des charges. |

Format retenu pour chaque fonctionnalité : **commande exacte** (entre `« »`, telle que citée dans l'aide) → **1 ligne de description** → **1 ligne d'état Phénix**.

---

## 2. Thème 1 — Dictée, transcription et formatage

**23 fonctionnalités**

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | `« (dictée libre) »` | Écriture directe au curseur dans la fenêtre active, sans boîte intermédiaire. | `[DÉJÀ]` Pilier « Zéro Boîte de Dictée », `SendInput` + `Shadow Buffer`, 18/18 apps validées. |
| 2 | Contrôle total du texte (anc. *Select-and-Say*) | Indicateur de la barre : le champ courant accepte sélection/correction vocale via modules de compatibilité. | `[PARTIEL]` Cible Phénix = `UI Automation` (`TextPattern`/`ValuePattern`) ; couverture par application non confirmée. |
| 3 | `« Ouvrir Boîte de dictée »` | Repli obligatoire là où aucun module de compatibilité n'existe (PowerPoint, invite de commandes, champs Electron). | `[ABSENT]` — *inversé* : c'est précisément le point que Phénix supprime. |
| 4 | `« Activer mode dictée »` / `« Activer mode commandes »` / `« Activer mode numérique »` / `« Activer mode épellation »` | Force le type d'entrée (texte / commandes / chiffres / lettres) pour supprimer l'arbitrage texte-vs-commande. | `[PARTIEL]` Phénix a le mode épellation, pas les modes numériques ni commandes. |
| 5 | `« Activer mode caché »` / `« Passer en mode caché »`, puis `« Transférer le texte »` (Ctrl+Maj+H) | Dictée en aveugle dans la Boîte de dictée puis injection différée ; ~6 commandes seulement actives en mode caché. | `[ABSENT]` (peu pertinent : Phénix écrit en direct). |
| 6 | `« point »`, `« virgule »`, `« point d'interrogation »`, `« nouveau paragraphe »`, `« ouvrez les guillemets »`… | Ponctuation dictée explicitement. | `[DÉJÀ]` `punctuation.py` + ponctuation finale auto non forcée (étape 1). |
| 7 | `« chiffre X »` / `« en lettres »` / `« mot X »` | Bascule chiffres↔lettres. | `[DÉJÀ]` (mode épellation seulement) ; `« Chiffre romain »` → `[ABSENT]`. |
| 8 | `« arobase »` | Reconnaissance des adresses e-mail/Web : `@` rendu comme mot, concaténation sans espaces. | `[PARTIEL]` Prévu Module 1, non signalé comme fait. |
| 9 | Options de formatage automatique (Outils > Options de formatage automatique) | Téléphones, dates (J/M/AAAA), prix, codes monétaires ISO, unités, « millions » vs `000 000`, seuil *nombre ≥ N en chiffres* (0/2/10/100). | `[ABSENT]` |
| 10 | Abréviations de titres | `Dr`, `Mme`, `Maj. Gen.`, `Prof.`… rendus abrégés automatiquement à la dictée du titre. | `[ABSENT]` |
| 11 | `« Afficher Règles de Formatage Intelligent »` | À la 1ʳᵉ correction d'un format auto, propose `1 – Ne jamais appliquer` / `2 – Toujours appliquer` ; le choix est **appris**. | `[ABSENT]` |
| 12 | `« Créer une liste à puces pour ça »` / `« Formater ça avec des puces »` / `« Annuler le formatage de ce texte avec des puces »` | Listes à puces par la voix. | `[ABSENT]` |
| 13 | Dictée juridique | Vocabulaire et formats spécialisés édition Legal. | `[ABSENT]` |
| 14 | Champ de résultats | Zone de saisie de résultats de calcul. | `[ABSENT]` |
| 15 | `Outils > Transcrire un enregistrement` | Transcription de `.wav/.mp3/.wma/.dss/.ds2/.m4a` (≥ 16 kHz), ponctuation auto, options de commandes interprétées. | `[ABSENT]` |
| 16 | Profil « transcription uniquement » | Transcrire la voix d'autrui sans polluer son propre profil. | `[ABSENT]` |
| 17 | Fichier `.DRA` (`Toujours` / `Jamais` / `Avec confirmation`) | Conserve l'audio de la dictée pour *corriger plus tard*. | `[DÉJÀ]` `logs/session_trace.jsonl` + `user_data/session_audio/seg_*.wav` (rotation 300). |
| 18 | `Profil > Gérer les sources de dictée` | Plusieurs périphériques audio sur un même profil ; permuter par la voix. | `[PARTIEL]` Prévu, non implémenté. |
| 19 | PowerMic III (options) | Personnalisation des boutons (clic gauche/droit, déclencheur, balayage tactile, commandes assignées). | `[ABSENT]` |
| 20 | Boîte de dictée : paramètres de collage | Options de transfert du texte (presse-papier, « Conserver dans le presse-papier »). | `[ABSENT]` |
| 21 | Éditeur Dragon / DragonPad | Éditeur intégré avec ses propres options texte et mise en forme. | `[PARTIEL]` |
| 22 | Guidelines de dictée | Recommandations de dictée (pauses, respiration) affichées en contexte. | `[DÉJÀ]` Aide intégrée « Que puis-je dire ? ». |
| 23 | Modes de reconnaissance de la Barre Dragon | Liste déroulante + point noir d'activation, sur les deux châssis de barre. | `[DÉJÀ]` HUD Phénix (3 états micro). |

---

## 3. Thème 2 — Correction, sélection et révision (vue d'ensemble)

**22 fonctionnalités** — *le détail du mécanisme de citation est traité en §4.*

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | `« Corriger ça »` | Ouvre le menu Correction sur le dernier texte dicté. | `[DÉJÀ]` |
| 2 | `« Effacer ça »` / `« Annuler ça »` · `« Effacer ceci »` / `« Annuler ceci »` | Supprime ou annule le dernier segment. | `[DÉJÀ]` |
| 3 | `« Choisir <nombre> »` / `« Choisir <numéro> »` | Sélectionne une alternative numérotée. | `[DÉJÀ]` `CHOOSE_MAP` 1→9 |
| 4 | Menu Correction | Alternatives + bascule épellation + réécoute dans une même surface. | `[DÉJÀ]` `CorrectionWindow` grille 3×3, 9 boutons |
| 5 | `« Epeler ça »` | Ouvre directement la fenêtre d'épellation au lieu du menu. | `[DÉJÀ]` `SpellingWindow` |
| 6 | Options > Correction | Nombre d'alternatives, ancrage près du curseur, double-clic, rejeu auto à la correction, bascule *menu* ↔ *fenêtre d'épellation*. | `[PARTIEL]` |
| 7 | `« Rejouer ça »`, `« Rejouer la ligne »`, `« Rejouer le paragraphe »`, `« Rejouer le document »`, `« Rejouer à partir d'ici »`, `« Rejouer jusqu'ici »` | Réécoute de l'audio enregistré (barre de fonctions avancées). | `[ABSENT]` |
| 8 | `« Rejouer la fenêtre »` / `« Rejouer l'écran »` | Relit ce qui est affiché à l'écran. | `[ABSENT]` |
| 9 | Boîte Historique de reconnaissance | Liste les énoncés de la session avec l'heure ; consultable, **non corrigeable**. | `[ABSENT]` |
| 10 | Correction de la dictée d'un autre utilisateur | Ouverture du `.DRA` d'un collègue, réécoute + correction. | `[ABSENT]` |
| 11 | Correction de commandes mal reconnues | Distinction *commande ratée* vs *texte dicté*, réassignation. | `[DÉJÀ]` « C'était une commande » (panneau trié = étape 4) |
| 12 | Classification correction « règle de texte » vs « acoustique » | Une correction orthographique n'alimente jamais l'apprentissage audio. | `[DÉJÀ]` `is_textual_only_correction` |
| 13 | Séparation « Corriger & Apprendre » vs « Corriger sans apprendre » | Deux actions distinctes avec validation explicite. | `[DÉJÀ]` — **avantage Phénix** |
| 14 | Snapshots du profil | Sauvegarde/restauration des états du profil vocal. | `[DÉJÀ]` `user_data/snapshots/` |
| 15 | Annulations limitées | 25 révisions `Corriger` ; 50 pour gras/italique/souligner/supprimer. | `[PARTIEL]` |
| 16 | `« Prendre <numéro> »` / `« Prendre tout »` / `« Annuler tout »` | Action sur une instance précise, sur toutes, ou retour en arrière global. | `[ABSENT]` |
| 17 | Numérotation des instances multiples | Des numéros s'affichent en regard de chaque occurrence trouvée (option *Activer la sélection de plusieurs instances*). | `[ABSENT]` |
| 18 | `« Sélectionner ça »` / `« Sélectionner à nouveau »` | Reprend le fragment, puis l'occurrence suivante du même fragment. | `[PARTIEL]` |
| 19 | `« Désélectionner ça »` | Annule la sélection courante. | `[ABSENT]` |
| 20 | `« Insérer avant <texte> »` / `« Insérer après <texte> »` | Déplace le curseur *autour* du fragment cité pour y dicter. | `[ABSENT]` |
| 21 | `« Reprendre <texte> »` | Re-positionne le curseur sur le fragment, puis on dicte la suite. | `[ABSENT]` |
| 22 | Fenêtre d'épellation (`SpellingWindow`) | Champ pré-rempli modifiable, append des chunks, insertion au curseur, boutons Vider/Appliquer. | `[DÉJÀ]` |

---

## 4. Sous-section dédiée — Correction et sélection **par citation de texte** (mécanisme UIA)

> *Cœur de la demande. Tout est reformulé d'après `Correction/correcting_your_dictation`, `Correction/about_correction`, `WorkingWithText/selecting_and_deselecting`, `WorkingWithText/working_with_multiple_text_matches`, `WorkingWithText/inserting_replacing_and_deleting_text`, `Dictation/about_full_text_control`, `Dictation/about_unknown_text_fields`, `DialogBoxes/options/options_dialog_correct_tab`, `tshoot/commands_entered_as_text`, `problems/compat_mode_msg`, et les pages applicatives `commands/app_level2/{gmail,google_docs,msword_web_app}`.*

### 4.1 Commandes exactes

| Commande | Effet |
|---|---|
| `« Corriger ça »` | Dernier texte dicté → menu Correction |
| **`« Corriger <texte> »`** | Cite un fragment dicté → Dragon **cherche ce fragment dans le document** puis ouvre le menu Correction dessus |
| **`« Corriger <texte> à <texte> »`** | Cite le début et la fin → sélectionne l'intervalle |
| **`« Corriger de <texte> à <texte> »`** / **`« Corriger de <texte> jusqu'à <texte> »`** | Variante régionale de la plage |
| **`« Sélectionner <texte> »`** | Sélectionne le fragment cité (ouvre le menu Correction par défaut) |
| **`« Sélectionner <texte> à <texte> »`** / **`« Sélectionner de <texte> à <texte> »`** | Sélection d'intervalle par citation |
| **`« Sélectionner ça »`** | Reprend le dernier fragment manipulé |
| **`« Sélectionner à nouveau »`** / **`« Sélectionner ça à nouveau »`** | Occurrence suivante du même fragment |
| **`« Epeler ça »`** | Ouvre la fenêtre d'épellation au lieu du menu Correction |
| **`« Epeler <texte> »`** | Épellation d'un fragment cité |
| `« Effacer <texte> »`, `« Couper <texte> »`, `« Copier <texte> »` (+ formes `de X à Y`) | Actions directes sur fragment cité — **raccourcis à activer** en Options > Commandes (`Activer le raccourci de commande Supprimer / Couper / Copier` ; `Copier` désactivé par défaut) |
| `« Insérer avant <texte> »` / `« Insérer après <texte> »` | Déplace le curseur autour du fragment cité |
| `« Reprendre <texte> »` | Re-positionne le curseur sur le fragment |

**Sélection relative — plafond `<1-20>`** (même family pour **mots**, **caractères**, **lignes**, **paragraphes**) :

- `« Sélectionner les <1-20> mots précédents »` · `… mots suivants` · `… mots avant` · `… mot arrière` · `… derniers mots`
- `« Sélectionner les <1-20> caractères précédents »` (etc.), `« Sélectionner les <1-20> lignes … »`, `« Sélectionner les <1-20> paragraphes … »`
- Suppressions correspondantes : **`« Effacer les <2-20> mots précédents »`** — plafond **20**, base **2** (la forme `« Effacer le mot 1 précédent »` couvre l'unité).
- Navigation curseur : `« <1-20> mots à droite | à gauche | vers l'avant | vers l'arrière »`, idem lignes/paragraphes, `« <1-20> à droite/gauche »` (caractères).
- Réserve : `« Sélectionner le document »` / `« Sélectionner tout »`, `« Sélectionner le dernier mot | paragraphe | ligne »`.

> ⚠️ **Il n'existe aucune commande « Corriger les N *souffles* précédents »** : Dragon ne compte qu'en **unités de texte** (mots / lignes / paragraphes), jamais en segments audio. C'est la raison pour laquelle cette extension est une innovation Phénix, pas une copie.

### 4.2 Le mécanisme — ce que l'aide révèle

1. **Pas d'OCR, jamais.** Tout repose sur le **Contrôle total du texte** :
   - modules de compatibilité par application (`dgnword.dll`, `dgnoutlook.dll`, `dgnexcel.dll`, `dgnwp9.dll`, `web_ie.dll`, ré-enregistrables via `regsvr32`) ;
   - **`MSAA` / Active Accessibility** pour les menus et boîtes de dialogue (option *« Activer les commandes vocales pour les menus et les boîtes de dialogue »*, désactivable **par programme**) ;
   - **extension Web** pour les navigateurs (Chrome, Firefox, Edge, IE).
2. **L'aide liste explicitement le symptôme d'absence** : sans Contrôle total, Dragon « ne peut pas effectuer de corrections ni de commandes qui citent des mots de votre texte (telles que *supprimer…* ou *sélectionner…* ) », n'insère ni majuscule de début de phrase ni espace, et ouvre la Boîte de dictée.
3. **Recherche dans le document, à partir du curseur.** `« Sélectionner <texte> »` interroge le **texte réel du champ** en partant du point d'insertion — *pas* un historique interne de dictée.
4. **Sens de recherche commutable.** Option *« Les commandes « Sélectionner » recherchent en arrière »* ; sinon la recherche ne progresse que vers la fin — d'où l'utilité de `« Sélectionner ça à nouveau »`.
5. **Plafond de 70 caractères** pour une correction par citation (constaté tel quel dans l'aide : *« vous pouvez corriger un texte de 70 caractères maximum à une fois »*). *Conseil officiel : pour corriger un **petit** mot, sélectionner plutôt les mots environnants* — le mot isolé est trop ambigu.
6. **Ouverture conditionnelle du menu.** Option *« Les commandes « Sélectionner » affichent le menu Correction »* ; si désactivée, `« Sélectionner <texte> »` ne fait que sélectionner. Symétriquement, l'option *« Les commandes "Corriger" affichent la fenêtre d'épellation »* fait basculer `« Corriger … »` vers l'épellation au lieu du menu.
7. **Occurrences multiples numérotées.** Si le fragment apparaît N fois, des numéros s'affichent ; on tranche par `« <numéro> »` / `« Prendre <numéro> »`, ou tout d'un coup par `« Prendre tout »`. Réglage : *« Activer la sélection de plusieurs instances d'un mot ou groupe de mots »* — **désactivé, Dragon n'agit que sur l'occurrence la plus proche du curseur** (erreur silencieuse fréquente sur texte long).
8. **Fenêtres applicatives.** La citation fonctionne **dans la fenêtre qui a le focus**, et uniquement dans les champs contrôlés. Exemples contraires documentés : dans **Google Docs** et **Word Online** *sans* Contrôle total, on peut dicter et dire `« ligne »`, mais **on ne peut pas** `« Corriger <mot(s)> »` ni `« Supprimer <mot(s)> »` — l'unique recours est la Boîte de dictée.
9. **Limites d'annulation** : 25 révisions `Corriger`, 50 pour formatages/suppressions ; `« Annuler tout »` ne déroule que la dernière action `Prendre tout`.
10. **Historique et audio** : l'historique de session est consultable mais **non corrigeable** ; la réécoute n'existe que dans les champs à Contrôle total, et l'audio est purgé à la fermeture de l'application (sauf `.DRA` conservé).
11. **Interaction avec les Règles de formatage intelligent** : une correction qui touche un format auto déclenche l'invite de règle (`1 – Ne jamais` / `2 – Toujours`).

### 4.3 État Phénix sur cette sous-section

| Élément | État | Commentaire |
|---|---|---|
| Fenêtre de correction **ne volant jamais le focus** de la fenêtre cible | `[DÉJÀ]` | `CorrectionWindow` : `Tool window`, `WA_ShowWithoutActivating`, grille 3×3, champ éditable, bascule 🧠/🛡️, ✕ = annuler. |
| `« Corriger ça »`, `« Effacer ça »`, alternatives numérotées `Choisir 1…9` | `[DÉJÀ]` | + libellé ✅/⚠️/❌ `n/9`. |
| `« Epeler ça »` → fenêtre d'épellation séparée | `[DÉJÀ]` | `SpellingWindow` : pré-remplie, modifiable, append, insertion au curseur. |
| **`« Corriger <texte> »` / `« Sélectionner <texte> »` sur texte long** | `[PARTIEL]` | Prévu au **CAHIER §Module 1** (« lecture directe du champ texte via `TextPattern`/`ValuePattern` », numérotation des occurrences, retrouvaille de l'extrait audio correspondant). Fonction `select_word` présente dans les logs (`select_word_not_found`) — **couverture UIA et numérotation des instances non confirmées**. |
| Sélection relative `<1-20>` (mots/caractères/lignes/paragraphes) | `[ABSENT]` | Non listée dans `PROMPT_REPRISE.md` ; le `deque` du `Shadow Buffer` fait 25. |
| Plages `de X à Y`, `« Sélectionner à nouveau »`, `« Insérer/Reprendre <texte> »` | `[ABSENT]` | |
| Plafond 70 caractères, options de sens de recherche, option menu↔épellation | `[ABSENT]` | À arbitrer : le plafond Dragon est une **limite**, pas un objectif. |
| Numérotation des instances + `« Prendre tout »` | `[ABSENT]` | Voir Top #6. |
| Réécoute, historique de session | `[ABSENT]` | Voir Top #3 et #4. |
| **Correction « Apprendre » vs « Sans apprendre »** | `[DÉJÀ]` | **Avantage Phénix** : Dragon n'a pas cette distinction fine. |
| Protection des commandes de correction par **empreinte acoustique** | `[DÉJÀ]` | Dragon n'a que l'« adaptation » manuelle. **Avantage Phénix.** |

---

## 5. Thème 3 — Contrôle de Windows, souris et clavier

**45 fonctionnalités**

### 5.1 Souris (10)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | `« Souris clic »` / `« Souris clic droit »` / `« Souris double clic »` | Clics standards au point courant. | `[PARTIEL]` |
| 2 | `« Souris à gauche <1-10> »` / `« Souris à droite <1-10> »` / `« Souris en haut <1-10> »` / `« Souris en bas <1-10> »` | Déplacement par paliers avec accélération. | `[PARTIEL]` |
| 3 | `« Déplacer la souris à droite | à gauche | en haut | en bas | en haut à droite … »` | Déplacement directionnel continu. | `[PARTIEL]` |
| 4 | `« Damier de souris »` / `« Fenêtre du Damier de souris »` | MouseGrid 3×3 récursive, `« Choisir <numéro> »` pour descendre d'un niveau. | `[PARTIEL]` CAHIER Module 5, non implémenté |
| 5 | `« Glisser la souris à … »` | Glisser-déposer directionnel. | `[ABSENT]` |
| 6 | `« Contrôler glisser la souris … »` | Glisser en mode maintien (8 directions). | `[ABSENT]` |
| 7 | `« Taper Ctrl clic de souris »` / `« Taper Maj clic de souris »` | Clic combiné. | `[ABSENT]` |
| 8 | Option *« Commandes de la souris »* | Active/désactive tout le bloc souris (gain de performance si off). | `[ABSENT]` |
| 9 | Réglage **vitesse** de déplacement (défaut 2) | Vitesse du pointeur vocal. | `[ABSENT]` |
| 10 | Clic sur éléments numérotés | Surbrillance numérotée des boutons/liens cliquables (CAHIER Module 5). | `[PARTIEL]` |

### 5.2 Clavier et édition (5)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 11 | `« Ctrl <touche> »`, `« Maj <touche> »`, `« Alt <touche> »`, `« Ctrl Maj <touche> »`, `« Ctrl Alt <touche> »` | Envoi de combinaisons. | `[PARTIEL]` |
| 12 | `« Pavé numérique <touche> »` | Touche du pavé numérique. | `[ABSENT]` |
| 13 | `« Retour arrière »` / `« Touche Retour arrière <2-20> »` | Retour arrière avec répétition. | `[PARTIEL]` |
| 14 | `« Copier ça »` / `« Couper ça »` / `« Coller ça »` | Actions sur la dernière sélection. | `[PARTIEL]` |
| 15 | `« Annuler ça »` / `« Refaire »` / `« Annuler tout »` | Historique d'édition. | `[DÉJÀ]` |

### 5.3 Fenêtres et bureaux (11)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 16 | `« Fermer la fenêtre »` / `« Réduire la fenêtre »` / `« Agrandir la fenêtre »` | Gestion standard de fenêtre. | `[PARTIEL]` |
| 17 | `« Fenêtre précédente »` / `« Fenêtre suivante »` | Alternance rapide (type Alt+Tab). | `[ABSENT]` |
| 18 | `« Lister toutes les fenêtres »` / `« Lister les fenêtres pour <nom du programme> »` | Listage vocalisé puis sélection. | `[ABSENT]` |
| 19 | `« Ancrer la fenêtre à droite | à gauche | en haut | en bas »` | Snap Windows par la voix. | `[ABSENT]` |
| 20 | `« Créer un bureau virtuel »` / `« Ajouter le bureau »` | Bureaux virtuels. | `[ABSENT]` |
| 21 | `« Passer au bureau virtuel suivant »` / `« Fermer ce bureau virtuel »` | Navigation entre bureaux. | `[ABSENT]` |
| 22 | `« Afficher le Bureau »` | Minimise tout. | `[ABSENT]` |
| 23 | `« Lancer le menu Démarrer »` / `« Cliquer menu Démarrer »` / `« Développer le menu Démarrer »` | Accès au menu Démarrer. | `[ABSENT]` |
| 24 | `« Ouvrir le Gestionnaire de tâches »` / `« Ouvrir la vue des tâches »` | Outils système. | `[ABSENT]` |
| 25 | `« Ouvrir le Panneau de configuration »` / `« Ouvrir la boîte de dialogue Exécuter »` / `« Ouvrir Ajout ou suppression de programmes »` | Raccourcis système. | `[ABSENT]` |
| 26 | `« Lire la fenêtre »` | Synthèse vocale de la fenêtre active. | `[ABSENT]` |

### 5.4 Lancement et recherche (8)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 27 | `« Ouvrir <nom de l'application> »` | Lancement direct (option *« Lancer par la voix des programmes du menu Démarrer »*). | `[PARTIEL]` |
| 28 | `« Ouvrir mes documents »` / `« Ouvrir mon ordinateur »` / `« Ouvrir ma musique »` / `« Ouvrir mes images »` | Dossiers système. | `[ABSENT]` |
| 29 | `« Rechercher sur l'ordinateur <mots-clés> »` | Recherche Windows (option *« Activer les commandes de recherche de Bureau »*). | `[ABSENT]` |
| 30 | `« Rechercher <mots-clés> sur Internet »` | Recherche Web. | `[ABSENT]` |
| 31 | `« Rechercher <mots-clés> sur <site web> »` | Recherche sur un site imposé. | `[ABSENT]` |
| 32 | `« Rechercher <mots-clés> dans les documents | dans la messagerie électronique | dans les Favoris | dans les signets | dans l'historique Web »` | Recherche multi-sources. | `[ABSENT]` |
| 33 | Option *« Afficher le texte avant d'effectuer la recherche »* | Fenêtre de confirmation/édition des termes avant recherche. | `[ABSENT]` |
| 34 | `« Ouvrir le meilleur site Web sur <mot-clé> »` | Recherche orientée navigation. | `[ABSENT]` |

### 5.5 Menus, boutons et contrôles (11)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 35 | `« Cliquer <option de menu> »` / `« Cliquer <nom du bouton> »` / `« Cliquer <nom de la case à cocher> »` | Clic par libellé d'élément d'interface. | `[PARTIEL]` |
| 36 | `« Cliquer <nom du bouton radio> »` / `« Cliquer <nom du lien> »` / `« Cliquer <nom de l'onglet> »` | Idem pour les autres types de contrôles. | `[PARTIEL]` |
| 37 | `« Cliquer <nom de l'image> »` / `« Cliquer <nom du champ de texte> »` / `« Cliquer <nom du dossier> »` | Idem. | `[PARTIEL]` |
| 38 | `« Afficher les liens »` / `« Afficher les commandes d'application »` / `« Cacher les numéros »` | Numérotation des éléments cliquables. | `[PARTIEL]` |
| 39 | `« Choisis <numéro> »` / `« <numéro> »` | Sélection par numéro affiché. | `[DÉJÀ]` |
| 40 | Option *« "Cliquer" est obligatoire pour sélectionner un menu »* | Anti-clic accidentel pendant la dictée. | `[ABSENT]` |
| 41 | Option *« "Cliquer" est obligatoire pour sélectionner un contrôle »* | Idem pour boutons/contrôles. | `[ABSENT]` |
| 42 | Option *« "Cliquer" est obligatoire pour sélectionner les hyperliens dans la fenêtre HTML »* | Idem pour les liens Web. | `[ABSENT]` |
| 43 | Option *« Activer les commandes vocales pour les menus, les boutons et autres contrôles »* (Active Accessibility) | Désactivable **globalement ou par programme** pour accélérer la dictée. | `[ABSENT]` |
| 44 | Option *« Activer les commandes pour changer de mode de reconnaissance »`* | Autorise `« Activer mode dictée »` etc. | `[PARTIEL]` |
| 45 | Option *« Activer la prise en charge de HTML »* / *« Commandes supplémentaires dans les fenêtres HTML »* | Active les commandes Web et les boîtes Outlook HTML. | `[ABSENT]` |

### 5.6 Micro, aide et réglages transverses (4)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 46 | `« Au repos »` / `« Au travail »` | Pause/reprise à la voix. | `[DÉJÀ]` |
| 47 | `« Éteindre le microphone »` + bascule physique F8/F9 | Coupure matérielle/vocale. | `[DÉJÀ]` (« Couper Phénix ») |
| 48 | `« Vérifier le microphone »` | Assistant de vérification (niveau, positionnement, carte son). | `[PARTIEL]` |
| 49 | `« Que puis-je dire ? »` · `« Ouvrir l'aide »` · `« Rechercher dans l'aide… »` | Aide contextuelle et recherche. | `[DÉJÀ]` / `[PARTIEL]` |
| 50 | Option *« Pause requise avant les commandes »* | **250 ms par défaut** ; ne s'applique pas aux commandes de dictée. | `[PARTIEL]` |

> *Compteur Thème 3 : 50 entrées (les sous-titres indiquent le détail ; le total par sous-section est indicatif).*

---

## 6. Thème 4 — Mise en forme

**19 fonctionnalités**

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | `« Mettre en gras <texte> »` / `« <texte> en gras »` | Gras sur fragment cité. | `[ABSENT]` |
| 2 | `« Ceci en gras »` / `« Sélection en gras »` | Gras sur la sélection courante. | `[ABSENT]` |
| 3 | `« Dernier paragraphe en gras »` / `« <nombre> mots suivants en gras »` / `« Mot suivant en gras »` / `« Phrase suivante en gras »` | Formatage sur unité relative. | `[ABSENT]` |
| 4 | `« <texte> à <texte> en gras »` | Plage citée. | `[ABSENT]` |
| 5 | Mêmes formes pour **italiques** | `« … en italiques »`, `« Sélection en italiques »`… | `[ABSENT]` |
| 6 | Mêmes formes pour **souligné** | `« … soulignés »`, `« Mot suivant souligné »`… | `[ABSENT]` |
| 7 | `« Formater ça en gras | en italiques | en souligné | avec des puces | sans puces »` | Sur la dernière sélection. | `[ABSENT]` |
| 8 | `« Formater ça <type de police> <taille de la police> <style de police> »` | Police + taille + style en une commande. | `[ABSENT]` |
| 9 | `« Définir la police sur <nom de la police> »`, `… dans cette phrase`, `… dans ce document` | Portée explicite dans la commande. | `[ABSENT]` |
| 10 | `« Définir ce texte avec des puces »` / `« Formater ça sans puces »` | Puces sur sélection. | `[ABSENT]` |
| 11 | `« Police taille <taille> points »` / `« Augmenter la police à <nombre> points »` | Taille numérique. | `[ABSENT]` |
| 12 | `« Tout en maj »` / `« Majuscule »` / `« Ceci tout en maj »` / `« <mot> en majuscules »` / `« <mot> pas en majuscules »` | Commandes de casse. | `[DÉJÀ]` `_CASING_COMMANDS`, singulier/pluriel |
| 13 | `« Annuler toutes maj »` / `« Annuler toutes min »` / `« Désactiver maj »` | Fin de bascule persistante. | `[PARTIEL]` |
| 14 | `« Formater le mot suivant en majuscules »` | Casse sur unité. | `[ABSENT]` |
| 15 | `« Nouveau paragraphe »` / `« Sélectionner le paragraphe »` | Paragraphe. | `[DÉJÀ]` casse inter-souffles |
| 16 | `« Sélection entre guillemets »` / `« Mettre la sélection entre guillemets »` | Guillemets sur sélection. | `[ABSENT]` |
| 17 | `« Déplacer le paragraphe vers l'avant de <nombre> paragraphes »` | Réordonnancement. | `[ABSENT]` |
| 18 | Alignement du texte | Alignements (gauche/centré/droite/justifié). | `[ABSENT]` |
| 19 | Propriétés de mot | Forme imprimée, espaces avant/après, capitales, abréviations. | `[ABSENT]` |

---

## 7. Thème 5 — Applications métier et Web

**34 fonctionnalités**

### 7.1 Applications de bureau (5)

| # | Cible | Exemples de commandes | État |
|---|---|---|---|
| 1 | **Microsoft Word** | `« <texte> en gras »`, tables, ruban, déplacement dans le document. | `[PARTIEL]` |
| 2 | **Microsoft Excel** | `« Sélectionner la cellule <colonne><ligne> »`, `« Sélectionner la colonne <lettre> »`, `« Colonne suivante »`, `« Ligne suivante »`, `« Effacer tout de la cellule | de la colonne | de la ligne »`, `« Colonne <lettre> en gras »`. | `[ABSENT]` |
| 3 | **Microsoft PowerPoint** | `« Ajouter un titre de diapositive »`, `« Ajouter une nouvelle présentation »`, navigation de diapositives. | `[ABSENT]` |
| 4 | **Corel WordPerfect** | Prise en charge native équivalente à Word. | `[ABSENT]` |
| 5 | **Skype** | `« Créer une réunion Skype »`, `« Organiser une réunion »`. | `[ABSENT]` |

### 7.2 Outlook — raccourcis vocaux à langage naturel (12)
*Option « Activer les commandes pour l'e-mail et la gestion de calendrier »*

| # | Commande | Description | État |
|---|---|---|---|
| 6 | `« Composer un nouveau message »` | Nouveau courriel. | `[ABSENT]` |
| 7 | `« Envoyer un message à <contact> »` / `« Envoyer un e-mail sur <objet> »` | Envoi à langage naturel. | `[ABSENT]` |
| 8 | `« Envoyer la sélection par e-mail à <contact> »` | Transmission du texte sélectionné. | `[ABSENT]` |
| 9 | `« Planifier un rendez-vous le <mois><jour> à <heure> »` | Rendez-vous daté en une commande. | `[ABSENT]` |
| 10 | `« Planifier une réunion avec <contact> »` / `« Planifier une réunion sur <objet> »` | Réunion. | `[ABSENT]` |
| 11 | `« Créer rendez-vous pour <objet> »` / `« Générer rendez-vous »` | Variante courte. | `[ABSENT]` |
| 12 | `« Créer une tâche sur <objet> »` | Tâche. | `[ABSENT]` |
| 13 | `« Aller au message suivant | précédent »` | Navigation dans la liste. | `[ABSENT]` |
| 14 | `« Aller au champ Corps de message »` | Saut de champ. | `[ABSENT]` |
| 15 | `« Obtenir tous les nouveaux messages »` | Actualisation. | `[ABSENT]` |
| 16 | `« Cliquer Répondre »` / `« Cliquer Répondre à tout »` | Réponse par libellé. | `[ABSENT]` |
| 17 | `« Ouvrir la pièce jointe »` / `« Afficher les fichiers récents à associer en pièce jointe »` | Pièces jointes. | `[ABSENT]` |

### 7.3 Navigateurs et Web (12)

| # | Commande / nom | Description | État |
|---|---|---|---|
| 18 | **Extension Web Dragon** (Chrome, Firefox, Edge, IE) | Contrôle total du texte + clic sur éléments de page. | `[PARTIEL]` |
| 19 | `« Aller à une adresse »` / `« Aller à cette adresse »` / `« Aller à la barre d'adresse »` | Navigation URL. | `[ABSENT]` |
| 20 | `« En avant »` / `« En arrière »` / `« Page en avant »` | Historique du navigateur. | `[ABSENT]` |
| 21 | `« Ouvrir un nouvel onglet »` / `« Créer un onglet »` | Onglets. | `[ABSENT]` |
| 22 | `« Fermer l'onglet »` / `« Fermer cet onglet »` | Fermeture d'onglet. | `[ABSENT]` |
| 23 | `« Ouvrir ça dans un nouvel onglet »` / `« … en arrière-plan »` | Onglet en arrière-plan. | `[ABSENT]` |
| 24 | `« Ouvrir l'onglet suivant »` / `« Ouvrir l'onglet précédent »` / `« Aller au <nième> onglet »` | Navigation d'onglets. | `[ABSENT]` |
| 25 | `« Afficher les commandes du site »` / `« Cacher les commandes du site »` | Bulle des commandes propres au site (Gmail, messageries). | `[ABSENT]` |
| 26 | Messageries en ligne (Gmail/Yahoo) : `« Cliquer Boîte de réception »`, `« Cliquer Messages envoyés »`, `« Cliquer Brouillons »`, `« Aller à Destinataire »`, `« Prendre <n> »` sur autocomplétion | Navigation de messagerie Web. | `[ABSENT]` |
| 27 | Google Docs / Word Online | *Pas* de Contrôle total → dictée directe limitée (**pas** de `« Corriger <mot(s)> »`), recours à la Boîte de dictée. | `[ABSENT]` — *contre-exemple qui confirme la dépendance UIA (§4.2)* |
| 28 | Facebook / Twitter | Publication par commande vocale. | `[ABSENT]` |
| 29 | Google Docs / Office 2013 / Word Online (`app_level2`) | Pages CHM uniques : menus et rubans par numérotation (`« Cliquer lien »` → `« Prendre <x> »`). | `[ABSENT]` |

### 7.4 Recherche Web (5)

| # | Commande | Description | État |
|---|---|---|---|
| 30 | `« Rechercher des horaires de cinéma à Boston sur Bing »` (typique) | Recherche en langage naturel avec site imposé. | `[ABSENT]` |
| 31 | `« Rechercher <date, heure, nom ou calcul> sur <site Web> »` | Recherche structurée. | `[ABSENT]` |
| 32 | `« Rechercher des images … »` | Recherche d'images. | `[ABSENT]` |
| 33 | Option *« Activer les commandes de recherche de Web »* | Activation/désactivation du bloc. | `[ABSENT]` |
| 34 | `« Ouvrir Internet Explorer »` / `« Ouvrir Google Chrome »` / `« Ouvrir Microsoft Edge »` / `« Ouvrir Mozilla Firefox »` | Ouverture de navigateur par la voix. | `[PARTIEL]` |

---

## 8. Thème 6 — Vocabulaire et apprentissage

**20 fonctionnalités**

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | `« Ouvrir l'éditeur de vocabulaire »` | Ajout/édition/suppression de mots et formes orales. | `[PARTIEL]` CAHIER Module 4 |
| 2 | `« Adapter »` / `« Adapter ça »` | Enregistre une prononciation pour un mot/expression/commande. | `[DÉJÀ]` studio + empreintes DTW |
| 3 | Ajouter un nouveau mot/expression | Ajout rapide depuis la dictée. | `[PARTIEL]` |
| 4 | Fenêtre d'épellation → vocabulaire | Épeler un mot inconnu puis l'ajouter. | `[PARTIEL]` |
| 5 | `Vocabulaire > Apprendre à partir de documents spécifiques` | Analyse locale, liste des mots inconnus avec fréquence, cases à cocher, puis adaptation. | `[PARTIEL]` CAHIER Module 4 |
| 6 | `Vocabulaire > Apprendre à partir des messages envoyés` | Analyse des messages envoyés (Outlook + messageries web via IMAP/POP), extraction des noms de contacts, adaptation du modèle linguistique. | `[PARTIEL]` — *fonction explicitement déclarée obsolète au §1.2.3 du cahier* (`.mbox`/`.eml`/IMAP-OAuth prévu) |
| 7 | Rappel périodique d'analyse | 2 jours après création, puis chaque semaine, puis chaque mois ; désactivable. | `[ABSENT]` |
| 8 | `Vocabulaire > Exporter/Importer une liste de mots…` | `.TXT` ou `.XML` (XML conserve les propriétés de mot). | `[PARTIEL]` |
| 9 | Fenêtre *Laissez Dragon rechercher des mots* | Analyse « Mes documents » + « Messages envoyés » en une passe (docs < 512 octets ou > 90 jours exclus). | `[PARTIEL]` |
| 10 | Propriétés de mot | Forme imprimée, espaces avant/après, capitales, abréviations. | `[ABSENT]` |
| 11 | Vocabulaires multiples + dictionnaire de réserve | Création/renommage/export de vocabulaires. | `[ABSENT]` |
| 12 | Vocabulaire `BestMatch Plus` | Petit vocabulaire pour machine faible (512 Mo), sélection à la création du profil. | `[ABSENT]` |
| 13 | `Audio > Lancer l'Optimisation de la précision` | Fusionne jusqu'à **180 min** de données acoustiques + séquences de mots fréquents ; optimisation **acoustique** et **linguistique** séparées. | `[PARTIEL]` snapshots / LoRA étape 5 |
| 14 | Modèles acoustiques | Choix/optimisation automatique du modèle selon l'accent ; option pour bloquer. | `[PARTIEL]` étape 5 |
| 15 | Modèle linguistique | Statistiques de séquences issues des `.DRA`. | `[PARTIEL]` |
| 16 | Profils utilisateur | Création/renommage/suppression/import/export/sauvegarde/restauration + propriétés (langue, vocabulaire, modèle vocal, dernière sauvegarde). | `[PARTIEL]` |
| 17 | Assistant nouveau profil | Langue, **région**, **accent** (Standard, adolescents, accents régionaux), âge, vérification micro, lecture de texte d'apprentissage (10 min – 1 h). | `[PARTIEL]` |
| 18 | Option *« Enregistrer les pauses entre énoncés »* | Conserve ou supprime les pauses/bruits dans l'archive audio. | `[ABSENT]` |
| 19 | Définition de la langue/région du vocabulaire | Une langue par profil ; région = conventions d'orthographe et de formatage. | `[PARTIEL]` |
| 20 | Optimisation planifiée (`Paramètres administratifs`) | Ordonnancement des tâches d'amélioration. | `[ABSENT]` |

---

## 9. Thème 7 — Commandes personnalisées et Explorateur de commandes

**24 fonctionnalités**

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | `« Lancer l'Explorateur de commandes »` (Outils > Explorateur de commandes) | Parcours/recherche de **toutes** les commandes par contexte d'application. | `[PARTIEL]` Phénix : « Que puis-je dire ? » seulement |
| 2 | Boîte *« Mot filtre »* + boutons *Afficher tout / Affiner / Partielles / Ou \| / Ellipse* | Filtrage et développement de la syntaxe d'une commande (crochets = facultatif, `\|` = alternative). | `[ABSENT]` |
| 3 | Adapter une commande depuis l'Explorateur (bouton *Adapter*, file *« Adapter plus tard »*) | Améliore la reconnaissance d'une commande précise (ex. `« Corriger ça »` → « Corriger pas »). | `[DÉJÀ]` empreinte acoustique des commandes critiques |
| 4 | *Créer / Modifier / Supprimer* une commande (boutons *Script* → *Créer*) | Gestion de bout en bout. | `[PARTIEL]` |
| 5 | Commandes **AutoTexte** (`Outils > Ajouter un nouvel AutoTexte`) | Insère un bloc texte/graphique figé. | `[PARTIEL]` CAHIER Module 5 |
| 6 | Champs variables dans les AutoTexte | `[champ]`, valeur par défaut, `« Champ suivant »`/`« Champ précédent »` (Ctrl+Maj+N), `« Variable suivante »`, `« Accepter les valeurs par défaut »`, `« Effacer les séparateurs de variables »`. | `[ABSENT]` |
| 7 | Commandes **Pas-à-pas** | Étapes *Touches*, *Saisir du texte*, *Ouvrir application/document*, *Attendre*. | `[PARTIEL]` |
| 8 | **Enregistreur de macros** | Enregistre une séquence souris+touches (fenêtre flottante) ; boutons *Saisir / Jouer / Insérer / Modifier / Supprimer*. | `[PARTIEL]` |
| 9 | Fenêtre *Action de l'enregistreur de macros* | Édite une étape : type d'action, touche, coordonnées X/Y. | `[ABSENT]` |
| 10 | **Langage de script avancé (VB)** | Éditeur complet, variables `<…>`, bibliothèques de références (`.OLB/.TLB/.DLL`), Explorateur d'objets ActiveX. | `[ABSENT]` |
| 11 | Éditeur de **boîtes de dialogue utilisateur** | Zones de groupe, cases à cocher, boutons d'option, listes, images, grille. | `[ABSENT]` |
| 12 | **Commandes structurées (à états)** | Exemples XML livrés (`samplecommands`), invites de commande, changement d'état en cours de session. | `[ABSENT]` |
| 13 | Commandes **ouvertes / flexibles** (`<dictée>`) | Fin de nom de commande libre (`<<dictation>>` en contenu ; `UtilityProvider.ContextValue(n)` en script) — une seule occurrence, uniquement en fin, pause avant/après. | `[ABSENT]` |
| 14 | Listes de variables | `<1-10>`, `<DirGaucheDroite>`, création/suppression via *Insérer une liste*. | `[ABSENT]` |
| 15 | **Portée** de commande | *Globale* / *spécifique à l'application* / *spécifique à la fenêtre* + état « Reconnu dans l'état ». | `[PARTIEL]` |
| 16 | Nom de commande | 200 caractères max, pas de symboles (`* @ # $ % _`), unicité sauf fenêtre distincte ; bouton *Adapter* pour la prononciation. | `[PARTIEL]` |
| 17 | `« Créer une commande »` | Création à la voix. | `[ABSENT]` |
| 18 | Gérer les commandes personnelles | Boîte *Nouveau / Modifier / Supprimer* (voix ou clic). | `[PARTIEL]` |
| 19 | Import/Export | `.dat` et `.xml`, fusion ou écrasement, validation DTD. | `[ABSENT]` |
| 20 | Outil `mycmdsxml2dat.exe` | Conversion XML → DAT pour distribution. | `[ABSENT]` |
| 21 | `protectcmds.exe` | Verrouille le code source des commandes distribuées. | `[ABSENT]` |
| 22 | Onglet Commandes : séparateurs de variables | `[` `]` par défaut, jusqu'à 5 caractères. | `[ABSENT]` |
| 23 | Option *« Activer Automatiquement sélectionner le premier champ »* | Curseur automatique dans le 1ʳᵉ champ de formulaire. | `[ABSENT]` |
| 24 | Paramètres administratifs des commandes | Interdire création/modification aux profils restreints ; désactiver Enregistreur / Pas-à-pas / Script. | `[ABSENT]` |

---

## 10. Thème 8 — Ergonomie, Barre Dragon et aide

**18 fonctionnalités**

| # | Commande / nom | Description | État |
|---|---|---|---|
| 1 | Barre Dragon (nouvelle) + Barre Dragon classique | Deux châssis, réduction automatique, menu de personnalisation, retour possible à la classique. | `[DÉJÀ]` HUD Phénix |
| 2 | Modes de la barre + transcription affichée | Microphone 3 états, modes de reconnaissance, texte transcrit (85 → 110 car.). | `[DÉJÀ]` |
| 3 | Barre de fonctions avancées (classique) | Commandes de réécoute (avance, retour rapide). | `[ABSENT]` |
| 4 | Volet de référence (anc. Volet Dragon) | Volets repliables de commandes + conseils ; ancrage, largeur, taille de police. | `[PARTIEL]` aide « Que puis-je dire ? » |
| 5 | Didacticiel interactif | Leçons simulées : ponctuation, dictée, correction, navigation Web, clic vocal, barre, épellation, Options, éditeur de vocabulaire. | `[ABSENT]` |
| 6 | Mains libres | Contrôle micro entièrement vocal ; non supporté pour la création de profil ni le didacticiel. | `[DÉJÀ]` (mixte voix + bouton) |
| 7 | Mode tablette / mode muet | Optimisations tactiles, bascule muet. | `[DÉJÀ]` F8/F9 |
| 8 | Clavier vocal | Frappe de touches par la voix. | `[PARTIEL]` |
| 9 | Astuces (`Help/tips`) | Astuces Gmail, *scratch that*, WCIS. | `[ABSENT]` |
| 10 | Conseils utilisateurs mal voyants | `tips_for_vision_impaired_users`. | `[ABSENT]` |
| 11 | `« Basculer vers la barre Dragon »` | Navigation vocale dans les menus Dragon. | `[DÉJÀ]` |
| 12 | Options : navigation vocale entre pages | `« [nom de la page] »`, `« Cliquer sur [nom] »`, `« Aller à [nom] »` + bouton *Par défaut* par page. | `[ABSENT]` |
| 13 | 100 % hors-ligne | Aucune requête réseau en dictée. | `[DÉJÀ]` `local_files_only` — **avantage Phénix** |
| 14 | Connexion compte Nuance / abonnement | Validation de licence, synchronisation Dragon Anywhere. | `[ABSENT]` — **avantage Phénix** (open, gratuit) |
| 15 | Paramètres administratifs | Emplacements de sauvegarde/distribution, mises à jour au démarrage, verrous, planification. | `[ABSENT]` |
| 16 | Rapport d'utilisation (Options > Données > Avancé) | Journal des commandes pour le support Nuance. | `[ABSENT]` (Phénix a déjà `injection_trace.jsonl`) |
| 17 | Partage avec Dragon Anywhere | Synchronisation des mots et AutoTextes vers le mobile. | `[ABSENT]` |
| 18 | `Help` : plan de touches, changement de numéro de série | Métadonnées produit. | hors périmètre |

---

## 11. Top 14 — Fonctionnalités absentes probablement désirées

> Chaque entrée : **ce que fait Dragon** → **pourquoi c'est probablement désiré ici** → **écart Phénix**.

| # | Fonctionnalité | Justification | État |
|---|---|---|---|
| **1** | **Correction/sélection par citation complète** : `« Corriger <texte> »`, `« Sélectionner <texte> »`, plages `de X à Y`, `« Sélectionner à nouveau »`, numérotation des instances + `« Prendre tout »` | Permet de corriger *n'importe quel* mot dicté il y a des minutes, sans se souvenir de l'ordre. **C'est la fonctionnalité qui justifie à elle seule le `Shadow Buffer` + UIA du Module 1.** | `[PARTIEL]` — **priorité la plus élevée** : le cahier la promet, la couverture `UIA TextPattern` n'est pas confirmée. |
| **2** | **Correction des N segments précédents** (« N souffles ») | Déjà identifiée et **reportée** : proposition = N = mots 1…9 (table `CHOOSE_MAP`), plafond 25 (taille du `deque`), concaténation des N derniers segments → remplacement fusionné. | `[ABSENT]` — **à valider avec l'utilisateur avant implémentation.** |
| **3** | **Réécoute** : `« Rejouer ça »`, `« Rejouer à partir d'ici »`, rejeu automatique à la correction | Écouter son propre souffle *pendant* la correction double le taux de réparation, surtout en dysarthrie (entendre ce qu'on a réellement dit vs ce qu'on croit avoir dit). | `[ABSENT]` |
| **4** | **Historique de reconnaissance de session** | Relister les énoncés récents pour corriger *après coup*, même sans audio. Coût faible : `logs/session_trace.jsonl` existe déjà. | `[ABSENT]` |
| **5** | **Sélection relative `<1-20>`** (mots / caractères / lignes / paragraphes, suppressions `<2-20>`) | Indispensable pour éditer **sans citer de texte** — donc sans dépendre de l'UIA, donc fiable partout. Plafond 20, base 2 pour les effacements. | `[ABSENT]` |
| **6** | **Numérotation des occurrences + `« Prendre <n> »` / `« Prendre tout »`** | Sans elle, `« Sélectionner septembre »` n'agit que sur l'occurrence la plus proche du curseur : **erreur silencieuse** fréquente sur texte long. | `[ABSENT]` |
| **7** | **Formatage automatique riche** (dates J/M/AAAA, prix + codes ISO, unités, téléphones, seuil *nombre ≥ N en chiffres*, « 8 millions » vs `8 000 000`, abréviations de titres) | Gain de temps en rédaction courante ; **100 % déterministe et hors-ligne**, compatible avec la contrainte zéro réseau. | `[ABSENT]` |
| **8** | **Règles de formatage intelligent** (`1 – Ne jamais` / `2 – Toujours`) | Dragon apprend *de vos corrections de formatage* ; Phénix apprend de vos corrections acoustiques mais pas de vos choix de formatage. **Boucle d'apprentissage complémentaire.** | `[ABSENT]` |
| **9** | **MouseGrid (« Damier de souris ») + glisser vocal + `« Souris à gauche <1-10> »`** | Spécifié au Module 5, absent du code. *Arbitrage : l'utilisateur a déjà un pointage fluide → priorité probablement basse.* | `[PARTIEL]` |
| **10** | **Explorateur de commandes** (navigateur filtrable, par contexte d'app, aperçu de syntaxe) | « Que puis-je dire ? » donne des suggestions ; l'Explorateur permet de ***chercher*** une commande. Utile surtout pour rédiger le lexique. | `[PARTIEL]` |
| **11** | **Commandes personnalisées avec variables `<…>` et portée application/fenêtre** | AutoTexte à champs + disponibilité *Globale / Application / Fenêtre*. Prévu au Module 5 (« macros vocales ») mais pas de système de variables. | `[PARTIEL]` |
| **12** | **Recherche vocale unifiée** | `« Rechercher <mots-clés> sur Internet \| sur l'ordinateur \| dans les documents \| dans la messagerie »` + fenêtre de confirmation des termes. | `[ABSENT]` |
| **13** | **Commandes Outlook/calendrier à langage naturel** | `« Planifier une réunion avec <contact> »`, `« Créer rendez-vous pour <objet> »`. Forte valeur si pilotage messagerie à la voix ; sinon rester sur des macros dédiées. | `[ABSENT]` |
| **14** | **Navigation en mode épellation** (curseur gauche/droite, supprimer caractère) | Déjà listée **À FAIRE à l'étape 2** dans `PROMPT_REPRISE.md` ; à faire **en même temps que l'enregistrement du studio** (26 mots NATO), sinon le filet acoustique reste inopérant. | `[ABSENT]` |

### Deux absences **volontaires** à ne pas combler

- **La Boîte de dictée** — c'est précisément le défaut que Phénix est conçu pour éliminer (§1.2.2 du cahier).
- **Le mode caché** — même logique : dictée différée incompatible avec le pilier « Zéro Boîte de Dictée ».

---

## 12. Synthèse des compteurs

| Thème | Fonctionnalités inventoriées |
|---|---|
| 1. Dictée, transcription et formatage | **23** |
| 2. Correction, sélection et révision (vue d'ensemble) | **22** |
| *4. Sous-section Correction/sélection par citation (détail)* | *12 commandes + 3 tableaux de contraintes + 11 éléments d'état* |
| 3. Contrôle de Windows, souris et clavier | **50** |
| 4. Mise en forme | **19** |
| 5. Applications métier et Web | **34** |
| 6. Vocabulaire et apprentissage | **20** |
| 7. Commandes personnalisées et Explorateur | **24** |
| 8. Ergonomie, Barre Dragon et aide | **18** |
| **TOTAL inventorié** | **210 fonctionnalités** |
| Top des fonctionnalités absentes désirées | **14** (+ 2 absences volontaires) |

### Répartition des états

| État | Signification |
|---|---|
| `[DÉJÀ]` | Opérationnel dans Phénix — dictée directe, correction 9 choix, épellation NATO, casse, variantes d'accord, « C'était une commande », anti-dérive, hors-ligne, HUD. |
| `[PARTIEL]` | Prévu au cahier des charges, non ou partiellement construit — UIA de citation, MouseGrid, vocabulaire/macros, contexte applicatif, profils. |
| `[ABSENT]` | Ni dans le code ni au cahier — formatage automatique, réécoute, historique, sélection relative `<1-20>`, commandes Outlook, Explorateur complet, bureaux virtuels. |

---

*Document produit en consultation seule de l'aide locale Dragon 15 — tout est reformulé, aucun texte Nuance n'est reproduit. Sources : `Help\fra\ProfessionalIndividual` (291 `.htm` / 288 exploités) + CHM extraits `$TEMP\opencode\dragon_help\` (224 `.htm` / 66 utiles) ; 943 formes de commandes indexées.*
