# Migration MQ V5.3 -> V8.1 NonStop

Appli Streamlit qui convertit une sortie `DISPLAY QMGR/QLOCAL/QALIAS/QREMOTE/
QMODEL/CHANNEL/PROCESS/NAMELIST ALL` capturée sur un queue manager IBM MQ
**V5.3** (HPE NonStop, série J) en trois fichiers MQSC **V8.1** prêts à
injecter avec `runmqsc <QM> < fichier.mqsc` sur la cible (série L).

Conversion 100% déterministe : pas d'appel réseau, pas de LLM, rien n'est
exécuté ni connecté à un queue manager. Upload de fichiers uniquement --
l'appli ne lit rien sur le disque serveur et n'écrit rien de persistant.

## Pourquoi ce détour par du texte

Les utilitaires IBM `exportmqm`/`importmqm` ne fonctionnent pas dans le
contexte V5.3 du parc concerné. La conversion se fait donc par
transformation textuelle des sorties `runmqsc`.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

```bash
streamlit run app.py
```

Deux modes dans la barre latérale :

- **Conversion** : upload d'une sortie V5.3, génère `01_queues.mqsc`,
  `02_channels.mqsc`, `03_qmgr_process_namelist.mqsc` et le rapport de
  conversion. Téléchargement individuel ou zip global.
- **Validation croisée** : upload de la source V5.3 *et* d'une capture
  V8.1 réelle (ex: le même QM déjà converti sur LEIA/PADME). La conversion
  est générée depuis la source puis comparée objet par objet, attribut par
  attribut, à la capture réelle -- diff à trois colonnes (V5.3 / généré /
  V8.1 réel). C'est l'outil de mise au point du catalogue.

## Architecture

```
app.py                  interface Streamlit uniquement
core/parser.py          parsing tolérant des sorties DISPLAY ... ALL
core/model.py           dataclasses MQObject / MQAttribute / résultats
core/converter.py       application des règles du catalogue
core/renderer.py        génération des trois fichiers MQSC + du rapport
core/validator.py       comparaison généré vs capture V8.1 réelle
rules/attributes.yaml   catalogue d'attributs éditable (pas de règles en dur)
tests/                  pytest + fixtures anonymisées
```

Aucune règle de conversion n'est codée en dur dans `core/` : tout passe par
`rules/attributes.yaml`.

## Format source (déduit d'une capture réelle, pas supposé)

La sortie `DISPLAY ... ALL` V5.3 sur NonStop a des particularités qui ont
toutes été observées sur une vraie capture avant d'écrire le parseur (voir
`core/parser.py` pour le détail) :

- Chaque objet commence par une ligne `AMQ84xx: Display ... details.` ; le
  type exact (QLOCAL/QALIAS/QREMOTE/QMODEL) se déduit de l'attribut
  `TYPE(...)` à l'intérieur du bloc, pas du code AMQ (qui est le même --
  `AMQ8409` -- pour les quatre).
- Les attributs sont disposés en grille deux-colonnes de largeur fixe, sans
  rapport avec un regroupement logique.
- Un attribut est soit `NOM(valeur)` soit un mot-clé nu sans parenthèses
  (`NOSHARE`, `HARDENBO`, `SYNCPT`...).
- Les valeurs vides existent sous deux formes : `NOM( )` et `NOM()`.
- Les valeurs peuvent contenir des parenthèses imbriquées
  (`CONNAME(host.example.com(1415))`) -- le tokenizer fait un comptage de
  profondeur, pas une regex plate.
- **Artefact réel observé sur la capture MT03/LEIA** : la frappe de la
  commande `DISPLAY` suivante peut être capturée entrelacée caractère par
  caractère avec la sortie encore en cours de la commande précédente
  (capture terminal asynchrone sur NonStop). Ça produit des lettres
  résiduelles collées devant `AMQ84xx:` (ex: `DAMQ8409:`) et des fragments
  de commande en plein milieu d'un bloc d'attributs (ex: `ISPLAY
  PROCESS(*) ALL`). Le parseur les détecte et les neutralise sans perdre ni
  contaminer l'objet concerné -- chaque occurrence est signalée dans
  l'onglet "Non parsé" / le rapport, jamais silencieuse.
