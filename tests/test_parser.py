from pathlib import Path

from core.parser import parse_display_all

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_qmgr():
    result = parse_display_all(load("v53_sample.log"))
    assert result.source_qmgr == "TEST"
    qmgr_objs = [o for o in result.objects if o.obj_type == "QMGR"]
    assert len(qmgr_objs) == 1
    assert qmgr_objs[0].get("DEADQ") == "TEST.DEAD.QUEUE"
    assert qmgr_objs[0].get("SYNCPT") == "SYNCPT"  # flag


def test_ignores_garbled_header_before_first_amq_message():
    result = parse_display_all(load("v53_sample.log"))
    # Le bruit d'écho de commande concaténé avant le premier AMQ8408 ne doit
    # jamais produire d'objet ni de fragment non parsé.
    for issue in result.issues:
        assert "DISPLAY QMGR ALLDISPLAY" not in issue.text


def test_resolves_queue_subtypes_via_type_attribute():
    result = parse_display_all(load("v53_sample.log"))
    types = {o.name: o.obj_type for o in result.objects if o.obj_type in {"QLOCAL", "QALIAS", "QREMOTE", "QMODEL"}}
    assert types["QL.APPLI.TEST"] == "QLOCAL"
    assert types["QA.APPLI.TEST"] == "QALIAS"
    assert types["QR.APPLI.TEST"] == "QREMOTE"
    assert types["SYSTEM.DEFAULT.MODEL.QUEUE"] == "QMODEL"


def test_channel_chltype_and_nested_parens_in_conname():
    result = parse_display_all(load("v53_sample.log"))
    sdr = next(o for o in result.objects if o.obj_type == "CHANNEL" and o.name == "CH.TEST.SDR")
    assert sdr.chltype == "SDR"
    # CONNAME(distant.host.example.net(1415)) : parenthèse imbriquée préservée.
    assert sdr.get("CONNAME") == "distant.host.example.net(1415)"


def test_empty_values_both_forms():
    result = parse_display_all(load("v53_sample.log"))
    rcvr = next(o for o in result.objects if o.obj_type == "CHANNEL" and o.name == "CH.TEST.RCV")
    assert rcvr.get("SSLPEER") == ""  # SSLPEER()
    assert rcvr.get("DESCR") == ""  # DESCR( )


def test_flag_attributes_captured():
    result = parse_display_all(load("v53_sample.log"))
    q = next(o for o in result.objects if o.name == "QL.APPLI.TEST")
    assert q.get("SHARE") == "SHARE"
    assert q.get("HARDENBO") == "HARDENBO"
    assert q.get("NOTRIGGER") == "NOTRIGGER"


def test_process_and_namelist():
    result = parse_display_all(load("v53_sample.log"))
    proc = next(o for o in result.objects if o.obj_type == "PROCESS")
    assert proc.name == "PR.TEST.DISTANT"
    nl = next(o for o in result.objects if o.obj_type == "NAMELIST")
    assert nl.name == "SYSTEM.DEFAULT.NAMELIST"
    assert nl.get("NAMES") == ""


def test_syntax_error_block_is_captured_as_issue_not_object():
    result = parse_display_all(load("v81_sample.log"))
    assert not any(o.obj_type == "NAMELIST" for o in result.objects)
    error_texts = " ".join(i.text for i in result.issues if i.kind == "error_message")
    assert "AMQ8405" in error_texts


def test_v81_sample_has_no_crash_and_expected_counts():
    result = parse_display_all(load("v81_sample.log"))
    assert result.source_qmgr == "TEST"
    qlocals = [o for o in result.objects if o.obj_type == "QLOCAL"]
    assert len(qlocals) == 2
    channels = [o for o in result.objects if o.obj_type == "CHANNEL"]
    assert {c.chltype for c in channels} == {"RCVR", "SDR", "SVRCONN"}
