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

        # Construction du header
        header = f"ALTER QMGR +" if obj_type == "QMGR" else f"DEFINE {actual_type}({obj_name}) +"
        command = [header, "   REPLACE +"]

        attr_list = list(attrs.items())
        # Injection MCAUSER pour les SVRCONN
        if "CHLTYPE(SVRCONN)" in block and "MCAUSER" not in attrs:
            attr_list.append(("MCAUSER", "('MQM.ADMIN2')"))

        for i, (k, v) in enumerate(attr_list):
            line = f"   {k}{v}"
            if i < len(attr_list) - 1: line += " +"
            command.append(line)

        final_output.append("\n".join(command))
    return "\n\n".join(final_output)

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="HPN MQ Migration", layout="wide")
st.title("🚀 MQ Migration Tool (V5 to V8)")

# Sidebar pour les options
with st.sidebar:
    st.header("Options de sortie")
    obj_type = st.selectbox("Type d'objet :", ["QUEUE", "CHANNEL", "PROCESS", "QMGR"])
    extension = st.radio("Format du fichier :", [".txt", ".mqsc"], index=0)

# Main
col1, col2 = st.columns(2)

with col1:
    st.subheader("Source (V5)")
    uploaded_file = st.file_uploader("Joindre un fichier", type="txt")
    text_input = st.text_area("Ou coller ici :", height=400)

input_data = uploaded_file.read().decode("utf-8") if uploaded_file else text_input

with col2:
    st.subheader("Résultat (V8)")
    if input_data:
        result = transform_mq_clean(input_data, obj_type)
        st.code(result, language="sql")
        
        # Nom du fichier dynamique
        output_filename = f"MIGRATE_{obj_type}{extension}"
        
        st.download_button(
            label=f"📥 Télécharger en {extension}",
            data=result,
            file_name=output_filename,
            mime="text/plain"
        )
    else:
        st.info("Colle ou upload des données pour voir la magie.")