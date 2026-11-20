# Messages de promotion — Appel à contributeurs

Brouillons prêts à publier. À adapter au canal, puis à coller manuellement
(l'ouverture des comptes/sessions sur les forums reste entre vos mains).

**Transparence (à conserver dans TOUS les messages)** : le développement a été
réalisé **à 100 % avec de l'intelligence artificielle** ; l'auteur **ne
programme pas en Python aujourd'hui** mais a été **formé au développement il y
a une dizaine d'années**, ce qui lui a permis de **superviser** le projet
(cadrage, architecture, validation en conditions réelles) sans écrire le code
lui-même. Résultats satisfaisants mais projet estimé à **moins de 25 %
terminé** ; l'auteur cherche des collaborateurs pour **auditer, architecturer
et faire avancer le projet plus efficacement**.

---

## 1. Message FR principal (base pour Developpez.com, LinuxFR…)

**Titre** : Phénix Voice — reconnaissance vocale 100 % locale pour les voix
dysarthriques : cherche co-développeurs Python

**Corps** :

> Bonjour,
>
> Je développe **Phénix Voice**, une reconnaissance vocale et commande de
> Windows **100 % locale** (aucune donnée ne quitte la machine), pensée
> spécifiquement pour les personnes **dysarthriques ou aux voix atypiques** —
> un public que les solutions du marché (Dragon, dictées cloud) maltraitent.
>
> Ce qui marche aujourd'hui :
> - dictée directe dans toutes les fenêtres Windows (zéro boîte de dictée) ;
> - commandes vocales protégées par empreinte acoustique (infaillibles même
>   avec une voix fatiguée) ;
> - mode épellation (alphabet OTAN) pour ce que la voix ne passe pas ;
> - **100 % hors ligne**, GPU AMD/Intel/NVIDIA via ONNX/DirectML (pas de
>   carte NVIDIA obligatoire, pas de cloud) ;
> - fine-tuning local du modèle avec la voix de l'utilisateur (LoRA).
>
> **Transparence totale** : ce projet a été développé **à 100 % avec de l'IA**
> (OpenCode). Je ne programme pas en Python aujourd'hui, mais j'ai été **formé
> au développement il y a une dizaine d'années** : cette base m'a permis de
> **superviser** le projet — cadrer l'architecture, suivre la logique, valider
> le comportement en conditions réelles — sans écrire le code moi-même.
> Les résultats sont satisfaisants sur le plan fonctionnel, mais je l'estime à
> **moins de 25 % terminé**, et il a besoin d'un vrai travail d'**audit,
> d'architecture et d'optimisation** que je ne peux pas faire seul.
>
> C'est pourquoi je cherche **2-3 co-développeurs Python** : auditer le code,
> reprendre l'architecture là où c'est nécessaire, et faire avancer le projet
> de manière plus efficace. Même un coup de main ponctuel sur un correctif ou
> un test est utile. Le guide du contributeur est prêt (CONTRIBUTING.md) et
> les issues « bonne première contribution » sont étiquetées.
>
> Le code est en Python, ~160 tests unitaires, licence GPL-3.0 :
> https://github.com/HandigamerFR/phenix-voice
>
> Prochaine étape prévue : installeur Windows simple pour les utilisateurs
> finaux non techniques.
>
> Toute remarque, idée ou test en conditions réelles est aussi la bienvenue !

---

## 2. Reddit r/opensource (EN, à traduire ou version FR selon le sub)

**Title**: Offline speech recognition built for dysarthric voices — developed
100% with AI supervision, looking for reviewers & co-developers

**Body**:

> Hi all,
>
> I've been building **Phénix Voice** ([GitHub](https://github.com/HandigamerFR/phenix-voice)),
> a fully local (100% offline) speech-to-text and Windows control app designed
> for **dysarthric and atypical voices** — people whom commercial tools
> (cloud dictation, Dragon) fail badly.
>
> What works today: direct dictation into any Windows app (no dictation box),
> acoustic-fingerprint-protected voice commands (they stay reliable even when
> the voice is tired), NATO spelling mode, local LoRA fine-tuning on the
> user's own voice, and ONNX/DirectML inference so it runs on AMD/Intel GPUs
> too — no NVIDIA required. ~160 unit tests, GPL-3.0, Python.
>
> **Honest disclaimer:** the whole project was **written by AI** (an agentic
> coding tool). I don't program Python myself today, but I trained as a
> developer about ten years ago — that background let me **supervise** the
> project (shape the architecture, follow the logic, validate behavior in
> real-world use) rather than write the code line by line. It works, but I
> estimate it's **less than 25% done**, and it needs real architecture and
> audit work. I'm looking for **reviewers and 2-3 regular contributors** to
> help make it better and faster. CONTRIBUTING.md is ready,
> good-first issues are labeled. Even small PRs (tests, dead code cleanup)
> help a lot. Feedback and testers are equally welcome.
>
> The app itself is 100% offline by design: no audio ever leaves the machine.

---

## 3. Forum FR technique (Developpez.com, LinuxFR, Clubic commentaires…)

**Titre** : [Projet] Phénix Voice — dictée vocale locale Windows pour voix
dysarthriques (Python, open source, cherche contributeurs)

**Corps** : réutiliser le texte principal (§1), en ajoutant :

> Détails techniques : Whisper Large-v3-Turbo converti ONNX (fp16),
> DirectML pour le GPU, VAD Silero, arbitre de plausibilité contextuelle,
> pipeline 4 étages (audio → STT → post-traitement → injection SendInput).
> Architecture détaillée dans docs/ARCHITECTURE.md du dépôt.
>
> Développé à 100 % par IA, supervisé par un auteur formé au développement
> il y a une dizaine d'années ; moins de 25 % du
> travail est estimé terminé (audit, architecture, optimisations restent à
> faire) — les issues ouvertes listent les premiers chantiers.

---

## 4. Message court (pour un premier post / réponse à un fil)

> Je développe Phénix Voice, dictée vocale 100 % locale pour voix
> dysarthriques (GitHub : HandigamerFR/phenix-voice, GPL-3.0). Projet écrit
> intégralement par IA et supervisé par moi, formé au développement il y a une
> dizaine d'années (je ne code plus en Python) ; estimé à moins de 25 % terminé
> — je cherche des co-développeurs Python pour auditer et architecturer.
> CONTRIBUTING.md prêt, issues « bonne première contribution » ouvertes.
> Testeurs aussi bienvenus !

---

## Checklist avant publication

- [x] Dépôt GitHub rendu **public** (fait le 19/11)
- [x] README relu (mis à jour : statut, transparence, roadmap)
- [x] Issues créées à partir de l'audit (18 issues, 19/11)
- [x] Compteurs : tests verts (164 passed, 1 échec préexistant hors sujet), dernier commit propre
- [ ] **Developpez.com** : premier canal choisi (compte réactivé par l'utilisateur le 20/11) — message §1/§3, publication **uniquement après feu vert de l'utilisateur**
- [ ] Puis Reddit (§2, compte Google existant) et autres canaux
- [ ] Ne jamais publier : `user_data/`, `logs/`, chemins locaux, nom complet

> Note : « Tech for Good » (§1) n'a **pas de forum de publication** (c'est un
> sommet annuel + un magazine UK) — le texte §1 sert de base pour les canaux
> FR réellement ouverts (Developpez, LinuxFR…).
