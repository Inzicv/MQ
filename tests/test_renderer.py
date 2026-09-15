from pathlib import Path

from core.converter import convert, load_catalogue
from core.parser import parse_display_all
from core.renderer import (
    render_channels_file,
    render_qmgr_process_namelist_file,
    render_queues_file,
    render_report,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _convert(include_system=False):
    catalogue = load_catalogue()
    parse_result = parse_display_all(load("v53_sample.log"))
    result = convert(parse_result, catalogue, include_system=include_system)
    return catalogue, parse_result, result


def test_queues_file_order_is_qlocal_qmodel_qalias_qremote():
    catalogue, parse_result, result = _convert()
    text = render_queues_file(result, catalogue, parse_result.source_qmgr, "ISIS", replace=False)
    pos_qlocal = text.index("* --- QLOCAL")
    pos_qmodel = text.index("* --- QMODEL")
    pos_qalias = text.index("* --- QALIAS")
    pos_qremote = text.index("* --- QREMOTE")
    assert pos_qlocal < pos_qmodel < pos_qalias < pos_qremote
    assert "DEFINE QLOCAL(QL.APPLI.TEST)" in text


def test_queues_file_uses_replace_when_requested():
    catalogue, parse_result, result = _convert()
    text = render_queues_file(result, catalogue, parse_result.source_qmgr, "ISIS", replace=True)
    assert "DEFINE QLOCAL(QL.APPLI.TEST) REPLACE" in text


def test_channels_file_grouped_by_chltype_in_order():
    catalogue, parse_result, result = _convert()
    text = render_channels_file(result, catalogue, parse_result.source_qmgr, "ISIS", replace=False)
    pos_sdr = text.index("CHLTYPE(SDR)")
    pos_rcvr = text.index("CHLTYPE(RCVR)")
    pos_svrconn = text.index("CHLTYPE(SVRCONN)")
    assert pos_sdr < pos_rcvr < pos_svrconn
    assert "DEFINE CHANNEL(CH.TEST.SDR)" in text
    assert "CONNAME('distant.host.example.net(1415)')" in text


def test_qmgr_file_uses_alter_never_define():
    catalogue, parse_result, result = _convert()
    text = render_qmgr_process_namelist_file(result, catalogue, parse_result.source_qmgr, "ISIS", replace=False)
    assert "ALTER QMGR" in text
    assert "DEFINE QMGR" not in text
    assert "SCMDSERV(QMGR)" in text
    assert "DEFINE PROCESS(PR.TEST.DISTANT)" in text


def test_empty_attributes_are_not_emitted():
    catalogue, parse_result, result = _convert()
    text = render_queues_file(result, catalogue, parse_result.source_qmgr, "ISIS", replace=False)
    # PROCESS( ) sur QL.APPLI.TEST est vide côté source -> pas réémis.
    assert "PROCESS( )" not in text
    assert "PROCESS()" not in text


def test_report_lists_removed_and_renamed():
    catalogue, parse_result, result = _convert()
    report = render_report(result, parse_result.source_qmgr, "ISIS", 0)
    assert "TARGQ" in report and "TARGET" in report
    assert "CURDEPTH" in report
    assert "altmqfls" in report  # checklist statique toujours présente
