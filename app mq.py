import streamlit as st
import re

def transform_mq_clean(input_text, obj_type):
    # Mapping des types d'objets
    type_map = {"QUEUE": "QLOCAL", "CHANNEL": "CHANNEL", "PROCESS": "PROCESS", "QMGR": "QMGR"}
    to_ignore = ['CURDEPTH', 'IPPROCS', 'OPPROCS', 'ALTDATE', 'ALTTIME', 'CRDATE', 'CRTIME', 'LPIPROCS', 'LOPPROCS']

    blocks = [b.strip() for b in input_text.split('\n\n') if b.strip()]
    final_output = []

    for block in blocks:
        tokens = re.findall(r'([A-Z0-9]+)\s*(?:\((.*?)\))?', block)
        attrs = {}
        obj_name = ""
        actual_type = type_map.get(obj_type, "QLOCAL")

        for key, val in tokens:
            if key in to_ignore: continue
            if key == obj_type:
                obj_name = val
                continue
            if key == "TYPE" and obj_type == "QUEUE":
                actual_type = val
                continue
            attrs[key] = f"({val})" if val is not None else ""

        # --- RECONSTRUCTION DE LA COMMANDE ---
        if obj_type == "QMGR":
            command = ["ALTER QMGR +"]
        else:
            command = [f"DEFINE {actual_type}({obj_name}) +"]

        attr_list = list(attrs.items())
        
        # Injection MCAUSER pour les SVRCONN
        if "CHLTYPE(SVRCONN)" in block and "MCAUSER" not in attrs:
            attr_list.append(("MCAUSER", "('MQM.ADMIN2')"))

        # On boucle sur les attributs
        for i, (k, v) in enumerate(attr_list):
            line = f"   {k}{v}"
            # On met TOUJOURS un + après un attribut car le REPLACE (ou la suite) arrive
            line += " +"
            command.append(line)

        # --- LA CLAUSE FINALE ---
        if obj_type != "QMGR":
            command.append("   REPLACE") # Le REPLACE ferme la commande sans +
        else:
            # Pour le QMGR, on retire le dernier + du dernier attribut car pas de REPLACE
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
