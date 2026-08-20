"""
Configuración de la base de datos y del pool de conexiones.

El comportamiento cambia según la variable de entorno FAULT_MODE:
  - "none"        -> Comportamiento correcto (baseline sano).
  - "pool_leak"   -> Fuga de conexiones: no se devuelven al pool (el bug de la demo).
  - "pool_tiny"   -> Pool diminuto + sin reciclado: se satura bajo carga.
  - "slow_query"  -> Cada consulta duerme, ocupando conexiones más tiempo del debido.

Esto permite ensayar varios escenarios sin editar código: solo se cambia
la variable de entorno y se reinicia la app.
"""

import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Cadena de conexión a PostgreSQL. En local, Docker expone Postgres en localhost:5432.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://demo:demo@localhost:5432/demodb",
)

# El "interruptor" del incidente. Por defecto, sin fallo.
FAULT_MODE = os.getenv("FAULT_MODE", "none").lower()

# ---------------------------------------------------------------------------
# Configuración del engine y el pool según el modo de fallo.
# ---------------------------------------------------------------------------

if FAULT_MODE == "pool_tiny":
    # Pool minúsculo, sin conexiones extra y sin reciclado. Se satura rapidísimo.
    engine = create_engine(
        DATABASE_URL,
        pool_size=1,          # solo 1 conexión en el pool
        max_overflow=0,       # cero conexiones adicionales permitidas
        pool_timeout=5,       # si en 5s no hay conexión libre, lanza timeout
        pool_pre_ping=False,
    )
else:
    # Pool de tamaño normal para el resto de los modos.
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Dependencia de sesión de base de datos.
#
# Aquí vive el bug principal. FastAPI llama a esta función en cada petición
# que necesita la base de datos.
# ---------------------------------------------------------------------------

def get_db():
    """
    Provee una sesión de base de datos a los endpoints.

    En modo sano, la sesión SIEMPRE se cierra al final (bloque finally),
    devolviendo la conexión al pool.

    En modo 'pool_leak', se omite el cierre a propósito: cada petición se
    queda con su conexión, el pool se vacía, y las siguientes peticiones
    esperan hasta agotar el timeout -> latencia altísima y errores.
    """
    db = SessionLocal()
    try:
        if FAULT_MODE == "slow_query":
            # Simula una consulta lenta que retiene la conexión más tiempo.
            db.execute(text("SELECT pg_sleep(2)"))
        yield db
    finally:
        if FAULT_MODE == "pool_leak":
            # BUG INTENCIONAL: no cerramos la sesión.
            # La conexión NO regresa al pool -> fuga de conexiones.
            pass
        else:
            # Comportamiento correcto: la conexión regresa al pool.
            db.close()


def init_db():
    """Crea la tabla de ejemplo y algunos datos si no existen."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                amount NUMERIC(10, 2) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        # Insertar datos de ejemplo solo si la tabla está vacía.
        result = conn.execute(text("SELECT COUNT(*) FROM transactions"))
        count = result.scalar()
        if count == 0:
            for i in range(50):
                conn.execute(
                    text("INSERT INTO transactions (amount, status) "
                         "VALUES (:amount, :status)"),
                    {"amount": round(10.0 + i * 3.5, 2), "status": "completed"},
                )
        conn.commit()
