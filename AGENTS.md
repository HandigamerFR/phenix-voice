# Instructions Agent (OpenCode) — Phénix Voice

Ce dépôt contient **Phénix Voice (`phenix-voice`)**, un système de reconnaissance vocale adaptatif et de contrôle de Windows pensé pour les voix dysarthriques et atypiques.

## Lecture obligatoire en début de session
1. Lisez **immédiatement** [`PROMPT_REPRISE.md`](./PROMPT_REPRISE.md) pour connaître le profil de l'utilisateur, les contraintes matérielles (**GPU AMD Radeon RX 5700 XT — pas de CUDA, utiliser Vulkan / DirectML / ONNX**), l'état d'avancement exact et la tâche en cours.
2. Au besoin, consultez [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md), [`docs/CAHIER_DES_CHARGES.md`](./docs/CAHIER_DES_CHARGES.md) et la dernière entrée de [`JOURNAL_DE_BORD.md`](./JOURNAL_DE_BORD.md).

## Ergonomie de communication avec l'utilisateur
- L'utilisateur dicte ses messages par reconnaissance vocale et dispose d'un pointage/clic souris fluide.
- Privilégiez l'outil `question` (choix multiples cliquables) lorsque plusieurs choix de conception ou de validation se présentent, afin de lui éviter de longues dictées.

## Règle de suivi en fin de session / jalon
À chaque étape importante terminée ou en fin de session :
1. Ajoutez une entrée chronologique détaillée dans [`JOURNAL_DE_BORD.md`](./JOURNAL_DE_BORD.md).
2. Mettez à jour la section **"4. État d'Avancement Actuel & Prochaine Tâche Immédiate"** dans [`PROMPT_REPRISE.md`](./PROMPT_REPRISE.md) (qui doit rester concis).
3. Commitez et poussez les changements sur le dépôt GitHub `phenix-voice`.
