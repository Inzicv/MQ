"""Parseur tolérant de sorties `DISPLAY ... ALL` runmqsc V5.3 sur HPE NonStop.

Format déduit d'une capture réelle (ISIS/MT03, V5.3) :

- Chaque objet commence par une ligne message `AMQ8409: Display Queue details.`
  (le code varie selon le type : 8408=QMGR, 8409=Queue, 8414=Channel,
  8407=Process, 8550=Namelist). Les autres codes AMQ (ex: 8405/8427, erreur
  de syntaxe) ne décrivent pas un objet et sont capturés comme "issues".
- Les attributs de l'objet sont disposés en grille deux-colonnes de largeur
  fixe, sans rapport avec un regroupement logique : une valeur longue peut
  occuper toute la largeur de la ligne, un attribut peut être seul sur sa
  ligne, deux attributs peuvent se suivre sur la même ligne.
- Un attribut est soit `NOM(valeur)` soit un mot-clé nu sans parenthèses
  (ex: `NOSHARE`, `HARDENBO`, `SYNCPT`) -- un "flag" MQSC.
- La valeur peut être vide -- `NOM( )` ou `NOM()` (les deux formes existent) --
  ou contenir des espaces et des parenthèses imbriquées, par exemple
  `CONNAME(host.example.com(1415))`.
- Le nom de l'objet est lui-même un attribut du bloc (QUEUE(...), CHANNEL(...),
  PROCESS(...), NAMELIST(...), QMNAME(...)) -- il n'y a pas de marqueur séparé.
- Le fichier est encadré par un bandeau de capture "OV Log Start/End" et
  précédé d'un écho de commande tronqué/mis en forme par le terminal : tout
  ce qui précède le premier message AMQ84xx est ignoré sans risque (pur bruit
  d'écho de commande).
- Les lignes de contrôle (`MQSC >...`, `   12 : DISPLAY ... ALL`) ne portent
  pas d'attributs ; elles servent seulement à retrouver le contexte
  (quelle commande DISPLAY est en cours) en cas d'ambiguïté.
"""

from __future__ import annotations

import re

from core.model import MQAttribute, MQObject, ParseIssue, ParseResult

_AMQ_HEADER_RE = re.compile(r"^AMQ(?P<code>\d+):\s*(?P<msg>.*)$")
# Sur NonStop, la frappe de la commande DISPLAY suivante peut être capturée
# entrelacée caractère par caractère avec la sortie encore en cours de la
# commande précédente (capture terminal asynchrone). Ça se traduit par des
# lettres résiduelles collées devant "AMQ84xx:" (ex: "DAMQ8409:") -- vu en
# conditions réelles sur MT03/LEIA. On tolère un petit préfixe résiduel.
_AMQ_HEADER_LOOSE_RE = re.compile(r"^(?P<prefix>\S{0,6})AMQ(?P<code>\d+):\s*(?P<msg>.*)$")
_CONTROL_LINE_RE = re.compile(r"^\s*(MQSC\s*>|\d+\s*:)")
_DISPLAY_CTX_RE = re.compile(
    r"DISPLAY\s+(QMGR|QLOCAL|QALIAS|QREMOTE|QMODEL|CHANNEL|PROCESS|NAMELIST)\b",
    re.IGNORECASE,
)
_TOKEN_START_RE = re.compile(r"[A-Za-z0-9_]")
# Même phénomène d'entrelacement : le reste de la commande frappée en avance
# ("ISPLAY PROCESS(*) ALL") peut atterrir en plein milieu d'un bloc
# d'attributs légitime. On le reconnaît et on l'évacue avant tokenisation
# plutôt que de laisser des attributs bidon (ex: PROCESS(*)) polluer l'objet.
_TORN_ECHO_RE = re.compile(
    r"D?ISPLAY\s+(QMGR|QLOCAL|QALIAS|QREMOTE|QMODEL|CHANNEL|PROCESS|NAMELIST)\s*"
    r"(\([^)]*\))?\s*ALL\b",
    re.IGNORECASE,
)

