from __future__ import annotations

import streamlit as st
from pathlib import Path

from app_service import ask_question, get_document_payload, get_documents_dir, get_runtime

st.set_page_config(page_title="Agente Logística", page_icon="📦", layout="wide")

if "runtime" not in st.session_state:
    st.session_state.runtime = None

runtime = st.session_state.runtime

st.title("Agente de IA para documentos logísticos")

with st.sidebar:
    st.header("Estado")
    st.write(f"Documentos base: {get_documents_dir()}")
    if runtime is None:
        st.info("El motor aún no se ha inicializado.")
    else:
        st.write(f"Sincronización OCI: {runtime['sync_summary']}")
        if runtime.get("init_error"):
            st.warning(f"Oracle no está disponible en este momento: {runtime['init_error']}")
        if runtime.get("loading_error"):
            st.error(f"Error al inicializar el motor: {runtime['loading_error']}")

    if st.button("Inicializar motor"):
        with st.spinner("Inicializando el motor RAG y la sincronización con OCI..."):
            st.session_state.runtime = get_runtime()
            runtime = st.session_state.runtime

    st.header("Explorar documentos")
    document_payload = get_document_payload()

    st.header("Explorar documentos")
    document_payload = get_document_payload()
    for folder in document_payload.get("folders", []):
        with st.expander(folder["title"], expanded=False):
            for file in folder.get("files", []):
                st.write(f"- {file['name']}")

question = st.text_area("Escribe tu pregunta sobre documentos, procesos o políticas", height=120)
if st.button("Consultar") and question.strip():
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

    st.caption(f"Sincronización previa: {response['sync_summary']}")
