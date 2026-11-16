# Corpus d'étalonnage phonémique — Lecture initiale (Étape 5)

> **Rôle** : corpus de phrases naturelles en français, lu à voix haute par l'utilisateur,
> servi à l'**alignement forcé MFA local** puis à l'**entraînement LoRA sur
> `whisper-large-v3-turbo`** (banc : ~13 000 segments/heure, RX 5700 XT / ROCm).
> Contrainte projet (13/11) : **français uniquement, aucun anglais sans accent.**
>
> **Fichier machine associé** : [`corpus/etalonnage.txt`](../corpus/etalonnage.txt)
> (une phrase par ligne, 384 lignes, sans numérotation — format directement lisible
> par MFA/Whisper).

---

## 1. Rationale du spécialiste (comment ce corpus a été conçu)

### 1.1 Naturalité d'abord
Le choix validé le 13/11 interdit les listes de phonèmes isolés : tout le corpus est
constitué de **phrases réellement parlables** de vocabulaire courant. Les contrastes
précis (paires quasi-minimales) sont **intégrés dans des phrases naturelles**, pas dans
des mots à prononcer hors contexte — seule exception assumée : le bloc §4 « contrastes »
(§6 ci-dessous) où la phrase reste naturelle mais a été choisie pour maximiser le
contraste en une seule lecture.

- **Longueurs variées** : de 3 à 13 mots (moyenne 8,1), pour alterner effort court et
  respiration longue.
- **Types variés** : déclaratives, questions (24), impératives (16), énumérations,
  phrases avec connecteurs (`d'abord`, `ensuite`, `malgré`, `quoiqu'il`…), narrations
  au passé, phrases datées/chiffrées.
- **Aucune phrase artificielle** : même les phrases à fort contraste sont grammaticales
  et plausibles à dire.

### 1.2 Couverture phonémique
Inventaire du français ciblé : **35 unités** — 12 voyelles orales (`i y e ɛ a ɑ o ɔ u ø œ ə`),
4 nasales (`ɑ̃ ɔ̃ ɛ̃ œ̃`), 3 semi-voyelles (`j ɥ w`), 16 consonnes
(`p b t d k g f v s z ʃ ʒ m n ɲ l r`). Chaque unité apparaît **plusieurs dizaines de fois**
(voir tableau §5), calculées par un **G2P français large automatisé** (règles
graphème→phonème + exceptions) — comptage **indicatif**, recontrôlé à la main sur les
phonèmes rares (`ɲ ɥ ɑ ø œ œ̃ w`) et sur les mots à prononciation irrégulière
(`sept, huit, vingt, comment, blanc, deuxièmement…`).

Les **4 nasales** sont très denses (`ɑ̃` 329, `ɔ̃` 196, `ɛ̃` 117, `œ̃` 63) parce que c'est
le couple de voyelles le plus déstabilisé par la dysarthrie (nasalité altérée,
résonance modifiée) et par les voix « nasillardes »/post-nasales.

### 1.3 Pourquoi c'est utile aux voix atypiques (et pas seulement dysarthriques)

