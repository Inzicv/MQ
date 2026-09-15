"""Interface Streamlit : DISPLAY ... ALL V5.3 (NonStop) -> MQSC V8.1 prêt à injecter.

Upload de fichiers uniquement. Rien n'est lu depuis le disque serveur, rien
n'est écrit de façon persistante, aucune commande générée n'est exécutée et
l'appli ne se connecte à aucun queue manager.
"""

from __future__ import annotations

import io
import zipfile

import streamlit as st

from core.converter import convert, load_catalogue
from core.parser import parse_display_all
from core.renderer import (
    render_channels_file,
    render_qmgr_process_namelist_file,
    render_queues_file,
    render_report,
)
from core.validator import summarize, validate

st.set_page_config(page_title="Migration MQ V5.3 -> V8.1 NonStop", layout="wide")

st.title("Migration IBM MQ V5.3 -> V8.1 sur HPE NonStop")
st.caption(
    "Convertit une sortie `DISPLAY ... ALL` runmqsc V5.3 en fichiers MQSC V8.1 "
    "prêts pour `runmqsc <QM> < fichier.mqsc`. Conversion 100% déterministe, "
    "aucun appel réseau ni LLM, rien n'est exécuté ni connecté à un QM."
)

with st.sidebar:
    st.header("Options")
    replace = st.checkbox("Ajouter REPLACE aux DEFINE", value=False)
    include_system = st.checkbox("Inclure les objets SYSTEM.*", value=False)
    source_machine = st.text_input("Machine source (info, pour l'en-tête des fichiers)", value="ISIS")
    st.divider()
    mode = st.radio("Mode", ["Conversion", "Validation croisée (vs capture V8.1 réelle)"])

catalogue = load_catalogue()

if mode == "Conversion":
    uploaded = st.file_uploader("Sortie DISPLAY ... ALL V5.3 (fichier texte)", type=["txt", "log"])
    if uploaded is not None:
        text = uploaded.read().decode("utf-8", errors="replace")
        parse_result = parse_display_all(text)
        conv_result = convert(parse_result, catalogue, include_system=include_system)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Files converties", len(conv_result.queues))
        col2.metric("Canaux convertis", len(conv_result.channels))
        col3.metric("PROCESS / NAMELIST", f"{len(conv_result.processes)} / {len(conv_result.namelists)}")
        col4.metric("Fragments non parsés", len(parse_result.issues))

        queues_mqsc = render_queues_file(
            conv_result, catalogue, parse_result.source_qmgr, source_machine, replace
        )
        channels_mqsc = render_channels_file(
            conv_result, catalogue, parse_result.source_qmgr, source_machine, replace
        )
        qpn_mqsc = render_qmgr_process_namelist_file(
            conv_result, catalogue, parse_result.source_qmgr, source_machine, replace
        )
        report_txt = render_report(conv_result, parse_result.source_qmgr, source_machine, len(parse_result.issues))

        tabs = st.tabs(
            ["01_queues.mqsc", "02_channels.mqsc", "03_qmgr_process_namelist.mqsc", "Rapport", "Non parsé"]
        )
        with tabs[0]:
            st.code(queues_mqsc, language="text")
            st.download_button("Télécharger 01_queues.mqsc", queues_mqsc, file_name="01_queues.mqsc")
        with tabs[1]:
            st.code(channels_mqsc, language="text")
            st.download_button("Télécharger 02_channels.mqsc", channels_mqsc, file_name="02_channels.mqsc")
        with tabs[2]:
            st.code(qpn_mqsc, language="text")
            st.download_button(
                "Télécharger 03_qmgr_process_namelist.mqsc",
                qpn_mqsc,
                file_name="03_qmgr_process_namelist.mqsc",
            )
        with tabs[3]:
            st.text(report_txt)
            st.download_button("Télécharger le rapport", report_txt, file_name="rapport_conversion.txt")
        with tabs[4]:
            if parse_result.issues:
                for issue in parse_result.issues:
                    st.text(f"L{issue.line} [{issue.kind}] {issue.text}")
            else:
                st.success("Aucun fragment non parsé.")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("01_queues.mqsc", queues_mqsc)
            zf.writestr("02_channels.mqsc", channels_mqsc)
            zf.writestr("03_qmgr_process_namelist.mqsc", qpn_mqsc)
            zf.writestr("rapport_conversion.txt", report_txt)
        st.download_button(
            "Télécharger tout (zip)",
            zip_buffer.getvalue(),
            file_name="migration_mqsc.zip",
            mime="application/zip",
        )
    else:
        st.info("Charge une sortie DISPLAY ... ALL V5.3 pour lancer la conversion.")

else:
    st.write(
        "Charge la sortie DISPLAY ... ALL V5.3 (source) et la capture DISPLAY ... ALL "
        "V8.1 réelle (cible, ex: LEIA) : la conversion est générée depuis la source puis "
        "comparée objet par objet, attribut par attribut, à la cible réelle."
    )
    c1, c2 = st.columns(2)
    with c1:
        src_file = st.file_uploader("Source V5.3", type=["txt", "log"], key="src")
    with c2:
        tgt_file = st.file_uploader("Cible V8.1 réelle", type=["txt", "log"], key="tgt")

    if src_file is not None and tgt_file is not None:
        src_text = src_file.read().decode("utf-8", errors="replace")
        tgt_text = tgt_file.read().decode("utf-8", errors="replace")
        source_parse = parse_display_all(src_text)
        target_parse = parse_display_all(tgt_text)
        conv_result = convert(source_parse, catalogue, include_system=include_system)
        diffs = validate(source_parse, conv_result, target_parse)
        stats = summarize(diffs)

        cols = st.columns(4)
        cols[0].metric("Objets comparés", stats["total_objects"])
        cols[1].metric("Attributs identiques", "OK" if stats["attr_diffs"] == 0 else stats["attr_diffs"])
        cols[2].metric("Objets absents de la cible réelle", stats["only_generated_objects"])
        cols[3].metric("Objets présents seulement côté cible réelle", stats["only_real_objects"])

        only_diffs = st.checkbox("N'afficher que les lignes en écart", value=True)
        for d in diffs:
            rows_to_show = [r for r in d.rows if (not only_diffs or r.status != "match")]
            if d.status != "matched":
                label = f"{d.obj_type} {d.obj_name} -- {d.status}"
            elif rows_to_show:
                label = f"{d.obj_type} {d.obj_name} -- {len(rows_to_show)} écart(s)"
            else:
                continue
            with st.expander(label):
                if d.status == "only_generated":
                    st.warning("Généré depuis la source mais absent de la capture V8.1 réelle.")
                elif d.status == "only_real":
                    st.info("Présent uniquement dans la capture V8.1 réelle (objet créé après migration ?).")
                if rows_to_show:
                    st.table(
                        [
                            {
                                "Attribut": r.attr,
                                "V5.3 (source)": r.v53_value,
                                "Généré": r.generated_value,
                                "V8.1 réel": r.real_value,
                                "Statut": r.status,
                            }
                            for r in rows_to_show
                        ]
                    )
