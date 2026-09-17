"""Génération des fichiers MQSC V8.1 (01_queues.mqsc, 02_channels.mqsc,
03_qmgr_process_namelist.mqsc) à partir d'un ConversionResult."""

from __future__ import annotations

import re
from datetime import datetime

from core.model import TYPE_TO_CATALOGUE_KEY, ConversionResult, MQAttribute, MQObject

CONVERTER_VERSION = "0.1.0"
_MAX_LINE = 72

_SAFE_UNQUOTED_RE = re.compile(r"^[A-Za-z0-9_.\-/*]+$")


def _quote(value: str) -> str:
    if _SAFE_UNQUOTED_RE.match(value):
        return value
    return "'" + value.replace("'", "''") + "'"


def format_attr(attr: MQAttribute) -> str:
    if attr.is_flag:
        return attr.name
    return f"{attr.name}({_quote(attr.value)})"


def _wrap_command(head: str, params: list[str]) -> list[str]:
    """Un attribut par ligne, continuation `+`, sans indentation."""
    if not params:
        return [head]
    lines = [f"{head} +"]
    last = len(params) - 1
    for i, p in enumerate(params):
        line = p
        if i != last:
            line += " +"
        lines.append(line)
    return lines


def render_object(obj: MQObject, catalogue: dict, replace: bool) -> list[str]:
    rules = catalogue[TYPE_TO_CATALOGUE_KEY[obj.obj_type]]
    chltype_attr = rules.get("chltype_attr")

    if obj.obj_type == "QMGR":
        head = "ALTER QMGR"
    else:
        define_cmd = rules["define_cmd"]
        head = f"DEFINE {define_cmd}({_quote(obj.name)})"

    params: list[str] = []
    if obj.obj_type == "CHANNEL" and obj.chltype:
        params.append(f"CHLTYPE({obj.chltype})")

    for attr_name in sorted(obj.attributes):
        if attr_name == chltype_attr:
            continue
        attr = obj.attributes[attr_name]
        if not attr.is_flag and attr.value == "":
            # Valeur vide == valeur par défaut V8.1 pour tous les attributs
            # caractère observés dans les fixtures réelles : on ne la réémet
            # pas, ça garde le MQSC lisible. Choix de conception documenté
            # dans le rapport et le README.
            continue
        params.append(format_attr(attr))

    if replace and obj.obj_type != "QMGR":
        params.append("REPLACE")

    return _wrap_command(head, params)


def _header(title: str, source_qmgr: str, source_machine: str, counts: dict[str, int]) -> list[str]:
    lines = [
        "*" + "=" * 70,
        f"* {title}",
        "* Migration IBM MQ V5.3 -> V8.1 sur HPE NonStop",
        f"* QM source     : {source_qmgr or '?'}",
        f"* Machine source: {source_machine or '?'}",
        f"* Genere le     : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"* Convertisseur : mq-migrate-nonstop v{CONVERTER_VERSION}",
    ]
    for label, count in counts.items():
        lines.append(f"* {label:<14}: {count}")
    lines.append("*" + "=" * 70)
    lines.append("")
    return lines


