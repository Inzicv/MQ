import streamlit as st
import re

# --- LOGIQUE DE TRANSFORMATION ---
def transform_mq_clean(input_text, obj_type):
    type_map = {"QUEUE": "QLOCAL", "CHANNEL": "CHANNEL", "PROCESS": "PROCESS", "QMGR": "QMGR"}
    # On ignore les stats et les dates
    to_ignore = ['CURDEPTH', 'IPPROCS', 'OPPROCS', 'LPIPROCS', 'LOPPROCS', 'ALTDATE', 'ALTTIME', 'CRDATE', 'CRTIME']
    
    blocks = [b.strip() for b in input_text.split('\n\n') if b.strip()]
    final_output = []
    
    for block in blocks:
        # Regex pour capturer les attributs
        pattern = r'([A-Z0-9]+)\s*\((.*?)\)|([A-Z0-9]{3,})'
        matches = re.findall(pattern, block)
        attrs = {}
        obj_name = ""
        actual_type = type_map.get(obj_type, "QLOCAL")
        
        for m in matches:
            key = m[0] if m[0] else m[2]
            val = m[1] if m[0] else None
            if key in to_ignore: continue
            clean_val = "" if (val is None or val.strip() == "") else val.strip()
            if key == obj_type:
                obj_name = clean_val
                continue
            if key == "TYPE" and obj_type == "QUEUE":
                actual_type = clean_val
                continue
            attrs[key] = f"({clean_val})" if val is not None else ""
            
        header = f"ALTER QMGR +" if obj_type == "QMGR" else f"DEFINE {actual_type}({obj_name}) +"
        command = [header]
        attr_list = list(attrs.items())
        
        if "CHLTYPE(SVRCONN)" in block and "MCAUSER" not in attrs:
            attr_list.append(("MCAUSER", "('MQM.ADMIN2')"))
            
        for i, (k, v) in enumerate(attr_list):
            command.append(f"   {k}{v} +")
            
        if obj_type != "QMGR":
            command.append("   REPLACE")
        else:
            command[-1] = command[-1].rstrip(' +')
            
        final_output.append("\n".join(command))
    return "\n\n".join(final_output)

# --- INITIALISATION ---
if 'master_script' not in st.session_state:
    st.session_state.master_script = ""

# --- INTERFACE ---
st.set_page_config(page_title="MQ Mass Importer", layout="wide")
st.title("🚀 MQ Mass Import Creator (V5 -> V8)")

with st.sidebar:
    st.header("⚙️ Paramètres du Projet")
    # On demande le numéro du MT
    mt_number = st.text_input("Numéro du Queue Manager (ex: 02, 03...)", value="01")
    filename_output = f"import_MT{mt_number}.mqsc"
    
    st.divider()
    st.header("📦 Mon Script de Masse")
    st.info(f"Fichier cible : **{filename_output}**")
    
    if st.button("🗑️ Réinitialiser le script"):
        st.session_state.master_script = ""
        st.rerun()
    
    st.download_button(
        label="📥 TÉLÉCHARGER LE SCRIPT COMPLET",
        data=st.session_state.master_script,
        file_name=filename_output,
        mime="text/plain",
        disabled=(st.session_state.master_script == "")
    )

c1, c2 = st.columns(2)
with c1:
    obj_selected = st.selectbox("Type d'objet à ajouter :", ["QUEUE", "CHANNEL", "PROCESS", "QMGR"])
    src = st.text_area("Colle la conf V5 ici :", height=300)
    
    if st.button("✨ Transformer et Ajouter") and src:
        new_conf = transform_mq_clean(src, obj_selected)
        separator = f"\n\n* {'='*50}\n* OBJET : {obj_selected} | SOURCE : MT{mt_number}\n* {'='*50}\n\n"
        st.session_state.master_script += separator + new_conf
        st.success(f"Config ajoutée au script MT{mt_number} !")

with c2:
    st.subheader(f"Aperçu du script : {filename_output}")
    if st.session_state.master_script:
        st.code(st.session_state.master_script, language="sql")
    else:
        st.info("Ajoute des configurations pour générer le script.")