- Une commande `DISPLAY` malformée par cet entrelacement peut carrément
  échouer côté QM (`AMQ8405: Syntax error...` suivi de `AMQ8427: Valid
  syntax...`) : ce bloc n'est pas un objet, il est capturé comme message
  d'erreur, jamais transformé en faux objet.

## Maintenir le catalogue (`rules/attributes.yaml`)

Le catalogue a été seedé à partir de deux captures réelles sur le QM MT03 :
la sortie V5.3 d'ISIS et la sortie V8.1 de LEIA (QM déjà converti --
vérité terrain). Pour chaque type d'objet :

- `runtime` : attributs générés par le QM, jamais valides en DEFINE/ALTER
  (dates, compteurs, `TYPE` implicite...).
- `renamed` : attributs dont le nom a changé entre V5.3 et V8.1 (ex:
  `TARGQ` -> `TARGET` sur QALIAS).
- `valid` / `valid_by_type` (canaux) : liste blanche des attributs
  DEFINE/ALTER valides en V8.1. **Un attribut absent de cette liste n'est
  jamais supprimé silencieusement** : il est conservé dans la sortie et
  signalé en warning dans le rapport ("attribut inconnu du catalogue").
- `review` : attributs V8.1 nouveaux sans équivalent V5.3
  (`MAXINST`/`MAXINSTC`/`SHARECNV`/`CERTLABL`/`SSLCIPH` sur SVRCONN...).
  Jamais injectés automatiquement -- documentés dans le rapport, à
  décision explicite.
- `forced` : toujours appliqué (ex: `SCMDSERV(QMGR)` sur `ALTER QMGR`).

Pour ajouter un attribut ou corriger une règle : éditer le YAML, relancer
`pytest`, puis repasser en mode Validation croisée sur un vrai couple
source/cible pour vérifier que le diff se resserre.

**Choix de conception** : un attribut caractère à valeur vide côté source
(`ATTR( )` ou `ATTR()`) n'est pas réémis dans les DEFINE/ALTER générés
(ça correspond à la valeur par défaut V8.1 dans tous les cas observés) --
ça garde le MQSC lisible. Documenté dans le rapport de chaque conversion.

## Ce que l'outil ne fait pas (checklist manuelle, dans chaque rapport)

- `altmqfls`/`dspmqfls` (fichiers Guardian associés)
- Configuration TMF
- `runnscnf` (config réseau NonStop du QM)
- `setmqaut`/`dmpmqaut` (droits OAM, une commande par file, pas de wildcard)
- `CHLAUTH`/`MCAUSER` (mapping canal -> utilisateur Guardian)
- `altmqusr`/`dspmqusr` (comptes utilisateurs MQ NonStop)
- Listener et command server comme attributs persistants du QM

## Tests

```bash
pytest tests/ -v
```

Les fixtures de test (`tests/fixtures/*.log`) sont **anonymisées** --
noms de QM/files/canaux/hosts génériques (`TEST`, `QL.APPLI.TEST`,
`distant.host.example.net`...), aucune donnée réelle du parc. Les vraies
confs (`exemple*/`, `*.mqsc`, logs `MT0*CNF.log`) sont exclues par
`.gitignore` dès le premier commit.

## Résultat de la validation croisée sur MT03 (ISIS -> LEIA réel)

Conversion générée depuis la capture ISIS (V5.3) et comparée à la capture
LEIA (V8.1, déjà converti) : 219 objets comparés (hors SYSTEM.*), 136
appariés à l'identique sur toutes leurs valeurs communes (à l'exception de
17 attributs figurant sur une poignée d'objets -- essentiellement du drift
métier réel post-migration : `MCAUSER` positionné depuis sur les
SVRCONN, quelques `DESCR` retapées sans accent, un `INITQ` vidé -- rien qui
révèle un bug de catalogue systématique). 5 files ISIS n'existent plus sur
LEIA (3 files dynamiques `AMQ.*` éphémères + 2 files métier `QL.COUMES` et
`QL.FL.ZAS.ESSAI`, à vérifier si elles devaient être reprises). Le détail
complet (objet par objet, attribut par attribut) est produit par le mode
Validation croisée de l'appli.
