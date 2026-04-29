import streamlit as st
import re

def transform_mq_clean(input_text, obj_type):
    type_map = {"QUEUE": "QLOCAL", "CHANNEL": "CHANNEL", "PROCESS": "PROCESS", "QMGR": "QMGR"}
    to_ignore = ['CURDEPTH', 'IPPROCS', 'OPPROCS', 'LPIPROCS', 'LOPPROCS', 'ALTDATE', 'ALTTIME', 'CRDATE', 'CRTIME']
    
    # 1. Découpage par les codes AMQ pour séparer chaque canal
    # On utilise re.split pour créer une liste d'objets propres
    raw_blocks = re.split(r'AMQ\d{4}:.*?\n', input_text)
    
    final_output = []
    
    for block in raw_blocks:
        # Nettoyage des résidus OutsideView et invite MQSC
        block = block.replace("MQSC >", "").strip()
        if not block or len(block) < 10:
            continue
            
        # 2. REGEX AMÉLIORÉE : 
        # On capture les Clé(Valeur) ou Clé seule, même avec des sauts de ligne (\s*)
        pattern = r'([A-Z0-9]{3,})\s*\((.*?)\)|([A-Z0-9]{5,})'
        matches = re.findall(pattern, block, re.DOTALL)
        
        attrs = {}
        obj_name = ""
        actual_type = type_map.get(obj_type, "QLOCAL")
        found_main_obj = False
        
        for m in matches:
            key = m[0] if m[0] else m[2]
            val = m[1] if m[0] else None
            
            if not key or key in to_ignore: 
                continue
                
            clean_val = "" if (val is None or val.strip() == "") else val.strip()

            # Identification du nom (ex: CHANNEL(CH.MSDD.MT01))
            if key == obj_type:
                # SI LE NOM EST UN ASTERISQUE, ON IGNORE LE BLOC COMPLET
                if clean_val == "*":
                    found_main_obj = False
                    break 
                
                obj_name = clean_val
                found_main_obj = True
                continue
                
            # Identification spécifique du type (SDR, RCVR, SVRCONN...)
            if key == "CHLTYPE" or (key == "TYPE" and obj_type == "QUEUE"):
                actual_type = clean_val
                if obj_type == "QUEUE": continue # On ne garde pas TYPE pour les queues, on l'utilise pour le DEFINE
            
            # Stockage des attributs
            attrs[key] = f"({clean_val})" if val is not None else ""

        if not found_main_obj:
            continue

        # 3. RECONSTRUCTION DU SCRIPT V8
        # Pour les Channels, on précise le CHLTYPE juste après le nom
        if obj_type == "CHANNEL":
            header = f"DEFINE CHANNEL({obj_name}) CHLTYPE({actual_type}) +"
            attrs["MCAUSER"] = "(MQM.ADMIN)" # Ta règle de sécurité
            # On supprime CHLTYPE des attributs car il est déjà dans le header
            attrs.pop("CHLTYPE", None)
        elif obj_type == "QMGR":
            header = "ALTER QMGR +"
        else:
            header = f"DEFINE {actual_type}({obj_name}) +"

        command = [header]
        
        # Ajout de tous les attributs capturés
        attr_list = list(attrs.items())
        for i, (k, v) in enumerate(attr_list):
            command.append(f"   {k}{v} +")

        # Conclusion de la commande
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