| Distorsion typique visée | Choix dans le corpus |
|---|---|
| **Dévoicing des occlusives** (b/p, d/t, g/k souvent confondus) | paires intégrées §6, + 366 `/p/`, 159 `/b/`, 511 `/t/`, 425 `/d/`, 319 `/k/`, 84 `/g/` occurrences : le LoRA voit chaque occlusive en contexte varié, voix et non-voix proches |
| **Frottements faibles ou distordus** (f/v, s/z, ʃ/ʒ) | `/f/` 151 vs `/v/` 240, `/s/` 470 vs `/z/` 154, `/ʃ/` 115 vs `/ʒ/` 144 : chaque paire minimalement contrastive est présente (§6) |
| **Nasales altérées** (ɑ̃/ɔ̃/ɛ̃/œ̃ proches) | blocs §4 et §17-19 : phrases contenant les 3 nasales ensemble (n° 222) |
| **Voyelles centrales / repliées** (schwa accentué, œ/ø confusionnés) | `/ə/` 540 occurrences (article `le`, `je`, syllabes finales), `/ø/` 52 et `/œ/` 69 en alternance (`deux/jeudi` vs `beurre/sœur`), `/ɑ/` 8 (pâte/papa — allophone, voir note §5) |
| **Prosodie et rythme altérés** | bloc de **phrases courtes** §12 (3-7 mots) + narrations longues §13/§20 + énumérations lentes §10 : le modèle voit des rythmes très différents sans que le texte change de nature |
| **Fatigue vocale** | phrase courte = respiration possible ; lecture segmentable tous les 25-30 phrases ; aucun segment > 13 mots |
| **Variabilité inter-lecteurs** | vocabulaire neutre (pas d'argot, pas de registre soutenu marqué), structures syntaxiques standards → la signature « standard » reste apprenable |
| **Garder la voix STANDARD reconnaissable** | ~92 % des formes sont dans le haut de fréquence de Lexique383 ; pas d'obscurité lexicale ; le corpus est lisible par n'importe quel francophone → le LoRA n'apprend pas un « style » mais la distribution phonémique du français parlé |

**Équilibre entraînement/voix standard** : le corpus ne contient que du français courant —
l'adaptation à la voix atypique se fait donc *par l'audio*, pas par le texte : la voix
standard n'est jamais « tirée » vers un lexique exotique.

### 1.4 Compatibilité MFA
- **Lexique courant** : tous les mots sont du français usuel → présents dans les
  dictionnaires IPA FR de MFA (modèles `mfa-models` / WikiPron).
- **Mots rares ou propres à vérifier au dictionnaire MFA** (avec prononciation de
  repli) : **Zoé** (n° 42) → `/zɔe/` ; **Lyon** (n° 128) → `/ljɔ̃/`.
- **Mots composés** (MFA : vérifier la forme composée ou le scindage) :
  `centre-ville, dix-huit, dix-neuf, vingt-deux, vingt-cinq, quinze-trente,
  quatre-vingts, petit-déjeuner, rendez-vous, station-service, après-midi,
  aujourd'hui, grand-mère, porte-parole…` — tous lexicaux usuels.
- Recommandation : lancer `mfa validate-dictionary` (ou un G2P de contrôle) sur le
  lexique FR avant l'alignement, et consigner les éventuels OOV.

---

## 2. Dimensionnement

| Indicateur | Valeur |
|---|---|
| Nombre de phrases | **384** |
| Nombre de mots (tokens, composés scindés) | **3 092** |
| Formes lexicales uniques | 1 175 |
| Longueur moyenne | 8,1 mots (médiane 8 ; min 3, max 13) |
| Débit de lecture retenu | 150–180 mots/min (consigne) |
| **Durée estimée @160 mots/min** | **≈ 19,3 min** |
| Durée estimée @145 mots/min (lecteur fatigable) | ≈ 21,3 min |
| Cible | **~20 min** ✔ |

**Estimation** : 3 092 mots ÷ 160 mots/min = 19,3 min ; avec pauses de reprise
(respiration, fatigue) compter **20 à 22 min d'immersion micro totale**, ce qui reste
largement dans la fenêtre « adaptation ≤ 1 h (1 h 30 max) » exigée au CAHIER_DES_CHARGES
(module 3) — l'étape 5 n'étant qu'une composante de ce budget.

### 2.1 Répartition par blocs

| Blocs | Phrases | Mots |
|---|---|---|
| §1–3 maison/cuisine/studio | 1–45 (45) | 373 |
| §4–5 nature & transports | 46–76 (31) | 243 |
| §6–8 santé, famille, travail | 77–122 (46) | 359 |
| §9–11 questions, connecteurs, nombres | 123–168 (46) | 385 |
| §12–14 courtes, narrations, clusters | 169–214 (46) | 331 |
| §15–16 contrastes & quotidien | 215–252 (38) | 306 |
| §17–18 phonèmes rares + suite variée | 253–349 (97) | 809 |
| §19–20 nasales/palatales + conclusion | 350–384 (35) | 286 |
| **Total** | **384** | **3 092** |

### 2.2 Répartition entraînement / évaluation (proposition)
- **Évaluation (10 %)** : **38 phrases** — celles dont le numéro est multiple de 10
  (`n° 10, 20, … 380`), couverture homogène dans tous les blocs.
- **Entraînement** : les **346 phrases** restantes.
- Motivation : un tirage aléatoire *déterministe* et reproductible, stratifié par
  position (donc par thème), qui évite de réserver un bloc entier à l'éval.
- À retenir pour l'alignement MFA : l'ordre du fichier est l'ordre de lecture ;
  l'audio peut être découpé en sessions de 25-30 phrases avec pauses.

---

## 3. Points d'attention pour l'enregistrement
1. **Lire naturellement**, sans appuyer sur les phonèmes (pas d'exagération) : c'est la
   prononciation *habitude* qui doit être apprise.
2. **Pauses** tous les 25–30 phrases (fatigue) — l'alignement MFA gère le silence.
3. En cas de bafouillage : **recommencer la phrase**, ne pas valider (règle
   « sans apprendre » du projet).
4. Le manifest studio actuel (`corpus_01…corpus_12`, phrases 34–45 du fichier) reste
   valide : ces 12 phrases ont été **réutilisées telles quelles** dans le corpus pour
   garder la cohérence avec les prompts déjà en place.

---

## 4. Corpus numéroté (384 phrases)


**Bloc 1 — Matin & maison** (n° 1–19)

1. Le soleil se lève derrière les collines.
2. J'ouvre la fenêtre pour laisser entrer l'air frais.
3. Une tasse de café fume sur la table.
4. Je cherche mes lunettes, elles sont sur le canapé.
5. La radio annonce une belle journée ensoleillée.
6. Mon frère prend le bus vers huit heures.
7. La porte du garage grince toujours le matin.
8. Nous achetons du pain chaud chez le boulanger.
9. Les voisins rangent leur voiture devant la maison.
10. Je remplis la bouilloire pour le thé.
11. Le chat dort au milieu du couloir.
12. Ma sœur écrit un message à notre cousin.
13. Le jardinier taille les roses derrière le haut mur.
14. Un oiseau chante sur le fil électrique.
15. J'oublie parfois mon parapluie dans l'entrée.
16. Les enfants déboulent dans la cour de l'école.
17. Le réveil sonne deux fois avant de s'arrêter.
18. Je prépare un sandwich au fromage et aux tomates.
19. La lampe du bureau clignote doucement.

**Bloc 2 — Cuisine** (n° 20–33)

20. La recette demande du beurre, des œufs et un peu de sel.
21. Fais chauffer l'huile dans la grande poêle.
22. Il épluche les carottes avec un couteau bien aiguisé.
23. La soupe mijote depuis une demi-heure.
24. J'ai coupé le gâteau en huit parts égales.
25. Le fromage de chèvre est très fort au goût.
26. Nous gardons le pain rassis pour faire des miettes.
27. Une odeur de viande grillée remplit la cuisine.
28. Passe-moi le saladier et la fourchette en bois.
29. Le vinaigre rend la sauce un peu trop acide.
30. Tu peux écraser l'ail avec la petite presse.
31. La tarte aux pommes refroidit sur la grille.
32. Nous mettons du poivre et du sel sur les tomates.
33. Le boucher découpe le jambon derrière la vitrine.

**Bloc 3 — Phrases du studio existant réutilisées (`corpus_*`)** (n° 34–45)

34. Le renard brun saute près du vieux pont.
35. J'ai écrit une lettre à ma sœur ce matin.
36. Les jeunes gens chantent une chanson joyeuse.
37. Mon frère achète des cerises très sucrées.
38. Pourquoi les ouvriers réparent-ils la toiture ?
39. Une île calme au milieu de la rivière.
40. Le bûcheron débite le bois sous la pluie.
41. Ta sœur a mangé des champignons au jardin.
42. Zoé a pris le bus jaune pour aller au cirque.
43. Vingt-cinq soldats chargent leurs sacs près du port.
44. Le docteur examine gentiment le petit oiseau.
45. Écoutez la musique douce du violon ce soir.

**Bloc 4 — Nature & saisons** (n° 46–60)

46. Le vent d'automne tombe doucement sur les champs.
47. Les feuilles mortes flottent dans la rivière.
48. Un brouillard épais couvre la vallée au petit matin.
49. Les grenouilles coassent près de l'étang.
50. Une abeille butine les fleurs du jardin.
51. Les étoiles brillent clairement dans la nuit froide.
52. Le torrent gronde entre les gros rochers.
53. Les branches du saule tremblent au vent.
54. Un cerf boit au bord du lac.
55. La neige couvre les toits et les sapins.
56. Les huîtres sont fraîches sur le marché.
57. Le chêne ancien abrite une nichée d'oiseaux.
58. Une libellule vole au-dessus de l'étang.
59. Les montagnes bleues s'effacent derrière la brume.
60. Le paysage change avec chaque saison.

**Bloc 5 — Ville & transports** (n° 61–76)

61. Le métro bondé traverse la ville sous la terre.
62. Je tourne à droite au prochain carrefour.
63. Les piétons attendent le feu vert au passage.
64. Le train arrive en retard à cause du brouillard.
65. Une ambulance traverse le centre-ville en klaxonnant.
66. Nous cherchons un parking près de la gare.
67. La bicyclette roule vite sur la piste cyclable.
68. Le taxi s'arrête devant le grand hôtel.
69. J'ai perdu le ticket de mon wagon.
70. La route serpente entre les collines boisées.
71. Un camion chargé de sable roule lentement.
72. Le bus s'éloigne pendant que nous courons.
73. Le chauffeur répare le pneu à l'aire d'autoroute.
74. Nous attendons le car à l'arrêt sous la pluie.
75. Le pont de pierre enjambe la rivière rapide.
76. Les passagers descendent du train en silence.

**Bloc 6 — Santé & corps** (n° 77–92)

77. Le médecin examine ma gorge avec une petite lampe.
78. Ma voix est un peu rauque depuis hier.
79. L'orthophoniste travaille avec moi deux fois par semaine.
80. Je fais des exercices de respiration chaque matin.
81. Mon dos me fait mal après avoir porté les courses.
82. L'infirmière prend ma tension avant l'examen.
83. Il tousse souvent quand l'air est trop sec.
84. J'avale un verre d'eau avec mes médicaments.
85. Le kinésithérapeute masse l'épaule droite.
86. Mon genou craque quand je monte l'escalier.
87. La fièvre est tombée pendant la nuit.
88. Je dois reprendre mes forces après l'opération.
89. Les yeux me piquent à cause du pollen.
90. Le dentiste vérifie mes dents et mes gencives.
91. Il se sent fatigué après cette longue journée.
92. Bois assez d'eau pour garder l'énergie.

**Bloc 7 — Famille & émotions** (n° 93–107)

93. Ma grand-mère habite dans un village du sud.
94. Nous fêtons l'anniversaire de mon cousin samedi.
95. Ton ami est très gentil avec tout le monde.
96. Je suis fier du travail accompli par l'équipe.
97. Il pleure souvent devant les films tristes.
98. La surprise de ta mère était adorable.
99. Nous discutons longuement autour de la grande table.
100. Mon voisin répare toujours mes outils.
101. Tu me manques depuis ton départ à l'étranger.
102. Le bébé sourit en voyant son doudou.
103. Elle chuchote des histoires à ses enfants.
104. Nous invitons les cousins pour le réveillon.
105. Je pense souvent à nos vieilles vacances.
106. Les voisins ont organisé une fête dans la rue.
107. Ton sourire rend tout plus simple.

**Bloc 8 — Travail & ordinateur** (n° 108–122)

108. J'écris un long rapport sur mon ordinateur.
109. La batterie du portable est presque vide.
110. Clique sur l'icône pour ouvrir le fichier.
111. Le fichier est trop lourd pour être envoyé.
112. Mon collègue corrige les fautes avant l'envoi.
113. Un écran bleu s'affiche soudain sur le bureau.
114. Sauvegarde tes documents sur le disque externe.
115. L'imprimante grince et refuse d'avancer.
116. J'attends la validation du client avant de partir.
117. Le message contient une pièce jointe énorme.
118. Nous organisons une réunion mardi matin.
119. Le projet avance malgré les problèmes techniques.
120. Il corrige le code pendant toute la nuit.
121. Cette application consomme trop de mémoire vive.
122. Le tableau affiche les résultats du mois.

**Bloc 9 — Questions** (n° 123–138)

123. Comment se porte ta mère depuis son opération ?
124. Est-ce que tu viens avec nous ce soir ?
125. Où ai-je mis mes clés de voiture ?
126. Comment se nomme ce village sur la carte ?
127. As-tu besoin de quelque chose avant de dormir ?
128. Quand part le prochain train pour Lyon ?
129. Qui veut goûter ce gâteau aux fruits ?
130. Combien de temps durera la réunion de demain ?
131. Peux-tu répéter cette phrase un peu plus lentement ?
132. À quelle heure ouvre la bibliothèque ?
133. Quelqu'un a-t-il vu mon parapluie jaune ?
134. Pourrais-tu m'aider à porter ces bagages ?
135. Est-il possible de changer la date du rendez-vous ?
136. Où se trouve la prochaine station-service ?
137. Sais-tu pourquoi le magasin est fermé aujourd'hui ?
138. Veux-tu du thé ou un verre d'eau ?

**Bloc 10 — Connecteurs & énumérations** (n° 139–154)

139. D'abord nous faisons les courses, ensuite nous rentrons.
140. Il est parti parce qu'il devait prendre le train.
141. C'est difficile, mais le résultat vaut vraiment le coup.
142. Bien que la pluie tombe, nous sortons nous promener.
143. Tandis que je prépare le dîner, tu peux t'asseoir.
144. Enfin, nous terminons par un café dans le jardin.
145. Tu peux choisir le bleu, le rouge ou le vert.
146. Il y a du pain, du fromage, des fruits et du jus.
147. Premièrement, vérifie le micro. Deuxièmement, lance l'enregistrement.
148. Non seulement il est ponctuel, mais il est aussi minutieux.
149. Par conséquent, nous devons avancer plus vite.
150. En revanche, la version précédente fonctionnait parfaitement.
151. Quoiqu'il soit tard, nous continuons la discussion.
152. Malgré le froid, les enfants jouent dehors.
153. Ainsi, chacun peut lire le texte à son rythme.
154. Au contraire, cette solution semble plus simple.

**Bloc 11 — Nombres, dates & heures** (n° 155–168)

155. Nous sommes le treize novembre.
156. Il a acheté trois kilos de pommes et deux poires.
157. La réunion commence à neuf heures et demie.
158. Six ouvriers travaillent sur le chantier ce matin.
159. Le train part à quinze heures trente.
160. J'ai téléphoné quatre fois sans succès.
161. Le colis pèse vingt-deux kilos.
162. Nous habitons au numéro vingt et un de la rue des Lilas.
163. La facture s'élève à cent quatre-vingts euros.
164. Dix-neuf visiteurs sont entrés dans le musée.
165. Sept personnes attendent déjà à l'accueil.
166. Le thermomètre indique dix-huit degrés.
167. Elle est née le premier juin mille neuf cent quatre-vingt-douze.
168. Le huit du mois, nous partons en vacances.

**Bloc 12 — Phrases courtes (fatigue vocale)** (n° 169–184)

169. Le café est prêt.
170. Ferme la fenêtre, s'il te plaît.
171. Je t'écoute.
172. Ouvre le tiroir du bas.
173. Il fait très chaud aujourd'hui.
174. Répète lentement, je t'en prie.
175. Le chien dort près du radiateur.
176. Nous y sommes presque.
177. Prends ton parapluie.
178. C'est exactement ça.
179. Laisse-moi finir cette phrase.
180. Tu as raison.
181. Il est déjà tard.
182. Mets la table pour le dîner.
183. J'ai besoin d'une pause.
184. Écoute bien la consigne.

**Bloc 13 — Narrations moyennes** (n° 185–200)

185. Hier après-midi, nous avons visité le vieux château.
186. Pendant les vacances, la famille se réunit au bord de la mer.
187. Le boulanger sort du four une fournée de baguettes croustillantes.
188. Sur le marché, les marchands vendent des légumes frais et des fleurs.
189. L'orage a abattu deux arbres devant l'école cette nuit.
190. Le professeur explique la leçon avec beaucoup de patience.
191. Nous avons trouvé une vieille photo dans le grenier.
192. Le voisin a adopté deux chats et un chien.
193. Après le dîner, tout le monde s'installe devant la télévision.
194. La petite fille raconte un conte à sa poupée.
195. Un livreur dépose un colis devant la porte.
196. Nous avons marché longtemps avant de trouver un banc.
197. Le jardin est plein de rosiers et de tilleuls.
198. Le facteur distribue le courrier dans la rue tranquille.
199. Quand la cloche sonne, les élèves sortent en courant.
200. Mon oncle cuisine souvent des plats du sud.

**Bloc 14 — Consonnes complexes (robustesse atypie)** (n° 201–214)

201. L'instructeur donne des instructions très claires.
202. Le stratège construit une stratégie prudente.
203. Cette brasserie produit une bière très recherchée.
204. Les ustensiles sont rangés dans le tiroir du bas.
205. Un extraordinaire spectacle se déroule sur la place.
206. Le pharmacien prépare une ordonnance complète.
207. Nous avons observé un bref silence après l'annonce.
208. L'architecte dessine une façade sobre et élégante.
209. Le gymnase est vaste et lumineux.
210. La circulaire annonce des travaux sur la route.
211. Un fragment de verre brillait sur le trottoir.
212. Le prince prononce un discours très court.
213. Le solstice arrive avec les jours plus courts.
214. L'astronome observe une étoile filante.

**Bloc 15 — Contrastes quasi-minimaux** (n° 215–235)

215. Le bûcheron plante un pieu près du buisson.
216. Le docteur tient un dossier très tendu.
217. Le clocher gronde quand le vent se lève.
218. Le vieux forgeron forge un fer à cheval.
219. Les amis organisent un séjour au bord de la mer.
220. Le chat saute sur le canapé.
221. Le juge achète un chapeau gris.
222. Les vingt pommes du panier sont encore fraîches.
223. Cet été, nous irons près de la mer.
224. Le gros collier tombe sur le sol.
225. Tu es fou de courir dans la rue.
226. Papa mange des pâtes au beurre.
227. Chacun de nous a son propre chemin.
228. Le parfum de la rose remplit la pièce.
229. Le loup gris rôde près de la bergerie.
230. Le dindon et le lapin dorment dans la grange.
231. Quatre chats noirs guettent la souris blanche.
232. La cloche et la glace résonnent ensemble.
233. Jeanne joue du piano avec ses doigts agiles.
234. Les filles et les garçons lisent dans la cour.
235. Le gymnaste répète ses sauts sur le tapis.

**Bloc 16 — Vie sociale & quotidien** (n° 236–252)

236. Nous aimons écouter la pluie tomber sur le toit.
237. La cuisine sent bon le citron et le thym.
238. Le facteur a laissé un mot dans la boîte.
239. Ils discutent de tout et de rien sous le porche.
240. Le voisinage se retrouve chaque dimanche au parc.
241. Ma cousine prépare un exposé pour sa classe.
242. La petite montagne domine la plaine ensoleillée.
243. Le guichet ferme dans dix minutes exactement.
244. Le hibou veille sur la ferme toute la nuit.
245. Les ramiers se posent sur le toit de la grange.
246. Leurs jumelles sont sur la table du salon.
247. La brise marine rafraîchit la terrasse.
248. Nous gardons toujours une lampe de poche à portée de main.
249. Le menu du jour est écrit à la craie.
250. La machine à laver vibre fort dans la buanderie.
251. Le facteur traverse le village à toute vitesse.
252. Un silence gêné suit la chute du vase.

**Bloc 17 — Phonèmes rares : /ɲ ø œ ɥ/ + nasales** (n° 253–292)

253. Dans la campagne, les moutons broutent l'herbe au pied de la montagne.
254. Le champignon pousse près des fougères humides.
255. Un agneau gris saute dans la prairie.
256. La ligne d'horizon sépare le ciel de la mer.
257. Ce geste est simple, mais il est digne d'intérêt.
258. Le signal vert permet enfin de passer.
259. Son chignon noir ondule dans le vent.
260. Le mignon chaton dort dans le panier.
261. Il gagne toujours au jeu des cartes.
262. La montagne est couverte de sapins et de rochers.
263. Nous avons mangé des champignons à la crème.
264. La campagne est calme au crépuscule.
265. Deux amis se retrouvent chaque jeudi au café.
266. Le bleu marine va bien avec cette veste.
267. Ils jouent ensemble un jeu de société le jeudi.
268. La pieuvre se cache entre les rochers.
269. Un vœu secret accompagne chaque bougie soufflée.
270. Le meuble bas est en bois massif.
271. Il a peu de temps, mais il aide souvent.
272. Le beurre fondu nappe les légumes chauds.
273. Une fleur sauvage pousse au bord du chemin.
274. Leur maison est au bout de la ruelle.
275. La peur du vide disparaît avec l'habitude.
276. Mon cœur bat vite pendant l'examen.
277. Ta sœur prépare un gâteau aux noix.
278. Nous attendons depuis une heure près du portail.
279. La lueur de la lampe éclaire le couloir.
280. Neuf amis participent au repas du dimanche.
281. Les œufs brouillés sont prêts pour le petit-déjeuner.
282. Il fait nuit, la lune brille déjà.
283. Huit visiteurs attendent devant la billetterie.
284. Tu huiles les roues de la chaise roulante.
285. Les huîtres sont servies avec du citron.
286. Il fait nuit noire depuis vingt heures.
287. Les fruits du verger sont mûrs cette année.
288. Lui aussi prépare les bagages pour le voyage.
289. Le pain cuit dans le four du boulanger.
290. La lune se lève lentement derrière les toits.
291. Un bruit étrange sort de la chambre.
292. Elle essuie la vaisselle avec un torchon.

**Bloc 18 — Suite variée : chiffres, questions, impératifs, scènes** (n° 293–349)

293. Vingt-cinq invités sont attendus pour le dîner.
294. Cinq minutes de pause suffisent pour reprendre des forces.
295. Le train de onze heures part du quai numéro trois.
296. Il boit un verre de vin blanc avant le repas.
297. Le train direct ne s'arrête pas en route.
298. Un train rapide traverse la plaine enneigée.
299. Il a besoin de repos après une semaine difficile.
300. Prends soin de toi pendant cette période chargée.
301. Mon bras droit me fait mal depuis trois jours.
302. Quand tu as le temps, appelle-moi pour prendre des nouvelles.
303. Est-ce que tu préfères le thé vert ou le café ?
304. Pourquoi as-tu choisi cette couleur pour le mur ?
305. Qui a laissé la porte de la cuisine ouverte ?
306. Combien de courses reste-t-il à faire avant ce soir ?
307. Peux-tu me dire où se trouve le cahier de texte ?
308. Nous faisons les courses le mardi et le samedi.
309. D'abord je lis le message, ensuite je réponds.
310. Il pleut beaucoup, alors nous restons à la maison.
311. Bien qu'il soit fatigué, il finit son travail.
312. Tandis que le dîner se prépare, les enfants jouent.
313. En revanche, la matinée s'est très bien passée.
314. Malgré les retards, tous les invités sont arrivés.
315. Ainsi, nous évitons les erreurs de transcription.
316. Premièrement, vérifie la connexion. Deuxièmement, ouvre l'application.
317. Il y a quatre pommes, trois poires et deux bananes sur la table.
318. Le facteur passe vers neuf heures, jamais après midi.
319. Nous avons acheté deux kilos de farine et un sachet de sucre.
320. Ma voisine m'a prêté un parapluie et un imperméable.
321. Le mécanicien a changé les pneus et vérifié les freins.
322. Chaque matin, je lis les nouvelles en buvant mon café.
323. Après la pluie, l'air sent la terre mouillée.
324. Le spectacle a duré une heure et demie.
325. Nous avons ri beaucoup pendant ce film comique.
326. La bibliothèque municipale ferme à dix-huit heures.
327. Ferme le robinet, l'eau coule encore.
328. Ouvre le couvercle de la casserole.
329. Pose les cartes sur la table.
330. Appuie longuement sur le bouton du haut.
331. Le verre est sale, il faut le laver.
332. Mets un peu moins de sucre.
333. Écris la date en haut de la page.
334. Tourne la clé dans la serrure.
335. Le sac est lourd, prends les anses.
336. Rince le bol avant de le ranger.
337. Le garagiste répare le moteur avec une grande attention.
338. Le juge a lu le dossier pendant deux heures.
339. La caissière scanne les produits un par un.
340. Le jardinier arrose les plantes avant le lever du soleil.
341. Le professeur distribue les copies à ses élèves.
342. Nous avons perdu le reçu de la machine à café.
343. La dame au comptoir sourit aux clients.
344. Mon cousin prépare son concours pour l'été prochain.
345. Le facteur a un nouveau trajet dans le village.
346. Un pêcheur ramène sa barque sur le sable.
347. La foule s'éloigne du stade après le match.
348. Le garde surveille l'entrée du bâtiment toute la nuit.
349. Nous prenons le chemin de traverse jusqu'au pont.

**Bloc 19 — Nasales & palatales /ɲ/** (n° 350–379)

350. La compagnie a organisé un voyage dans les montagnes.
351. Il enseigne les maths dans un collège de campagne.
352. Le paysage est digne d'être photographié.
353. La ligne du bus passe devant l'hôpital.
354. Un panneau indique le signal de sortie.
355. Elle se baigne dans le lac dès le matin.
356. Le règne de ce roi dure depuis vingt ans.
357. La foule grogne contre les retards du train.
358. La Bretagne est réputée pour ses plages sauvages.
359. Le diagnostic du médecin rassure toute la famille.
360. Nous enseignons l'orthographe aux enfants avec patience.
361. Un signe de la main suffit pour les saluer.
362. Les montagnards descendent au village chaque hiver.
363. Il soigne ses plantes avec un engrais naturel.
364. Une enseigne lumineuse éclaire la rue tranquille.
365. La campagne est belle au printemps, avec les fleurs.
366. Papa prépare les pâtes pour tout le monde.
367. Tu devrais baigner le chien aujourd'hui.
368. Ce vieux pont enjambe la rivière calme.
369. La boisson est trop sucrée pour les enfants.
370. L'enseignante écrit au tableau avec de la craie.
371. Il a gagné le premier prix du concours.
372. Un mignon couple danse sur la place du village.
373. Le règlement interdit de traverser ici.
374. Nous ramassons des champignons en forêt.
375. La montagne noire domine toute la région.
376. Elle parle avec dignité devant l'assemblée.
377. Le signal sonore prévient les passagers.
378. Le compagnon du boulanger arrive à l'aube.
379. Le règne du silence suit la tempête.

**Bloc 20 — Phrases longues de conclusion** (n° 380–384)

380. Quand nous sommes arrivés, tout le monde était déjà parti.
381. Après une longue marche, nous avons installé le camp sous les arbres.
382. Le dimanche matin, le marché du centre accueille les producteurs locaux.
383. Pendant l'orage, la lumière clignotait et le vent hurlait.
384. Si tu termines tôt, tu peux venir nous rejoindre au parc.

---

## 5. Tableau de couverture phonémique

> Méthode : comptage automatique (G2P français large, règles graphème→phonème +
> listes d'exceptions ; liaison `z` gérée sur articles/pronomes) ; unités affichées =
> « n° des phrases concernées » (échantillon, `…` = suite non listée). Les valeurs
> sont **indicatives à ±10 %** (les finales muettes et le schwa varient à l'oral),
> mais l'ordre de grandeur et la présence de chaque phonème sont vérifiés.

| Phonème | Graphèmes principaux | Occurrences | Phrases concernées (n°, extrait) |
|---|---|---|---|
| `i` | `i` (vie, lit) | **445** | 272 phrases : 1, 6, 10, 11, 12, 13, 14, 15, 18, 19, 21, 22, 23, 24, 26, 27 … |
| `y` | `u` (tu, rue) | **261** | 194 phrases : 3, 4, 5, 6, 7, 8, 9, 11, 13, 14, 19, 20, 22, 23, 27, 30 … |
| `e` | `e é` (le, été) | **293** | 218 phrases : 2, 3, 4, 5, 6, 8, 10, 12, 13, 14, 15, 16, 17, 18, 21, 22 … |
| `ɛ` | `è ê e` (père, même, sec) | **452** | 271 phrases : 1, 2, 4, 5, 6, 9, 12, 13, 14, 17, 18, 20, 21, 22, 24, 25 … |
| `a` | `a` (table, mal) | **827** | 340 phrases : 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 … |
| `ɑ` | `â a` final (pâte, papa) | **8** | 4 phrases : 81, 226, 301, 366 |
| `o` | `o au eau` (beau, métro) | **135** | 116 phrases : 5, 8, 11, 13, 14, 18, 19, 21, 22, 24, 25, 29, 31, 34, 36, 39 … |
| `ɔ` | `o` fermé (porte, sol) | **187** | 144 phrases : 1, 5, 7, 11, 12, 13, 16, 17, 18, 19, 22, 23, 25, 27, 31, 32 … |
| `u` | `ou` (toujours, four) | **245** | 180 phrases : 2, 5, 7, 8, 10, 11, 12, 15, 16, 19, 22, 23, 24, 25, 26, 28 … |
| `ø` | `eu eux` (deux, jeudi) | **52** | 48 phrases : 6, 17, 23, 30, 34, 36, 47, 59, 79, 85, 89, 97, 131, 132, 138, 143 … |
| `œ` | `eu` + r/l/f, `œu` (beurre, sœur) | **69** | 64 phrases : 9, 11, 12, 20, 27, 29, 35, 39, 41, 43, 44, 50, 63, 73, 78, 108 … |
| `ə` | `e` muet (le, je, petit) | **540** | 318 phrases : 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14, 16, 17, 18, 20 … |
| `ɑ̃` | `an am en em` (dans, temps, chambre) | **329** | 208 phrases : 2, 5, 6, 8, 9, 10, 14, 15, 16, 17, 18, 19, 20, 21, 24, 27 … |
| `ɔ̃` | `on om` (monde, nombre) | **196** | 150 phrases : 4, 5, 6, 8, 9, 15, 26, 32, 33, 34, 36, 37, 40, 41, 45, 46 … |
| `ɛ̃` | `in im ain ein ien` (vin, plein, bien) | **117** | 100 phrases : 7, 8, 9, 12, 22, 26, 35, 41, 43, 48, 50, 55, 57, 62, 64, 66 … |
| `œ̃` | `un um` (un, chacun, parfum) | **63** | 60 phrases : 12, 14, 18, 20, 22, 29, 34, 48, 54, 66, 71, 78, 84, 93, 108, 113 … |
| `j` | `ill ier y` (fille, papier, yeux) | **148** | 124 phrases : 1, 5, 11, 13, 15, 22, 26, 27, 28, 31, 33, 34, 38, 39, 45, 47 … |
| `ɥ` | `u` de `ui hu` (lui, huit, huile) | **65** | 63 phrases : 6, 15, 21, 22, 23, 24, 27, 40, 51, 56, 74, 78, 87, 96, 101, 103 … |
| `w` | `oi ou` (moi, toujours) | **92** | 82 phrases : 9, 10, 11, 14, 15, 17, 28, 31, 32, 38, 40, 44, 45, 49, 51, 54 … |
| `p` | `p` | **366** | 238 phrases : 2, 4, 6, 7, 8, 10, 15, 18, 19, 20, 21, 22, 23, 24, 26, 27 … |
| `b` | `b` | **159** | 130 phrases : 3, 5, 6, 8, 10, 15, 16, 19, 20, 22, 28, 33, 34, 40, 42, 46 … |
| `t` | `t` | **511** | 297 phrases : 2, 3, 4, 6, 7, 8, 9, 10, 12, 13, 14, 15, 17, 18, 19, 20 … |
| `d` | `d` | **425** | 269 phrases : 1, 3, 5, 7, 8, 9, 11, 13, 15, 16, 17, 18, 19, 20, 21, 23 … |
| `k` | `c k qu` | **319** | 221 phrases : 1, 3, 4, 11, 12, 14, 16, 19, 22, 24, 27, 30, 33, 35, 37, 38 … |
| `ɡ` | `g gu` | **84** | 74 phrases : 7, 21, 22, 24, 25, 26, 27, 29, 31, 44, 49, 52, 65, 66, 68, 69 … |
| `f` | `f ph` | **151** | 127 phrases : 2, 3, 6, 14, 15, 16, 17, 18, 20, 21, 25, 26, 28, 31, 37, 47 … |
| `v` | `v` | **240** | 179 phrases : 1, 2, 6, 9, 17, 22, 25, 27, 29, 30, 32, 33, 34, 38, 39, 43 … |
| `s` | `s ç ss c` | **470** | 268 phrases : 1, 2, 3, 4, 5, 6, 7, 12, 14, 17, 18, 19, 20, 23, 26, 28 … |
| `z` | `z s` intervocalique + liaisons | **154** | 128 phrases : 8, 9, 12, 13, 14, 16, 20, 22, 27, 30, 36, 37, 38, 42, 44, 45 … |
| `ʃ` | `ch` | **115** | 96 phrases : 4, 8, 11, 14, 18, 21, 22, 25, 28, 33, 36, 37, 40, 41, 43, 46 … |
| `ʒ` | `j g` devant e/i | **144** | 121 phrases : 4, 5, 7, 8, 9, 10, 12, 13, 18, 23, 25, 33, 36, 41, 42, 43 … |
| `m` | `m mm` | **275** | 198 phrases : 3, 4, 6, 7, 9, 11, 12, 13, 15, 18, 19, 20, 23, 25, 26, 28 … |
| `n` | `n nn` | **241** | 183 phrases : 1, 2, 3, 4, 5, 8, 12, 13, 17, 23, 26, 27, 29, 32, 33, 34 … |
| `ɲ` | `gn` (champignon, montagne) | **50** | 47 phrases : 19, 41, 59, 72, 184, 242, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262 … |
| `l` | `l ll` | **844** | 355 phrases : 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17 … |
| `ʁ` | `r rr` | **878** | 358 phrases : 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17 … |

**Notes sur le tableau**
- **`ɑ` [a]/[ɑ]** : paires d'allophones en français moderne (pas de minimal pair
  opposable) — occurrences concentrées sur `pâte(s), papa, mal, patate` (n° 81, 226,
  301, 366). Le reste du corpus porte `[a]` (827), qui est la valeur majoritaire.
- **`œ̃` [œ̃]/[ɛ̃]** : chez la plupart des locuteurs parisiens, `un/brun/chacun` fusionne
  avec `in/plein`. Les deux notations sont conservées (le dictionnaire MFA les
  distingue) ; l'audio réduira la distinction naturellement.
- **`ə` (schwa)** : très fréquent à l'écrit (`le, je, de, petit…`), **amovible à
  l'oral** — le comptage est un plafond, pas une certitude.
- Les **semi-voyelles** `j ɥ w` sont comptées glissements à part des voyelles
  (`oi` → `w`+`a`, `ui` → `ɥ`+`i`, `ien` → `j`+`ɛ̃`).

---

## 6. Contrastes quasi-minimaux intégrés (phrases naturelles)

Chaque contraste utile est couvert **en contexte parlable** ; le tableau indique la
phrase « pivot » (les contrastes sont aussi répétés dans le reste du corpus).

| Contraste | Phrase(s) pivot (n°) | Ce qu'elle oppose |
|---|---|---|
| **/b/ – /p/** | 215 « Le **b**ûcheron p**l**ante un p**ieu** près du **b**uisson. » ; 33 | occlusive bilabiale sourde/sonore |
| **/d/ – /t/** | 216 « Le d**o**cteur **t**ient un d**o**ssier très **t**endu. » | alvéolaires sourde/sonore |
| **/g/ – /k/** | 217 « Le c**l**ocher g**r**onde quand le vent se lève. » ; 129 | vélaire sourde/sonore |
| **/v/ – /f/** | 218 « Le v**ieu**x f**o**rgeron f**o**rge un f**e**r à cheval. » ; 111 | fricative labiodentale |
| **/z/ – /s/** | 219 « L**es** am**is** o**rg**anisent un s**é**jour… » (liaison `z` + `s`) ; 42 | fricative alvéolaire |
| **/ʃ/ – /s/** | 220 « Le c**h**at s**au**te sur le canapé. » ; 232 | post-alvéolaire/alvéolaire |
| **/ʃ/ – /ʒ/** | 221 « Le j**u**ge a**ch**ète un c**h**apeau g**r**is. » | affriquées sourde/sonore |
| **/ɑ̃/ – /ɔ̃/ – /ɛ̃/** (triple) | 222 « L**es** v**in**t p**om**mes du p**an**ier s**on**t en**core** fraîches. » ; 158, 293 | les 3 nasales en une phrase |
| **/e/ – /ɛ/** | 223 « C**e**t **é**té, nous irons pr**è**s de la m**e**r. » | e fermé/ouvert |
| **/o/ – /ɔ/** | 224 « Le gr**o**s c**o**llier t**o**mbe sur le s**o**l. » | o fermé/ouvert |
| **/u/ – /y/** | 225 « T**u** es f**ou** de courir dans la r**u**e. » | postérieure/antérieure arrondie |
| **/a/ – /ɑ/** | 226 « P**a**pa m**a**nge des p**â**tes… » ; 366 | allophones [a]/[ɑ] |
| **/œ/ – /ø/** | 272 « b**eu**rre » vs 265 « d**eu**x / je**u**di » ; 277 « s**œ**ur » | eu devant consonne r/l/f vs voyelle |
| **/œ̃/** (nasale arrondie) | 227 « C**h**acun de nous… » ; 228 « parf**u**m » | `un/u` nasalisé |
| **/ɥ/** (semi-voyelle arrondie) | 283 « H**ui**te visiteurs » ; 284 « Tu h**ui**les… » ; 288 « L**ui** aussi » ; 287 « fruits » | glide antérieur (le plus difficile) |
| **/ɲ/** (`gn`) | 253-264, 350-379 (campagne, montagne, champignons, gagne…) | nasale palatale |
| **/l/ – /ʁ/** | 229 « Le l**ou**p g**r**is r**ô**de pr**è**s… » | latérale/fricative |
| **/m/ – /n/** | 99 « Nous discutons long**u**ement… » ; 323 | nasales bilabiale/alvéolaire |
| **/w/ – /ɥ/ – /j/** | 156 « t**oi**s kilos » ; 283 « h**ui**te » ; 233 « J**e**anne j**ou**e » | les 3 glides en alternance |

---

## 7. Besoins complémentaires pour le système (PAS produits ici)

Ces besoins restent couverts par d'autres étapes — ce corpus ne les traite pas :

1. **Vocabulaire personnel** de l'utilisateur (noms, adresses, projets) : import
   Lexique383 + importateur de mails/documents (étape 5bis / lexique applicatif).
2. **Chiffres et symboles oraux** : « virgule », « tiret », « pour cent », «
   deux mille vingt-six », dates complètes, heures au format long — à part du corpus
   de lecture (le corpus contient quelques nombres naturels, pas de couverture
   systématique des symboles).
3. **Commandes vocales** (protège-acoustique DTW) : `Phénix écoute`, `Corriger ça`,
   `Oups`, casse, épellation… — gérées par le studio `cmd_*`/`nato_*`, pas ici.
4. **Épellation NATO** (26 mots studio `nato_*`) — déjà couverte par ailleurs.
5. **Ponctuation par prosodie** (étape 3) : le corpus est ponctué à l'écrit pour MFA ;
   la prédiction de ponctuation par l'audio fera l'objet d'un corpus dédié.
6. **Noms propres fréquents** de l'utilisateur (personnes, lieux) : à ajouter au
   lexique de l'utilisateur, avec prononciations IPA si hors lexique MFA.
7. **Vocabulaire applicatif** (Excel, Blender, navigateur…) : import de documents.

---

## 8. Limites connues
- Le comptage phonémique est **automatique et indicatif** (±10 %) ; la vérité
  terrain sera le **dictionnaire MFA** utilisé pour l'alignement (voir §1.4).
- Le schwa n'est pas stable à l'oral : sa « couverture » réelle dépendra du lecteur.
- Aucun mot anglais (contrainte 13/11) : le corpus est intégralement français ;
  les rares anglicismes d'usage (`sandwich`, `parking`, `scanne`) sont entrés dans le
  lexique français courant et ont une entrée dans les dictionnaires FR.
- Corpus conçu pour **un** locuteur (la voix de l'utilisateur) ; il pourra servir de
  base pour d'autres voix atypiques, mais la couverture n'est pas garantie à l'identique
  pour toutes les pathologies.
