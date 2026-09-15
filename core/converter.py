"""Application des règles du catalogue (rules/attributes.yaml) aux objets parsés."""

from __future__ import annotations

from pathlib import Path

import yaml

from core.model import (
    TYPE_TO_CATALOGUE_KEY,
    ConversionNote,
    ConversionResult,
    MQAttribute,
    MQObject,
    ParseResult,
)

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "attributes.yaml"


def load_catalogue(path: Path | str = DEFAULT_RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _convert_object(obj: MQObject, catalogue: dict, notes: list[ConversionNote]) -> MQObject:
    key = TYPE_TO_CATALOGUE_KEY[obj.obj_type]
    rules = catalogue[key]
    runtime = set(rules.get("runtime", []))
    renamed: dict[str, str] = rules.get("renamed", {})
    flags = rules.get("flags", [])
    flag_names = {kw for pair in flags for kw in pair}
    name_attr = rules["name_attr"]
    chltype_attr = rules.get("chltype_attr")

    if obj.obj_type == "CHANNEL":
        valid = set(rules.get("valid_by_type", {}).get(obj.chltype or "", []))
    else:
        valid = set(rules.get("valid", []))

    new_attrs: dict[str, MQAttribute] = {}
    for attr_name, attr in obj.attributes.items():
        if attr_name == name_attr:
            continue  # porté par l'objet lui-même, pas réémis comme attribut
        if attr_name == chltype_attr:
            new_attrs[attr_name] = attr
            continue
        if attr_name in runtime:
            notes.append(
                ConversionNote(
                    "removed", obj.obj_type, obj.name,
                    f"{attr_name} supprimé (attribut runtime / lecture seule, généré par le QM)",
                )
            )
            continue
        if attr_name in renamed:
            new_name = renamed[attr_name]
            notes.append(
                ConversionNote("renamed", obj.obj_type, obj.name, f"{attr_name} renommé en {new_name}")
            )
            new_attrs[new_name] = MQAttribute(new_name, attr.value, attr.is_flag, attr.line)
            continue
        if attr.is_flag:
            if attr_name not in flag_names and attr_name not in valid:
                notes.append(
                    ConversionNote(
                        "unknown_attr", obj.obj_type, obj.name,
                        f"{attr_name} (mot-clé booléen) inconnu du catalogue -- conservé sans modification",
                    )
                )
            new_attrs[attr_name] = attr
            continue
        if attr_name not in valid:
            notes.append(
                ConversionNote(
                    "unknown_attr", obj.obj_type, obj.name,
                    f"{attr_name} inconnu du catalogue -- conservé sans modification, à vérifier",
                )
            )
        new_attrs[attr_name] = attr

    forced: dict[str, str] = rules.get("forced", {})
    for fname, fvalue in forced.items():
        new_attrs[fname] = MQAttribute(fname, str(fvalue), False, 0)

    return MQObject(
        obj_type=obj.obj_type,
        name=obj.name,
        attributes=new_attrs,
        chltype=obj.chltype,
        source_line=obj.source_line,
    )


def convert(parse_result: ParseResult, catalogue: dict, include_system: bool = False) -> ConversionResult:
    """Convertit tous les objets d'un ParseResult V5.3 vers leurs équivalents V8.1.

    Ne modifie jamais silencieusement un attribut inconnu du catalogue : il est
    conservé tel quel et une note "unknown_attr" est ajoutée au rapport.
    """
    result = ConversionResult()
    for obj in parse_result.objects:
        if obj.obj_type not in TYPE_TO_CATALOGUE_KEY:
            result.notes.append(
                ConversionNote(
                    "ignored_object", obj.obj_type, obj.name,
                    "type d'objet non reconnu par le catalogue -- ignoré, absent de toute sortie",
                )
            )
            continue
        if obj.is_system() and not include_system:
            result.ignored_system_objects.append(obj)
            continue
        converted = _convert_object(obj, catalogue, result.notes)
        if obj.obj_type == "QMGR":
            result.qmgr = converted
        elif obj.obj_type in ("QLOCAL", "QMODEL", "QALIAS", "QREMOTE"):
            result.queues.append(converted)
        elif obj.obj_type == "CHANNEL":
            result.channels.append(converted)
        elif obj.obj_type == "PROCESS":
            result.processes.append(converted)
        elif obj.obj_type == "NAMELIST":
            result.namelists.append(converted)
    return result
