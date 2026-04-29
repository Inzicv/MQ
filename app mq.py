import streamlit as st
import re

def transform_mq_clean(input_text, obj_type):
    type_map = {"QUEUE": "QLOCAL", "CHANNEL": "CHANNEL", "PROCESS": "PROCESS", "QMGR": "QMGR"}
    
    # On ne vire QUE le strict nécessaire (stats dynamiques et dates)
    # Tout le reste (DEFPRESP, CLWL..., etc.) sera conservé
    to_ignore = [
        'CURDEPTH', 'IPPROCS', 'OPPROCS', 'LPIPROCS', 'LOPPROCS',
        'ALTDATE', 'ALTTIME', 'CRDATE', 'CRTIME'
    ]
    
    blocks = [b.strip() for b in input_text.split('\n\n') if b.strip()]
    final_output = []
    
    for block in blocks:
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

        # --- RECONSTRUCTION ---
        header = f"ALTER QMGR +" if obj_type == "QMGR" else f"DEFINE {actual_type}({obj_name}) +"
        command = [header]

        # Forçage MCAUSER pour les Channels
        if obj_type == "CHANNEL":
            attrs["MCAUSER"] = "(MQM.ADMIN2)"

        attr_list = list(attrs.items())
        for i, (k, v) in enumerate(attr_list):
            command.append(f"   {k}{v} +")

        if obj_type != "QMGR":
            command.append("   REPLACE")
        else:
            command[-1] = command[-1].rstrip(' +')

        final_output.append("\n".join(command))
    
    return "\n\n".join(final_output)
    
# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="MQ Migration HPN", layout="wide")
st.title("🚀 MQ Migration Transformer V5 -> V8")

with st.sidebar:
    st.header("Paramètres")
    obj_selected = st.selectbox("Type d'objet source :", ["QUEUE", "CHANNEL", "PROCESS", "QMGR"])
    ext = st.radio("Format de sortie :", [".txt", ".mqsc"])

c1, c2 = st.columns(2)
with c1:
    src = st.text_area("Colle ta conf V5 ici :", height=400)
    up = st.file_uploader("Ou upload un fichier", type="txt")

data = up.read().decode("utf-8") if up else src

with c2:
    if data:
        res = transform_mq_clean(data, obj_selected)
        st.code(res, language="sql")
        st.download_button("📥 Télécharger", res, f"MIGRATE_{obj_selected}{ext}")
    else:
        st.info("En attente de données...")
