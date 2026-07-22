import sqlite3
import os

# Obtiene la ruta absoluta de la carpeta actual donde está database.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define la ruta completa para que el archivo .db quede guardado aquí mismo
DB_NAME = os.path.join(BASE_DIR, "project_maintenance.db")

def get_connection():
    """Crea y retorna una conexión a la base de datos SQLite en la carpeta Base de datos."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# Resto de tus funciones de creación de tablas (init_db, etc.)
def init_db():
    """Crea las tablas necesarias para el mantenimiento y los logs."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Tabla para el Pipeline de Actualización (Control de archivos locales)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_registry (
            file_path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            last_modified TIMESTAMP NOT NULL,
            last_indexed TIMESTAMP NOT NULL
        )
    """)

    # 2. Tabla para el Historial de Conversaciones / Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_query TEXT NOT NULL,
            agent_response TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 3. Tabla para el Feedback del usuario
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id INTEGER,
            rating INTEGER, -- Ej: 1 para pulgar arriba, 0 o -1 para pulgar abajo
            comment TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (log_id) REFERENCES chat_logs(id)
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_feedback_log_id ON user_feedback(log_id)")

    conn.commit()
    conn.close()
    print("Base de datos y tablas inicializadas correctamente.")


def create_chat_log(user_query: str, agent_response: str) -> int:
    """Guarda una interacción y devuelve el identificador que usará el feedback."""
    if not user_query.strip() or not agent_response.strip():
        raise ValueError("La pregunta y la respuesta no pueden estar vacías.")

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO chat_logs (user_query, agent_response) VALUES (?, ?)",
            (user_query, agent_response),
        )
        return int(cursor.lastrowid)


def save_feedback(log_id: int, rating: int, comment: str | None = None) -> None:
    """Guarda o actualiza la calificación de una interacción."""
    if rating not in (-1, 1):
        raise ValueError("La calificación debe ser 1 o -1.")

    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM chat_logs WHERE id = ?", (log_id,)).fetchone() is None:
            raise ValueError("La interacción indicada no existe.")

        conn.execute(
            """
            INSERT INTO user_feedback (log_id, rating, comment)
            VALUES (?, ?, ?)
            ON CONFLICT(log_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment,
                timestamp = CURRENT_TIMESTAMP
            """,
            (log_id, rating, comment),
        )

if __name__ == "__main__":
    init_db()