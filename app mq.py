import streamlit as st
import re

def transform_mq_clean(input_text, obj_type):
    type_map = {"QUEUE": "QLOCAL", "CHANNEL": "CHANNEL", "PROCESS": "PROCESS", "QMGR": "QMGR"}
    to_ignore = [
        'CURDEPTH', 'IPPROCS', 'OPPROCS', 'LPIPROCS', 'LOPPROCS',
        'ALTDATE', 'ALTTIME', 'CRDATE', 'CRTIME'
    ]

    # Découpage par blocs (lignes vides)
    blocks = [b.strip() for b in input_text.split('\n\n') if b.strip()]
    final_output = []

    for block in blocks:
        # Regex pour attraper TOUT (paires ou mots seuls)
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
            # On met TOUJOURS un + car le REPLACE (ou l'attribut suivant) arrive derrière
            command.append(f"{line} +")

        # --- LA TOUCHE FINALE : LE REPLACE EN BAS ---
        if obj_type != "QMGR":
            command.append("   REPLACE") # Pas de + ici, c'est la fin !
        else:
            # Pour le QMGR (ALTER), on retire le + de la toute dernière ligne d'attribut
            command[-1] = command[-1].rstrip(' +')

        final_output.append("\n".join(command))
    
    return "\n\n".join(final_output)

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="MQ Conf Trandformer", layout="wide")
st.title("🚀 MQ Migration Tool : V5 -> V8")

with st.sidebar:
    st.header("Configuration")
    obj_selected = st.selectbox("Type d'objet :", ["QUEUE", "CHANNEL", "PROCESS", "QMGR"])
    ext = st.radio("Extension du fichier :", [".txt", ".mqsc"])

c1, c2 = st.columns(2)
with c1:
    src = st.text_area("Colle ta conf V5 ici :", height=500)
    up = st.file_uploader("Ou upload un fichier texte", type="txt")

data = up.read().decode("utf-8") if up else src

with c2:
    if data:
        res = transform_mq_clean(data, obj_selected)
        st.subheader("Résultat (V8)")
        st.code(res, language="sql")
        st.download_button("📥 Télécharger le résultat", res, f"MIGRATE_{obj_selected}{ext}")
    else:
        st.info("En attente de données source...")