def render_queues_file(
    result: ConversionResult, catalogue: dict, source_qmgr: str, source_machine: str, replace: bool
) -> str:
    order = catalogue.get("queue_order", ["QLOCAL", "QMODEL", "QALIAS", "QREMOTE"])
    by_type: dict[str, list[MQObject]] = {t: [] for t in order}
    for q in result.queues:
        by_type.setdefault(q.obj_type, []).append(q)

    counts = {t: len(by_type.get(t, [])) for t in order}
    lines = _header("01_queues.mqsc -- QLOCAL, QMODEL, QALIAS, QREMOTE", source_qmgr, source_machine, counts)

    for obj_type in order:
        objs = sorted(by_type.get(obj_type, []), key=lambda o: o.name)
        lines.append(f"* --- {obj_type} ({len(objs)} objet(s)) ---")
        lines.append("")
        for obj in objs:
            lines.extend(render_object(obj, catalogue, replace))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_channels_file(
    result: ConversionResult, catalogue: dict, source_qmgr: str, source_machine: str, replace: bool
) -> str:
    order = catalogue.get(
        "channel_order", ["SDR", "RCVR", "SVRCONN", "RQSTR", "SVR", "CLUSSDR", "CLUSRCVR", "CLNTCONN"]
    )
    by_chltype: dict[str, list[MQObject]] = {t: [] for t in order}
    for ch in result.channels:
        by_chltype.setdefault(ch.chltype or "?", []).append(ch)

    counts = {t: len(by_chltype.get(t, [])) for t in order}
    lines = _header("02_channels.mqsc -- Canaux par CHLTYPE", source_qmgr, source_machine, counts)

    for chltype in order:
        objs = sorted(by_chltype.get(chltype, []), key=lambda o: o.name)
        lines.append(f"* --- CHLTYPE({chltype}) : {len(objs)} canal(aux) ---")
        lines.append("")
        for obj in objs:
            lines.extend(render_object(obj, catalogue, replace))
            lines.append("")

    # CHLTYPE non prévus par channel_order mais présents dans la source
    extra_types = [t for t in by_chltype if t not in order]
    for chltype in extra_types:
        objs = sorted(by_chltype[chltype], key=lambda o: o.name)
        lines.append(f"* --- CHLTYPE({chltype}) : {len(objs)} canal(aux) [hors ordre standard] ---")
        lines.append("")
        for obj in objs:
            lines.extend(render_object(obj, catalogue, replace))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_qmgr_process_namelist_file(
    result: ConversionResult, catalogue: dict, source_qmgr: str, source_machine: str, replace: bool
) -> str:
    counts = {
        "QMGR": 1 if result.qmgr else 0,
        "PROCESS": len(result.processes),
        "NAMELIST": len(result.namelists),
    }
    lines = _header(
        "03_qmgr_process_namelist.mqsc -- ALTER QMGR, PROCESS, NAMELIST",
        source_qmgr,
        source_machine,
        counts,
    )

    lines.append("* --- QMGR (ALTER, jamais DEFINE) ---")
    lines.append("")
    if result.qmgr:
        lines.extend(render_object(result.qmgr, catalogue, replace=False))
        lines.append("")

    lines.append(f"* --- PROCESS ({len(result.processes)} objet(s)) ---")
    lines.append("")
    for obj in sorted(result.processes, key=lambda o: o.name):
        lines.extend(render_object(obj, catalogue, replace))
        lines.append("")

    lines.append(f"* --- NAMELIST ({len(result.namelists)} objet(s)) ---")
    lines.append("")
    for obj in sorted(result.namelists, key=lambda o: o.name):
        lines.extend(render_object(obj, catalogue, replace))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_report(
    result: ConversionResult,
    source_qmgr: str,
    source_machine: str,
    parse_issues_count: int,
) -> str:
    lines = [
        "RAPPORT DE CONVERSION MQ V5.3 -> V8.1",
        f"QM source      : {source_qmgr or '?'}",
        f"Machine source : {source_machine or '?'}",
        f"Genere le      : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Convertisseur  : mq-migrate-nonstop v{CONVERTER_VERSION}",
        "",
        "-- Compteurs --",
        f"QLOCAL   : {sum(1 for q in result.queues if q.obj_type == 'QLOCAL')}",
        f"QMODEL   : {sum(1 for q in result.queues if q.obj_type == 'QMODEL')}",
        f"QALIAS   : {sum(1 for q in result.queues if q.obj_type == 'QALIAS')}",
        f"QREMOTE  : {sum(1 for q in result.queues if q.obj_type == 'QREMOTE')}",
        f"CHANNEL  : {len(result.channels)}",
        f"PROCESS  : {len(result.processes)}",
        f"NAMELIST : {len(result.namelists)}",
        f"QMGR     : {'1 (ALTER QMGR)' if result.qmgr else '0'}",
        f"Objets SYSTEM.* ignores : {len(result.ignored_system_objects)}",
        f"Fragments/messages non parses (voir capture) : {parse_issues_count}",
        "",
    ]

    def section(title: str, category: str) -> None:
        notes = [n for n in result.notes if n.category == category]
        lines.append(f"-- {title} ({len(notes)}) --")
        for n in notes:
            lines.append(f"  [{n.obj_type}] {n.obj_name} : {n.detail}")
        lines.append("")

    section("Attributs supprimes (runtime/lecture seule)", "removed")
    section("Attributs renommes V5.3 -> V8.1", "renamed")
    section("Attributs inconnus du catalogue (conserves, a verifier)", "unknown_attr")
    section("Objets ignores (type non reconnu)", "ignored_object")

    lines.append("-- Points non automatisables par cet outil (checklist manuelle) --")
    lines.extend(
        [
            "  [ ] altmqfls / dspmqfls : fichiers Guardian associes aux objets MQ",
            "  [ ] Configuration TMF (transaction management facility)",
            "  [ ] runnscnf : configuration reseau NonStop du QM",
            "  [ ] setmqaut / dmpmqaut : droits OAM, a rejouer un par un (pas de wildcard sur -n)",
            "  [ ] CHLAUTH / MCAUSER : regles de mapping canal -> utilisateur Guardian",
            "  [ ] altmqusr / dspmqusr : comptes utilisateurs MQ NonStop",
            "  [ ] LISTENER et command server : attributs persistants du QM"
            " (CONTROL(QMGR), SCMDSERV force a QMGR dans 03_qmgr_process_namelist.mqsc)",
            "  [ ] SVRCONN : verifier MAXINST/MAXINSTC/SHARECNV/SSLCIPH/CERTLABL"
            " (non repris de la source V5.3, valeurs par defaut V8.1 appliquees a l'injection)",
        ]
    )
    lines.append("")
    lines.append(
        "Note methodologique : les attributs caracteres vides cote source "
        "(ATTR( ) ou ATTR()) ne sont pas reemis dans les DEFINE/ALTER generes "
        "(equivalent a la valeur par defaut V8.1)."
    )
    return "\n".join(lines) + "\n"
