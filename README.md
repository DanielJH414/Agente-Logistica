# Agente-Logistica

Este proyecto consiste en el desarrollo de un agente de IA escalable utilizando técnicas de Retrieval-Augmented Generation (RAG) para optimizar el acceso y procesamiento de información corporativa de una empresa de logística, el agente de IA va a ser público para los integrantes de la empresa, con el fin de que responder distintas dudas sobre temas de la empresa (financieros, logísticos, y de servicio al cliente).

# Funcionamiento del proyecto

![Funcionamiento del proyecto](Fotos de la ejecución del proyecto/image.png)

# Abrir y ejecutar el proyecto

Te sitúas dentro de la carpeta backend para instalar las dependencias dentro de un entorno virtual. En Windows:

```powershell
python -m venv .venv-gemini-3
.\.venv-gemini-3\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si prefieres instalar las dependencias manualmente, usa estos comando en la terminal:

```powershell
python -m pip install streamlit torchvision
```

# Modelos de IA
```powershell
python -m pip install cohere 
python -m pip install groq
```

# lector de documentos
```powershell
python -m pip install pypdf 
python -m pip install pdfplumber 
python -m pip install python-docx
python -m pip install openpyxl
```

# Base de datos vectorial
```powershell
python -m pip install chromadb 
```

# Generación de Embeddings
```poweshell
python -m pip install sentence-transformers 
```
## Dependencias de Python

Estas son las dependencias externas utilizadas por el backend:

| Paquete | Uso en el proyecto |
| --- | --- |
| `streamlit` | Ejecución de la interfaz web del proyecto. |
| `chromadb` | Almacén vectorial persistente para indexar y consultar los documentos. |
| `sentence-transformers` | Generación de embeddings para los documentos y las consultas. Utiliza el modelo `sentence-transformers/all-MiniLM-L6-v2`. |
| `torchvision` | Dependencia complementaria para ciertos componentes de procesamiento de modelos visuales y embeddings. |
| `cohere` | Reordenamiento (`rerank`) de los resultados recuperados. Es opcional si no se configura una clave de Cohere. |
| `groq` | Generación de respuestas mediante los modelos de Groq. Es opcional si no se configura una clave de Groq. |
| `openpyxl` | Lectura del contenido de archivos `.xlsx` y `.xls`. |
| `pypdf` | Extracción de texto y metadatos de archivos PDF. |
| `pdfplumber` | Método alternativo para extraer texto de archivos PDF. |
| `python-docx` | Lectura de documentos `.docx`. |
| `oci` | Conexión con Oracle Cloud Infrastructure Object Storage para descargar y sincronizar documentos. |
| `oracledb` | Conexión mediante wallet mTLS con Oracle Autonomous Database para el registro de archivos, conversaciones y feedback. |
| `python-dotenv` | Carga de variables de configuración desde el archivo `.env`. |

El proyecto también procesa archivos `.csv`, `.txt`, `.md`, `.json`, `.xml`, `.yaml` y `.yml` utilizando las herramientas de lectura incluidas en Python.

## Librerías estándar utilizadas

No necesitan instalación con `pip`:

- `oracledb`: conexión con Oracle Autonomous Database para el registro de archivos, conversaciones y feedback.
- `http.server`: servidor HTTP del backend.
- `json`, `pathlib`, `re`, `os`, `sys`, `datetime` y `urllib`: procesamiento de datos, rutas, texto y solicitudes HTTP.

## Configuración de las API

Para utilizar el reranking y la generación de respuestas, configura las claves de Cohere y Groq en `Backend/modelos/my_keys.py` o mediante el mecanismo de configuración que utilice tu entorno.

## Despliegue en Streamlit Cloud

Para desplegar la app en Streamlit Cloud, el punto de entrada debe ser el archivo `Backend/streamlit_app.py` y las siguientes variables deben configurarse como Secrets de Streamlit:

- `OPENAI_API_KEY` (si se usa por el flujo actual, aunque este proyecto usa Cohere/Groq)
- `COHERE_API_KEY`
- `GROQ_API_KEY`
- `ORACLE_USER`
- `ORACLE_PASSWORD`
- `ORACLE_DSN`
- `ORACLE_CONFIG_DIR`
- `ORACLE_WALLET_LOCATION`
- `ORACLE_WALLET_PASSWORD`
- `OCI_NAMESPACE`
- `OCI_BUCKET`
- `OCI_REGION`
- `OCI_PROFILE`
- `OCI_PREFIX`
- `DOCUMENTS_DIR`
- `VECTOR_STORE_DIR`
- `STATIC_DIR`

En Streamlit Cloud, el directorio de trabajo debe apuntar a la carpeta `Backend` o el repo debe tener el archivo de entrada correctamente referenciado. La app ahora resuelve rutas de forma segura mediante esas variables, y tolera fallos en Oracle/OCI para que el despliegue no se rompa por configuración incompleta.

## Configuración de Oracle Cloud Infrastructure

Durante las pruebas locales, configura el archivo de OCI en `~/.oci/config` y verifica que el perfil `DEFAULT` tenga permisos para leer objetos del bucket. No incluyas la clave privada ni otros secretos en el repositorio.

La sincronización utiliza estos valores por defecto:

| Configuración | Valor |
| --- | --- |
| `OCI_NAMESPACE` | `axtvg0vgl5uf` |
| `OCI_BUCKET` | `Documentos-Nexus` |
| `OCI_REGION` | `sa-bogota-1` |
| `OCI_PROFILE` | `DEFAULT` |
| `OCI_PREFIX` | vacío, usa todo el bucket |

Puedes sobrescribirlos mediante variables de entorno. Al iniciar el servidor, los documentos se descargan en `Backend/Documentos Nexus`, conservando las carpetas `Financiero`, `Responsables`, `Logística` y `Servicio al cliente`. Los cambios y eliminaciones remotos se reflejan después en ChromaDB.
