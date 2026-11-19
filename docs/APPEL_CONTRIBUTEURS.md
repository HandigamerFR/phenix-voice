# Messages de promotion — Appel à contributeurs

Brouillons prêts à publier. À adapter au canal, puis à coller manuellement
(l'ouverture des comptes/sessions sur les forums reste entre vos mains).

**Transparence (à conserver dans TOUS les messages)** : le développement a été
réalisé **à 100 % avec de l'intelligence artificielle**, sans revue de code par
l'auteur (qui ne maîtrise pas Python) ; résultats satisfaisants mais le projet
est estimé à **moins de 25 % terminé** ; l'auteur cherche des collaborateurs
pour **auditer, architecturer et faire avancer le projet plus efficacement**.

---

## 1. Tech for Good (FR)

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
> (OpenCode), **sans revue de code de ma part** — je ne maîtrise pas Python.
> Les résultats sont satisfaisants sur le plan fonctionnel (testé en conditions
> réelles), mais je l'estime à **moins de 25 % terminé**, et il a besoin d'un
> vrai travail d'**audit, d'architecture et d'optimisation** que je ne peux pas
> faire seul.
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
100% with AI, looking for reviewers & co-developers

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
> coding tool), with **no human code review** — I don't program Python myself.
> It works, but I estimate it's **less than 25% done**, and it needs real
> architecture and audit work. I'm looking for **reviewers and 2-3 regular
> contributors** to help make it better and faster. CONTRIBUTING.md is ready,
> good-first issues are labeled. Even small PRs (tests, dead code cleanup)
> help a lot. Feedback and testers are equally welcome.
>
> The app itself is 100% offline by design: no audio ever leaves the machine.

---

## 3. Forum FR technique (Developpez.com, LinuxFR, Clubic commentaires…)

**Titre** : [Projet] Phénix Voice — dictée vocale locale Windows pour voix
dysarthriques (Python, open source, cherche contributeurs)

**Corps** : réutiliser le texte Tech for Good (§1), en ajoutant :

> Détails techniques : Whisper Large-v3-Turbo converti ONNX (fp16),
> DirectML pour le GPU, VAD Silero, arbitre de plausibilité contextuelle,
> pipeline 4 étages (audio → STT → post-traitement → injection SendInput).
> Architecture détaillée dans docs/ARCHITECTURE.md du dépôt.
>
> Développé à 100 % par IA sans revue de code humaine ; moins de 25 % du
> travail est estimé terminé (audit, architecture, optimisations restent à
> faire) — les issues ouvertes listent les premiers chantiers.

---

## 4. Message court (pour un premier post / réponse à un fil)

> Je développe Phénix Voice, dictée vocale 100 % locale pour voix
> dysarthriques (GitHub : HandigamerFR/phenix-voice, GPL-3.0). Projet écrit
> intégralement par IA sans revue de code de ma part, estimé à moins de 25 %
> terminé — je cherche des co-développeurs Python pour auditer et
> architecturer. CONTRIBUTING.md prêt, issues « bonne première contribution »
> ouvertes. Testeurs aussi bienvenus !

---

## Checklist avant publication

- [ ] Dépôt GitHub rendu **public** (actuellement privé !)
- [ ] README relu (il est à jour depuis le commit d'ouverture)
- [ ] Issues créées à partir de l'audit (étape 2)
- [ ] Compteurs : tests verts, dernier commit propre
- [ ] Ne jamais publier : `user_data/`, `logs/`, chemins locaux, nom complet
