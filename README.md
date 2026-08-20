# Servicio de Transacciones — Demo SRE (versión SIN SSE)

App de ejemplo en **FastAPI + PostgreSQL** que reproduce, de forma controlada,
un incidente de **agotamiento del pool de conexiones** (connection pool
exhaustion). Diseñada para la demo "From Incident to Agentic Resolution"
donde **GitHub Copilot** investiga, corrige y valida el fallo.

El fallo se activa con una variable de entorno (`FAULT_MODE`), así puedes
mostrar el "antes y después" sin editar código en vivo.

---

## Requisitos

- Python 3.10+
- Docker (para levantar PostgreSQL sin instalarlo a mano)

---

## Puesta en marcha (5 pasos)

### 1. Levantar PostgreSQL con Docker
```bash
docker compose up -d
```
Esto arranca PostgreSQL en `localhost:5432` con usuario `demo`, contraseña
`demo`, base `demodb`.

### 2. Instalar dependencias de Python
```bash
pip install -r requirements.txt
```

### 3. Configurar la conexión
```bash
export DATABASE_URL="postgresql://demo:demo@localhost:5432/demodb"
```
(En Windows PowerShell: `$env:DATABASE_URL="postgresql://demo:demo@localhost:5432/demodb"`)

### 4. Arrancar el servicio (modo SANO)
```bash
export FAULT_MODE=none
uvicorn app.main:app --reload
```
Abre http://localhost:8000 — verás el servicio online. La documentación
interactiva está en http://localhost:8000/docs

### 5. Correr las pruebas
```bash
pytest -v
```
Con el código sano, las 5 pruebas pasan.

---

## Los modos de fallo (`FAULT_MODE`)

Cambia la variable de entorno y reinicia la app para activar cada escenario:

| Modo | Qué hace | Para qué sirve en la demo |
|------|----------|---------------------------|
| `none` | Todo funciona bien | Estado inicial sano / estado final tras la corrección |
| `pool_leak` | Las conexiones no se devuelven al pool (el bug principal) | El incidente central de la propuesta |
| `pool_tiny` | Pool de tamaño 1, se satura enseguida | Variante alterna para ensayar |
| `slow_query` | Cada consulta tarda 2s de más | Variante para mostrar latencia sin errores duros |

### Provocar el incidente en vivo
Con la app corriendo en un modo de fallo, en otra terminal:
```bash
python generar_carga.py --peticiones 50 --concurrencia 15
```
Verás la tasa de error y la latencia dispararse. En modo `none`, todas
las peticiones pasan.

---

## Guion sugerido para la demo

1. **Mostrar el servicio sano.** Arranca en `FAULT_MODE=none`, corre
   `generar_carga.py`, muestra 0% de error. "Así se ve en un día normal."

2. **Provocar el incidente.** Cambia a `FAULT_MODE=pool_leak`, reinicia,
   corre la carga otra vez. Ahora la tasa de error se dispara y la latencia
   sube. "Algo pasó. El servicio de transacciones se está degradando."

3. **Entra Copilot a investigar.** En la GitHub Copilot Desktop App, pídele
   que investigue el repositorio y encuentre la causa raíz. La pista está en
   `app/database.py`, en la función `get_db()`.

4. **Copilot propone la corrección.** El arreglo es asegurar que la conexión
   siempre se cierre (que el `finally` llame a `db.close()` en todos los casos).

5. **Aprobación humana + validación.** Apruebas el cambio, Copilot corre
   `pytest`, las pruebas pasan.

6. **Cierre.** Copilot genera el Postmortem en un Gist.

---

## ¿Dónde está exactamente el bug?

En `app/database.py`, función `get_db()`. En modo `pool_leak`, el bloque
`finally` **omite a propósito** el `db.close()`. Como la conexión no regresa
al pool, bajo carga concurrente el pool se agota y las nuevas peticiones
esperan hasta el timeout.

**La corrección correcta:** cerrar siempre la sesión en el `finally`, sin
importar el modo. Ese es el "fix" que Copilot debe proponer.

---

## Estructura del proyecto

```
fastapi-sre-demo/
├── app/
│   ├── main.py          # API FastAPI (endpoints)
│   └── database.py      # Pool de conexiones + el bug conmutable
├── tests/
│   ├── conftest.py      # Prepara la BD antes de las pruebas
│   └── test_transactions.py  # Pruebas (la de resiliencia valida el fix)
├── generar_carga.py     # Genera carga para provocar el incidente
├── docker-compose.yml   # PostgreSQL con un comando
├── requirements.txt
└── README.md
```

---

## Notas para presentar en Microsoft

- Se usa **PostgreSQL** (no SQLite) a propósito: el connection pool
  exhaustion es un fallo real de bases con servidor, y coincide con el
  escenario oficial de Microsoft (Octopets usa PostgreSQL).
- **SQLAlchemy** es la librería de acceso a datos, igual que en los ejemplos
  oficiales, así que el bug es idéntico al de un caso de producción real.
