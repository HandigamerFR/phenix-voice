# Cahier des Charges Fonctionnel — Phénix Voice

## 1. Contexte Utilisateur & Objectifs Généraux

### 1.1 Profil du créateur et premier utilisateur
- Utilisateur quotidien intensif de *Dragon NaturallySpeaking Professional Individual* (utilisé aussi bien pour rédiger que pour piloter le PC et interagir avec des agents de développement IA).
- En situation de handicap moteur avec une **diction légèrement dysarthrique**.
- Dispose d'un **périphérique de pointage/clic fluide** (permettant une ergonomie hybride Voix + Souris très efficace) et utilise un contrôle du micro mixte (commandes vocales + bouton physique).

### 1.2 Limites de Dragon à résoudre
1. **Dérive du profil vocal et rigidité des commandes de correction** : Avec le temps ou la fatigue, le profil se dégrade. Si une commande de correction elle-même (*« Corriger ça »*) n'est plus reconnue à cause de la dérive, l'utilisateur se retrouve bloqué. De plus, lorsqu'on bafouille et qu'on corrige, Dragon intègre parfois cette erreur dans le profil acoustique.
2. **La « Boîte de dictée » intrusive** : Dès qu'une application moderne (Electron, OpenCode, navigateur, terminal) ne supporte pas le vieux mécanisme de contrôle de texte de Dragon, celui-ci ouvre une boîte de dictée intermédiaire pénible.
3. **Obsolescence des outils d'apprentissage du vocabulaire** : Impossible de connecter les anciennes versions de Dragon aux messageries web modernes pour analyser les e-mails envoyés.
4. **Coût de licence prohibitif** : Phénix Voice a vocation à être partageable et ouvert à d'autres personnes (en situation de handicap ou valides) sur des machines moyennes actuelles.

---

## 2. Spécifications par Module

### Module 1 : Dictée Universelle (« Zéro Boîte de Dictée »)
- **Écriture directe universelle** : Capacité d'écrire dans 100 % des fenêtres Windows sans jamais imposer de boîte de dictée intermédiaire.
- **Tampon mémoire synchronisé (*Shadow Buffer*) & Correction sur Texte Long** :
  - Le logiciel conserve en mémoire vive l'historique multi-paragraphes des phrases dictées, la position relative du curseur et les extraits audio correspondants à chaque segment.
  - Pour permettre **la sélection et la correction dans des textes longs** (et pas uniquement sur le tout dernier souffle dicté), Phénix Voice combinera le *Shadow Buffer* avec la lecture directe du champ texte via *Windows UI Automation (`TextPattern` / `ValuePattern`)* :
    - L'utilisateur pourra dire *« Sélectionner [mot/expression] »* ou *« Corriger [mot/expression] »* sur n'importe quel mot d'un long paragraphe (avec numérotation des occurrences si le mot apparaît plusieurs fois à l'écran, comme dans Dragon).
    - Le logiciel retrouvera l'extrait audio correspondant dans l'historique de session afin de permettre *« Corriger & Apprendre »* même sur une phrase dictée plusieurs minutes plus tôt.
- **Politique 100 % Hors-Ligne & Mise à jour sécurisée des modèles** :
  - Aucune requête réseau n'est jamais émise pendant la dictée ni au démarrage normal du logiciel.
  - La vérification ou la mise à jour d'un modèle IA depuis Internet ne peut se faire que sur action explicite de l'utilisateur dans *Phénix Studio*, précédée d'un **avertissement clair** et d'une sauvegarde de secours de l'ancien modèle pour garantir qu'une mise à jour ne puisse jamais casser l'application.
- **Affichage par souffle / micro-pause** :
  - Détection d'activité vocale (*VAD*) ultra-rapide : dès qu'une micro-pause (300 à 500 ms configurable) est détectée, le segment est transcrit et écrit.
