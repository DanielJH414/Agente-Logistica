from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from app_service import ask_question, get_document_payload, get_documents_dir, get_runtime

st.set_page_config(page_title="Agente Logística", page_icon="📦", layout="wide")

if "runtime" not in st.session_state:
    st.session_state.runtime = None

if "initializing" not in st.session_state:
    st.session_state.initializing = False

runtime = st.session_state.runtime

st.title("Agente de IA para documentos logísticos")

with st.sidebar:
    st.header("Estado")
    if st.session_state.initializing:
        st.info("Iniciando el motor RAG y sincronizando con OCI...")
    elif runtime is None:
        st.info("El motor RAG y la sincronización OCI están pendientes. Pulsa 'Actualizar motor' para iniciar.")
    else:
        st.write(f"Documentos base: {get_documents_dir()}")
        st.write("Documentos indexados")
        if runtime.get("init_error"):
            st.warning(f"Oracle no está disponible en este momento: {runtime['init_error']}")
        if runtime.get("loading_error"):
            st.error(f"Error al inicializar el motor: {runtime['loading_error']}")

    if st.button("Actualizar motor"):
        st.session_state.initializing = True
        with st.spinner("Actualizando el motor RAG y la sincronización con OCI..."):
            st.session_state.runtime = get_runtime()
            runtime = st.session_state.runtime
        st.session_state.initializing = False

    st.header("Explorar documentos")
    document_payload = get_document_payload()
    for folder in document_payload.get("folders", []):
        with st.expander(folder["title"], expanded=False):
            for file in folder.get("files", []):
                url = file.get("url", "#")
                if file["name"].lower().endswith(".pdf"):
                    st.markdown(f'- <a href="{url}" target="_blank">{file["name"]}</a>', unsafe_allow_html=True)
                else:
                    st.markdown(f'- <a href="{url}">{file["name"]}</a>', unsafe_allow_html=True)

with st.form(key="ask_form"):
    question = st.text_input(
        "Escribe tu pregunta sobre documentos, procesos o políticas de la empresa",
        key="question_input",
    )
    submitted = st.form_submit_button("Consultar")

if submitted and question.strip():
    if runtime is None:
        with st.spinner("Inicializando el motor RAG..."):
            st.session_state.runtime = get_runtime()
            runtime = st.session_state.runtime

    with st.spinner("Buscando respuestas en los documentos..."):
        response = ask_question(question)

    st.subheader("Respuesta")
    st.write(response["answer"])

    if response.get("sources"):
        st.subheader("Fuentes")
        for source in response["sources"]:
            st.write(f"- {source['label']} ({source['caption']})")
