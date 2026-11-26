from pathlib import Path

from core.converter import convert, load_catalogue
from core.parser import parse_display_all
from core.validator import summarize, validate

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_validate_matches_common_objects():
    catalogue = load_catalogue()
    source_parse = parse_display_all(load("v53_sample.log"))
    target_parse = parse_display_all(load("v81_sample.log"))
    generated = convert(source_parse, catalogue, include_system=False)

    diffs = validate(source_parse, generated, target_parse)
    stats = summarize(diffs)

    ql_test = next(d for d in diffs if d.obj_name == "QL.APPLI.TEST")
    assert ql_test.status == "matched"
    # Aucune vraie divergence de valeur : les seuls écarts tolérés sont des
    # attributs V8.1 "review" (ACCTQ, CLWLRANK...) absents de la source V5.3
    # et donc non générés -- jamais une valeur qui diffère (status "diff").
    diverging = [r for r in ql_test.rows if r.status == "diff"]
    assert diverging == []

    assert stats["total_objects"] > 0
    # D'autres objets portent volontairement de vrais écarts dans la fixture
    # (MCAUSER positionné après coup sur LEIA, SSLKEYR qui change de chemin
    # d'install...) : c'est justement ce que ce mode doit détecter.
    assert stats["attr_diffs"] == 3


def test_validate_flags_object_only_in_real_target():
    catalogue = load_catalogue()
    source_parse = parse_display_all(load("v53_sample.log"))
    target_parse = parse_display_all(load("v81_sample.log"))
    generated = convert(source_parse, catalogue, include_system=False)

    diffs = validate(source_parse, generated, target_parse)
    # QL.APPLI.NOUVELLE n'existe que côté LEIA (créée après migration).
    only_real = next(d for d in diffs if d.obj_name == "QL.APPLI.NOUVELLE")
    assert only_real.status == "only_real"


def test_validate_three_column_diff_values():
    catalogue = load_catalogue()
    source_parse = parse_display_all(load("v53_sample.log"))
    target_parse = parse_display_all(load("v81_sample.log"))
    generated = convert(source_parse, catalogue, include_system=False)

    diffs = validate(source_parse, generated, target_parse)
    alias = next(d for d in diffs if d.obj_name == "QA.APPLI.TEST")
    target_row = next(r for r in alias.rows if r.attr == "TARGET")
    # V5.3 portait TARGQ, pas TARGET : la colonne "v53_value" ne connaît pas
    # l'attribut renommé -- seule la colonne générée et la colonne réelle le
    # portent, et elles doivent concorder.
    assert target_row.generated_value == "QL.APPLI.TEST"
    assert target_row.real_value == "QL.APPLI.TEST"
    assert target_row.status == "match"
