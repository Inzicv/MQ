"""Mode validation croisée : compare la conversion générée depuis une source
V5.3 à une capture réelle V8.1 (LEIA/PADME), objet par objet, attribut par
attribut. C'est l'outil de mise au point du catalogue."""

from __future__ import annotations

from dataclasses import dataclass

from core.model import ConversionResult, MQObject, ParseResult


@dataclass
class AttrDiffRow:
    obj_type: str
    obj_name: str
    attr: str
    v53_value: str | None
    generated_value: str | None
    real_value: str | None
    status: str  # "match" | "diff" | "only_generated" | "only_real" | "only_source"


@dataclass
class ObjectDiff:
    obj_type: str
    obj_name: str
    status: str  # "matched" | "only_generated" | "only_real"
    rows: list[AttrDiffRow]


def _key(obj: MQObject) -> tuple:
    if obj.obj_type == "CHANNEL":
        return ("CHANNEL", obj.chltype or "?", obj.name)
    return (obj.obj_type, obj.name)


def _index_by_key(objs: list[MQObject]) -> dict[tuple, MQObject]:
    return {_key(o): o for o in objs}


def validate(
    source_parse: ParseResult,
    generated: ConversionResult,
    target_parse: ParseResult,
) -> list[ObjectDiff]:
    """Compare, pour chaque objet généré, ses attributs à la fois à la source
    V5.3 brute et à la capture V8.1 réelle (LEIA). Retourne un diff par objet."""
    source_by_key = _index_by_key(source_parse.objects)
    target_by_key = _index_by_key(target_parse.objects)

    generated_objs: list[MQObject] = list(generated.queues)
    generated_objs += generated.channels
    generated_objs += generated.processes
    generated_objs += generated.namelists
    if generated.qmgr:
        generated_objs.append(generated.qmgr)
    generated_by_key = _index_by_key(generated_objs)

    diffs: list[ObjectDiff] = []

    for key, gen_obj in generated_by_key.items():
        real_obj = target_by_key.get(key)
        src_obj = source_by_key.get(key)
        rows: list[AttrDiffRow] = []
        attr_names = set(gen_obj.attributes) | (set(real_obj.attributes) if real_obj else set())
        for attr_name in sorted(attr_names):
            gen_val = gen_obj.get(attr_name)
            real_val = real_obj.get(attr_name) if real_obj else None
            src_val = src_obj.get(attr_name) if src_obj else None
            if gen_val is None and real_val is not None:
                status = "only_real"
            elif gen_val is not None and real_val is None:
                status = "only_generated" if real_obj else "only_generated"
            elif gen_val == real_val:
                status = "match"
            else:
                status = "diff"
            rows.append(AttrDiffRow(gen_obj.obj_type, gen_obj.name, attr_name, src_val, gen_val, real_val, status))
        diffs.append(
            ObjectDiff(
                gen_obj.obj_type,
                gen_obj.name,
                "matched" if real_obj else "only_generated",
                rows,
            )
        )

    for key, real_obj in target_by_key.items():
        if key not in generated_by_key:
            diffs.append(ObjectDiff(real_obj.obj_type, real_obj.name, "only_real", []))

    return diffs


def summarize(diffs: list[ObjectDiff]) -> dict[str, int]:
    total_objects = len(diffs)
    matched = sum(1 for d in diffs if d.status == "matched")
    only_generated = sum(1 for d in diffs if d.status == "only_generated")
    only_real = sum(1 for d in diffs if d.status == "only_real")
    attr_diffs = sum(1 for d in diffs for r in d.rows if r.status == "diff")
    attr_only_real = sum(1 for d in diffs for r in d.rows if r.status == "only_real")
    attr_only_generated = sum(1 for d in diffs for r in d.rows if r.status == "only_generated")
    return {
        "total_objects": total_objects,
        "matched_objects": matched,
        "only_generated_objects": only_generated,
        "only_real_objects": only_real,
        "attr_diffs": attr_diffs,
        "attr_only_real": attr_only_real,
        "attr_only_generated": attr_only_generated,
    }
