# Contribuer à Phénix Voice

Merci de votre intérêt ! **Phénix Voice** est une reconnaissance vocale 100 % locale
pensée pour les voix dysarthriques et atypiques. Le projet recherche des
contributeurs réguliers : le développement est trop important pour une seule
personne, et chaque coup de main est bienvenu.

## Code de conduite

Soyez respectueux et bienveillant. L'utilisateur final du logiciel a une
contrainte particulière (dictée par la voix, fatigue, motricité réduite) :
toute contribution doit garder cet usage au centre.

## Avant de commencer

1. **Cherchez une issue ouverte** (étiquettes `bonne-premiere-contribution`,
   `bug`, `optimisation`). Si vous avez une idée nouvelle, ouvrez une issue
   avant de coder pour éviter un travail inutile.
2. **Préférez les petites PR** : un correctif ciblé se revue bien plus vite
   qu'une refonte de 2 000 lignes.

## Mise en place

Prérequis : **Windows 10/11**, **Python 3.11 ou 3.12** (pas de CUDA nécessaire —
le projet tourne en DirectML/ONNX, compatible AMD/Intel/NVIDIA).

```powershell
git clone https://github.com/HandigamerFR/phenix-voice.git
cd phenix-voice
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Lancer l'application :

```powershell
.\Lancer_Phenix_Voice.bat
```

> **Remarque** : les modèles ONNX et les adaptateurs LoRA ne sont pas inclus dans
> le dépôt (trop lourds). Voir [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
> pour les télécharger. Les tests unitaires, eux, tournent sans modèle.

## Tests

**Toute PR doit passer la suite de tests existante** (environ 160 tests) :

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m pytest -q
```

Ajoutez un test reproduisant le bug corrigé ou la fonction ajoutée.
Les tests qui dépendent d'échantillons d'étalonnage présents uniquement sur la
machine de l'auteur se sautent automatiquement ailleurs.

## Convention de code

- **Langue** : commentaires, docstrings et noms de symboles **en français**
  (choix de design assumé du projet).
- **Commits** : messages en **ASCII** (pas d'accents ni de caractères
  spéciaux), à l'impératif, avec un corps expliquant le *pourquoi*.
  Exemple : `fix: garde-fou DTW - template doit etre une commande Phenix`.
- **Fichiers** : encodage UTF-8.
- **Zéro réseau** : le logiciel doit fonctionner 100 % hors ligne. Aucune
  dépendance ni télémétrie ne doit être ajoutée.
- Suivez le style du fichier que vous modifiez (docstrings françaises,
  type hints).

## Architecture (rappel court)

Pipeline en 4 étages : `audio/` (capture + VAD) → `stt/engine.py`
(Whisper ONNX) → `postprocess/` (ponctuation, arbitre de plausibilité,
commandes) → `os_control/` (injection `SendInput`, raccourcis).
Le détail est dans [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md), et
l'état d'avancement dans [`JOURNAL_DE_BORD.md`](./JOURNAL_DE_BORD.md).

## Revue de code

Chaque PR est relue par l'auteur. Les retours portent sur la clarté, les tests
et le respect des contraintes (hors ligne, voix atypiques). Soyez prêt à
iterer : ce n'est pas un jugement sur vous, c'est le fonctionnement normal.

## Licence

En contribuant, vous acceptez que vos contributions soient publiées sous la
**licence GPL-3.0-only** du projet (voir [`LICENSE`](./LICENSE)).

⚠️ **Ressources tierces** : `src/phenix_voice/resources/lexique_accords.tsv`
est dérivé du **Lexique 383**, distribué sous licence **CC BY-SA 4.0**
(voir `src/phenix_voice/resources/LICENSE-CC-BY-SA-4.0.txt`). Toute copie ou
dérivé doit respecter cette licence.
