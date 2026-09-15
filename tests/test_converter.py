from pathlib import Path

from core.converter import convert, load_catalogue
from core.parser import parse_display_all

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_system_objects_filtered_by_default():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=False)
    names = {q.name for q in result.queues}
    assert "SYSTEM.DEFAULT.LOCAL.QUEUE" not in names
    assert any(n.startswith("SYSTEM.") for n in (o.name for o in result.ignored_system_objects))


def test_system_objects_included_on_demand():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=True)
    names = {q.name for q in result.queues}
    assert "SYSTEM.DEFAULT.LOCAL.QUEUE" in names


def test_runtime_attributes_are_stripped():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=False)
    q = next(q for q in result.queues if q.name == "QL.APPLI.TEST")
    for runtime_attr in ("CRDATE", "CRTIME", "ALTDATE", "ALTTIME", "IPPROCS", "OPPROCS", "CURDEPTH", "TYPE"):
        assert runtime_attr not in q.attributes
    removed_notes = [n for n in result.notes if n.category == "removed" and n.obj_name == "QL.APPLI.TEST"]
    assert any("CURDEPTH" in n.detail for n in removed_notes)


def test_qalias_targq_renamed_to_target():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=False)
    alias = next(q for q in result.queues if q.name == "QA.APPLI.TEST")
    assert "TARGQ" not in alias.attributes
    assert alias.get("TARGET") == "QL.APPLI.TEST"
    renamed_notes = [n for n in result.notes if n.category == "renamed" and n.obj_name == "QA.APPLI.TEST"]
    assert renamed_notes


def test_qmgr_alter_forces_scmdserv():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=False)
    assert result.qmgr is not None
    assert result.qmgr.get("SCMDSERV") == "QMGR"


def test_unknown_attribute_is_kept_and_flagged():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    # Injecte un attribut fictif inconnu du catalogue pour vérifier qu'il
    # n'est jamais supprimé silencieusement.
    q_obj = next(o for o in parse_result.objects if o.name == "QL.APPLI.TEST")
    from core.model import MQAttribute

    q_obj.attributes["ATTRIBUTFICTIF"] = MQAttribute("ATTRIBUTFICTIF", "valeur", False, 0)

    result = convert(parse_result, catalogue, include_system=False)
    q = next(q for q in result.queues if q.name == "QL.APPLI.TEST")
    assert q.get("ATTRIBUTFICTIF") == "valeur"
    unknown_notes = [n for n in result.notes if n.category == "unknown_attr" and "ATTRIBUTFICTIF" in n.detail]
    assert unknown_notes


def test_channel_valid_attrs_depend_on_chltype():
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=False)
    sdr = next(c for c in result.channels if c.chltype == "SDR")
    svrconn = next(c for c in result.channels if c.chltype == "SVRCONN")
    assert sdr.get("XMITQ") is not None
    assert "XMITQ" not in svrconn.attributes