# code AMQ -> (obj_type de base, attribut qui donne le vrai type si ambigu)
_DETAIL_CODES: dict[str, str] = {
    "8408": "QMGR",
    "8409": "QUEUE",  # QLOCAL / QALIAS / QREMOTE / QMODEL, résolu via TYPE(...)
    "8414": "CHANNEL",
    "8407": "PROCESS",
    "8550": "NAMELIST",
}

_NAME_ATTR_BY_TYPE = {
    "QMGR": "QMNAME",
    "QLOCAL": "QUEUE",
    "QALIAS": "QUEUE",
    "QREMOTE": "QUEUE",
    "QMODEL": "QUEUE",
    "CHANNEL": "CHANNEL",
    "PROCESS": "PROCESS",
    "NAMELIST": "NAMELIST",
}


def _tokenize_attributes(text: str, base_line: int) -> tuple[list[MQAttribute], list[ParseIssue]]:
    """Découpe un bloc de texte en attributs NOM(valeur) / NOM (flag).

    Tokenizer à la main (pas de regex globale) car les valeurs peuvent
    contenir des parenthèses imbriquées (CONNAME(host(port))) et des espaces
    (DESCR(un texte avec des espaces)).
    """
    attrs: list[MQAttribute] = []
    issues: list[ParseIssue] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if not _TOKEN_START_RE.match(ch):
            # Caractère isolé non reconnu (ponctuation résiduelle, artefact
            # d'encodage...) : signalé, jamais fatal.
            line_no = base_line + text.count("\n", 0, i)
            issues.append(ParseIssue("unparsed_fragment", line_no, repr(ch)))
            i += 1
            continue
        start = i
        while i < n and (text[i].isalnum() or text[i] == "_"):
            i += 1
        name = text[start:i]
        if i < n and text[i] == "(":
            depth = 0
            val_start = i + 1
            j = i
            while j < n:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= n:
                # Parenthèse jamais fermée -- fin de bloc tronquée, on garde
                # ce qu'on a et on signale.
                value = text[val_start:].strip()
                line_no = base_line + text.count("\n", 0, start)
                issues.append(
                    ParseIssue("unparsed_fragment", line_no, f"{name}(...) non refermé")
                )
                attrs.append(MQAttribute(name.upper(), value, False, line_no))
                i = n
            else:
                value = text[val_start:j].strip()
                line_no = base_line + text.count("\n", 0, start)
                attrs.append(MQAttribute(name.upper(), value, False, line_no))
                i = j + 1
        else:
            line_no = base_line + text.count("\n", 0, start)
            attrs.append(MQAttribute(name.upper(), name.upper(), True, line_no))
    return attrs, issues


def _resolve_object_type(base_type: str, attrs: list[MQAttribute], ctx: str | None) -> tuple[str, str | None]:
    """Retourne (obj_type_final, chltype). Utilise TYPE(...)/CHLTYPE(...) si présent,
    sinon retombe sur le contexte de la dernière commande DISPLAY vue."""
    if base_type == "QUEUE":
        for a in attrs:
            if a.name == "TYPE" and not a.is_flag:
                return a.value.upper(), None
        return (ctx or "QLOCAL"), None
    if base_type == "CHANNEL":
        chltype = None
        for a in attrs:
            if a.name == "CHLTYPE" and not a.is_flag:
                chltype = a.value.upper()
                break
        return "CHANNEL", chltype
    return base_type, None