- **Ponctuation et mise en forme hybrides** :
  - Reconnaissance des commandes de ponctuation dictées (*« point »*, *« virgule »*, *« point d'interrogation »*, *« à la ligne »*, *« nouveau paragraphe »*, *« ouvrez les guillemets »*...).
  - Ponctuation et majuscules automatiques intelligentes lorsqu'elles ne sont pas dictées explicitement.
- **Contrôle du micro mixte** :
  - Bascule Actif / Veille / Coupé via un bouton ou raccourci clavier physique.
  - Bascule Actif / Veille à la voix (*« Écoute »* / *« Au repos »*, mots-clés personnalisables).

### Module 2 : Correction Intelligente & Protection Anti-Dérive
- **Commandes de correction personnalisables et protégées** :
  - L'utilisateur peut redéfinir le libellé de toutes les commandes de correction (*« Corriger ça »*, *« Sélectionner [X] »*, *« Choisir 1/2/3 »*, *« Effacer ça »*...).
  - Chaque commande système critique peut être associée à une **empreinte acoustique enregistrée** : le logiciel compare directement le son prononcé à l'enregistrement de référence de l'utilisateur, garantissant que la commande fonctionne même si le moteur de transcription général se trompe.
- **Interface de correction hybride (Voix + Clic souris fluide)** :
  - Fenêtre ou mini-barre flottante discrète près du curseur (qui **ne vole jamais le focus clavier** de la fenêtre cible).
  - Affiche les $N$ meilleures alternatives phonétiques et contextuelles numérotées (sélectionnables à la voix par *« Choisir 1, 2... »* ou d'un simple clic de souris).
  - Alphabet d'épellation personnalisable (possibilité de choisir des mots-clés faciles à prononcer pour chaque lettre).
- **Séparation stricte « Erreur du logiciel » vs « Bafouillage de l'utilisateur »** :
  - **Action A — Corriger & Apprendre** : Utilisée quand l'utilisateur a prononcé le mot avec sa diction habituelle mais que le logiciel a mal compris. Le texte est corrigé ET le couple `(Audio, Texte corrigé)` est conservé dans la base d'apprentissage.
  - **Action B — Corriger SANS apprendre (mode « Oups / J'ai fourché »)** : Déclenchable par une commande vocale dédiée ou un bouton dédié dans la barre de correction. Utilisée quand l'utilisateur a bégayé, toussé ou mal prononcé accidentellement. Le texte est corrigé à l'écran, mais **l'audio est immédiatement écarté** pour ne pas corrompre le profil vocal.
- **Points de restauration du profil (*Snapshots*)** :
  - Sauvegarde historique des états du profil vocal (automatique et manuelle) permettant de revenir en arrière si la qualité de reconnaissance baisse après une période d'utilisation.

### Module 3 : Adaptation à la Dysarthrie & Apprentissage Souple
- **Studio d'étalonnage guidé** :
  - Sessions d'entraînement proposant de prononcer plusieurs fois une liste de phonèmes, syllabes, mots fréquents ou phrases types.
  - À chaque prononciation, demande de confirmation : *« Avez-vous fait une erreur / bafouillé pendant cette prononciation ? (Oui / Non) »*.
  - Agrégation et modélisation des prononciations validées pour construire l'empreinte vocale de l'utilisateur.
- **Règles déterministes « Si je dis A, écris B »** :
  - Dictionnaire d'équivalences forcées : si le moteur acoustique transcrit systématiquement le mot ou phonème $A$ lorsque l'utilisateur veut dire $B$, l'utilisateur peut créer en 1 clic une règle prioritaire $A \rightarrow B$ (globale, en début/fin de phrase, ou entourée de certains mots).
- **Amélioration continue par consolidation locale (*Fine-Tuning LoRA*)** :
  - Entraînement périodique d'une couche d'adaptation légère (*LoRA*) sur les échantillons validés du Studio d'étalonnage et des corrections quotidiennes (Action A).
  - **Objectif chiffré (validé 16/11, à tenir dans le manuel)** : après une **lecture/corpus d'environ 20 minutes**, le système est **adapté au mieux possible** à la voix de l'utilisateur en **1 heure maximum de calcul en tâche de fond** (l'ordinateur peut être laissé en marche) — soit ~15 min de dictée + MFA + quelques minutes d'entraînement LoRA (débit mesuré ~13 000 segments/heure, config bf16 + batch 8, JOURNAL session 13 §7bis) avec de la marge.
  - **Phase 2 — adaptation au fil de l'eau** (après validation de l'entraînement initial) : consommation continue des échantillons déjà collectés (`user_data/corrections_learned/`, Action A) pour réentraîner/actualiser l'adaptateur LoRA périodiquement (ex. fin de session ou après N nouvelles corrections), avec les snapshots existants comme garde-fous anti-dérive. La **collecte** est déjà en place dans le code ; c'est la **boucle d'entraînement** qui reste à écrire.
- **Gestion de profils d'état (Fatigue vocale)** :
  - Possibilité de gérer plusieurs sous-profils acoustiques (ex. *Voix reposée* vs *Voix fatiguée*) pour s'adapter aux variations de diction en cours de journée (utile pour le créateur ou pour d'autres utilisateurs ayant une forte fatigabilité).

### Module 4 : Vocabulaire Moderne & Contextuel
- **Gestionnaire de vocabulaire personnel** :
  - Ajout/édition/suppression de mots, noms propres, termes techniques, sigles, avec forme écrite et prononciation enregistrée.
- **Analyse moderne des documents et e-mails existants** :
  - Importation de fichiers texte/Word/Markdown/PDF locaux.
  - Importation moderne des e-mails envoyés (via fichiers d'export standards `.mbox` / `.eml`, connexion IMAP/OAuth à jour, ou zone de collage rapide) pour extraire automatiquement le vocabulaire personnel et les tournures de phrases fréquentes.
- **Adaptation selon l'application active** :
  - Détection du logiciel au premier plan (navigateur, éditeur de texte, OpenCode/terminal, messagerie) pour activer le vocabulaire et les commandes propres à ce contexte.

### Module 5 : Contrôle de Windows, Souris & Macros
- **Clics et actions souris à la voix** : Clic gauche, clic droit, double-clic, clic milieu, maintenir/relâcher, défilement molette haut/bas.
- **Déplacement souris à la voix (pour l'ouverture à tous les handicaps moteurs)** :
  - Grille vocale numérotée (*MouseGrid*) et surbrillance numérotée des boutons/liens cliquables de la fenêtre active.
- **Navigation système & fenêtres** : Basculer entre les fenêtres (`Alt+Tab`), fermer, réduire, maximiser, copier/coller/couper/annuler.
- **Macros vocales personnalisées** :
  - Associer une commande vocale personnalisée à l'insertion d'un bloc de texte (signature, prompt type, courrier) ou à une séquence d'actions (raccourcis clavier, lancement de programme, pause).
