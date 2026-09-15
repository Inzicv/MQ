# Contexte projet — IBM MQ V8.1 sur HPE NonStop


## 1. Qui et quoi

- Céline, administratrice système / ingénieure sur parc HPE NonStop (Exploit Tandem, Capgemini CIS).
- Périmètre : migration **IBM MQ V5.3 → V8.1** sur le parc NonStop.
- Autonomie totale de décision sur **tous les queue managers** et tout le périmètre de migration. Aucune validation hiérarchique à demander, aucune couche de gouvernance à ajouter.

---

## 2. Le parc

| Machine | Série | Rôle | Statut |
|---|---|---|---|
| ATLAS | J (NS2300) | Production actuelle | source |
| ISIS | J (NS2300) | Dev + standby actuel | source / référence V5.3 |
| PADME | L (NS5X5-2L) | Future production | cible |
| LEIA | L (NS5X5-2L) | Futur dev + standby | cible active |

- ISIS et LEIA portent : **MT01, MT03, MT05**
- ATLAS (et PADME à terme) portent : **MT02, MT04**
- ISIS = référence V5.3, LEIA = cible V8.1. Tous les audits d'écart se font ISIS → LEIA.

---

## 3. Versions et arborescences

**V5.3 (ancien, ISIS/ATLAS)**
- Install Guardian : `$DEVT03.ZMQS`
- Architecture Pathway : `MQS-TCPLIS00`, `MQS-CMDSERV00`, démarrage par OBEY TACL + PATHCOM
- Statut Guardian via `$SYSEXP.ZWMQBIN.MQCHSVR` (invalide en V8.1, ne plus l'utiliser)

**V8.1 (nouveau, LEIA/PADME)**
- Install Guardian : `$DEVT03.MQV8`
- OSS : `/home/ibm/mqv8/opt/mqm` et `/home/ibm/mqv8/var/mqm`
- Logs QM : `/home/ibm/mqv8/var/mqm/qmgrs/<QM>/errors/AMQERR01.LOG`
- FDC système : `/home/ibm/mqv8/var/mqm/errors/`
- Profil à sourcer : `. <OSS_dir>/var/mqm/mqprofile`
- Compte admin : `MQM.ADMIN` (254,255)

**Point architectural clé** : la V5.3 et la V8.1 ne sont pas compatibles en démarrage. Ce n'est pas un simple changement de chemin.
- `STRMQM` est absent du subvolume Guardian V8.1 (il n'y a que `CRTMQM`, `DLTMQM`, `DSPMQ`, `DSPMQVER`, `ENDMQM`, `RUNMQSC`), mais `strmqm` existe bien en OSS.
- Listener et command server deviennent des attributs persistants du QM : `CONTROL(QMGR)`, `SCMDSERV(QMGR)`.

---

## 4. Modèle de sécurité déployé

- Principal applicatif : **`appmqm`** (groupe APP)
- Chaîne : `CHLAUTH` → `MCAUSER` → droits OAM via `setmqaut`
- Canal client type : `CH.SVRCONN.SWIP`
- Test client : `export MQSERVER='CH.SVRCONN.SWIP/TCP/LEIA(1414)'` puis `amqsputc`
- Déployé sur **MT01 et MT03**. MT05 est entré dans le périmètre mais n'a pas eu le chantier sécurité complet.
- `setmqaut` ne supporte pas les wildcards sur `-n` : une commande par file.

---

## 5. Outils utilisés

**Guardian / TACL** : TACL, TEDIT, FUP, PATHCOM, SPOOLCOM, SCF, BATCHCOM, TFINDCAR, TCHANCAR, EDIT, EMSDIST
**OSS** : OSH / ksh
**MQ V8.1** : `strmqm`, `endmqm`, `crtmqm`, `dspmq`, `runmqsc`, `runmqlsr`, `setmqaut`, `dmpmqaut`, `altmqusr`, `dspmqusr`, `altmqfls`, `dspmqfls`, `runnscnf`, `bcsamp`

**Skills disponibles** : `mq-nonstop-v81` (config et diagnostic MQ approfondi), `admin-nonstop-jl` (exploitation courante du parc)

**Manuel de référence** : IBM MQ for HPE NonStop V8.1 (`hpnss81.pdf`)
