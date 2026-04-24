import streamlit as st
import re

# --- LOGIQUE DE TRANSFORMATION ---
def transform_mq_clean(input_text, obj_type):
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

        header = f"ALTER QMGR +" if obj_type == "QMGR" else f"DEFINE {actual_type}({obj_name}) +"
        command = [header, "   REPLACE +"]

        attr_list = list(attrs.items())
        if "CHLTYPE(SVRCONN)" in block and "MCAUSER" not in attrs:
            attr_list.append(("MCAUSER", "('MQM.ADMIN2')"))

        for i, (k, v) in enumerate(attr_list):
            line = f"   {k}{v}"
            if i < len(attr_list) - 1: line += " +"
            command.append(line)

        final_output.append("\n".join(command))
    return "\n\n".join(final_output)

# --- INTERFACE WEB (STREAMLIT) ---
st.set_page_config(page_title="MQ Migration Tool", page_icon="🚀")
st.title("🚀 HPN MQ Migration Transformer")
st.markdown("Transforme tes confs **V5 (Guardian)** en **V8 (OSS)** proprement.")

# 1. Choix du type
obj_type = st.selectbox("Quel type d'objet transformons-nous ?", ["QUEUE", "CHANNEL", "PROCESS", "QMGR"])

# 2. Input (Fichier ou Texte)
st.subheader("Source")
uploaded_file = st.file_uploader("Joindre un fichier .txt", type="txt")
text_input = st.text_area("Ou colle la conf ici :", height=200)

input_data = ""
if uploaded_file:
    input_data = uploaded_file.read().decode("utf-8")
elif text_input:
    input_data = text_input

# 3. Transformation
if input_data:
    st.subheader("Résultat")
    result = transform_mq_clean(input_data, obj_type)
    
    # Affichage aperçu
    st.code(result, language="sql")
    
    # Bouton de téléchargement
    st.download_button(
        label="📥 Télécharger le fichier .mqsc",
        data=result,
        file_name=f"MIGRATE_{obj_type}.mqsc",
        mime="text/plain"
    )
else:
    st.info("En attente de données (colle du texte ou joins un fichier).")