def parse_display_all(text: str) -> ParseResult:
    """Parse une sortie complète de runmqsc V5.3 NonStop (plusieurs DISPLAY ... ALL
    concaténés) et retourne les objets structurés + tout ce qui n'a pas pu être
    interprété, sans jamais lever d'exception sur une entrée mal formée."""
    result = ParseResult()
    lines = text.splitlines()

    # Tout ce qui précède le premier message AMQ84xx est un bandeau de capture
    # et/ou un écho de commande tronqué par le terminal : bruit sans donnée,
    # ignoré sans perte (aucun attribut d'objet n'apparaît avant ce point).
    first_amq_idx = None
    for idx, line in enumerate(lines):
        if _AMQ_HEADER_RE.match(line.strip()):
            first_amq_idx = idx
            break
    if first_amq_idx is None:
        result.issues.append(ParseIssue("error_message", 1, "Aucun message AMQ84xx trouvé dans le fichier."))
        return result

    current_ctx: str | None = None
    pending_code: str | None = None
    pending_msg: str = ""
    pending_lines: list[str] = []
    pending_start_line = 0

    def flush_pending() -> None:
        nonlocal pending_code, pending_msg, pending_lines
        if pending_code is None:
            pending_lines = []
            return
        block_text = "\n".join(pending_lines)
        if pending_code not in _DETAIL_CODES:
            # Message AMQ non lié à un détail d'objet (erreur de syntaxe,
            # "aucun objet trouvé", etc.) : capturé pour le rapport, jamais
            # transformé en objet.
            full_msg = pending_msg + ("\n" + block_text if block_text.strip() else "")
            result.issues.append(
                ParseIssue("error_message", pending_start_line, f"AMQ{pending_code}: {full_msg.strip()}")
            )
        else:
            base_type = _DETAIL_CODES[pending_code]
            attrs, tok_issues = _tokenize_attributes(block_text, pending_start_line)
            result.issues.extend(tok_issues)
            obj_type, chltype = _resolve_object_type(base_type, attrs, current_ctx)
            name_attr = _NAME_ATTR_BY_TYPE.get(obj_type, _NAME_ATTR_BY_TYPE.get(base_type, ""))
            attr_map = {a.name: a for a in attrs}
            name_val = attr_map[name_attr].value if name_attr in attr_map else "?"
            obj = MQObject(
                obj_type=obj_type,
                name=name_val,
                attributes=attr_map,
                chltype=chltype,
                source_line=pending_start_line,
            )
            result.objects.append(obj)
            if obj_type == "QMGR" and result.source_qmgr is None:
                result.source_qmgr = name_val
        pending_code = None
        pending_msg = ""
        pending_lines = []

    for idx in range(first_amq_idx, len(lines)):
        raw_line = lines[idx]
        stripped = raw_line.strip()
        lineno = idx + 1

        if not stripped:
            continue

        # Bandeau de fin de capture : arrêt propre.
        if stripped.startswith("=" * 10) or stripped.startswith("OV Log End"):
            flush_pending()
            break

        amq_match = _AMQ_HEADER_RE.match(stripped)
        loose_prefix = ""
        if not amq_match:
            loose_match = _AMQ_HEADER_LOOSE_RE.match(stripped)
            if loose_match and loose_match.group("prefix") and "(" not in loose_match.group("prefix"):
                amq_match = loose_match
                loose_prefix = loose_match.group("prefix")
        if amq_match:
            flush_pending()
            if loose_prefix:
                result.issues.append(
                    ParseIssue(
                        "unparsed_fragment",
                        lineno,
                        f"préfixe résiduel {loose_prefix!r} devant AMQ{amq_match.group('code')}: "
                        "(écho de commande entrelacé, capture NonStop) -- ignoré, en-tête reconnu malgré tout",
                    )
                )
            pending_code = amq_match.group("code")
            pending_msg = amq_match.group("msg")
            pending_start_line = lineno
            continue

        if _CONTROL_LINE_RE.match(raw_line):
            # Ligne d'écho de commande / prompt MQSC : met à jour le contexte
            # de type courant, ne contient aucun attribut exploitable.
            ctx_match = _DISPLAY_CTX_RE.search(stripped)
            if ctx_match:
                current_ctx = ctx_match.group(1).upper()
            flush_pending()
            continue

        if pending_code is not None:
            torn = _TORN_ECHO_RE.search(raw_line)
            if torn:
                result.issues.append(
                    ParseIssue(
                        "unparsed_fragment",
                        lineno,
                        f"fragment d'écho de commande intercalé ignoré : {torn.group(0)!r}",
                    )
                )
                raw_line = _TORN_ECHO_RE.sub(" ", raw_line)
            pending_lines.append(raw_line)
        else:
            result.issues.append(ParseIssue("unparsed_fragment", lineno, stripped))

    flush_pending()
    return result
