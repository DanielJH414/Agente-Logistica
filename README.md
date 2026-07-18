# Agente-Logistica

Este proyecto consiste en el desarrollo de un agente de IA escalable utilizando técnicas de Retrieval-Augmented Generation (RAG) para optimizar el acceso y procesamiento de información corporativa de una empresa de logística, el agente de IA va a ser público para los integrantes de la empresa, con el fin de que responder distintas dudas sobre temas de la empresa (financieros, logísticos, y de servicio al cliente).


# Abrir y ejecutar el proyecto

Cuando hayas descargado el proyecto necesitas preparar tu entorno virtual para el backend (especificamente para trabajar en langchain) para ello se siguen los siguientes pasos:

<h2> venv en windows </h2>
```powershell
python -m venv .venv-gemini-3
.\.venv-gemini-3\Scripts\activate 
```

# Instalaciones en la terminal

después de activar el entorno de trabajo el siguiente paso es la instalación de paquetes necesarios para que pueda funcionar

<h2> Librerías para la extracción de formatos </h2>
```powershell
pip install pymupdf  (PDF)
pip install python-docx  (Word)
pip install pandas (Excel/CSV)

```

<h2> Librería para calcular los chunks </h2>

```powershell
pip install tiktoken 

```

<h2> Instalación de Chroma </h2>

´´´powershell
pip install chromadb´´´