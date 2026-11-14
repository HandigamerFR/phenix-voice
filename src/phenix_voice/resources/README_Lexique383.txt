Lexique383 — ressource compilée pour Phénix Voice
=================================================

Fichier : lexique_accords.tsv (compilé, voir plus bas)
Source   : Lexique 3.83 — base de données lexicales du français
           (~140 000 formes fléchies : orthographe, lemme, catégorie
           grammaticale, genre, nombre, fréquences livres/sous-titres)
Site    : http://www.lexique.org
Téléchargement : http://www.lexique.org/databases/Lexique383/Lexique383.zip
Auteurs  : Boris New, Christophe Pallier, Marc Brysbaert, Ludovic Ferrand,
           Ronald Peereman, Sophie Dufour, Christian Lachaud et contributeurs
Publications : New et al. (2004), Behavior Research Methods, Instruments, &
           Computers 36(2) ; New et al. (2001), L'Année Psychologique 101(3).

Licence  : CC BY-SA 4.0 (Creative Commons Attribution - Partage dans les Mêmes
           Conditions 4.0 International) — texte intégral dans
           LICENSE-CC-BY-SA-4.0.txt, à respecter pour toute redistribution
           du fichier compilé (attribution + partage à l'identique).

Compilation (effectuée le 2026-11-14 par tools/build_lexicon_accords.py)
------------------------------------------------------------------------
Le fichier original fait 25 Mo (34 colonnes : phonologie, syllabes,
fréquences…). Phénix Voice n'a besoin que des FAMILLES d'accord : une ligne
du fichier compilé regroupe les formes réelles partageant le même lemme, le
même tronc d'accord et le même statut accentué du suffixe, classées par
fréquence décroissante. Exemple :

    terminé	terminée	terminés	terminées

Les familles à une seule forme (ex. « café », sans variante réelle) sont
écartées : jamais de mot inventé proposé dans la boîte « Corriger ça ».

Recette pour recompiler à partir de Lexique383.tsv :

    python tools/build_lexicon_accords.py <chemin>/Lexique383.tsv

Citation recommandée si la ressource est réutilisée ailleurs :
    New, B., Pallier, C., Brysbaert, M., & Ferrand, L. (2004). Lexique 2:
    A New French Lexical Database. Behavior Research Methods, Instruments,
    & Computers, 36(2), 516-524.
