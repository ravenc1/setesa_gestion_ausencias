# Guía de despliegue — SETESA Workflow

Esta guía describe cómo pasar del entorno local a una instalación operativa con
**Streamlit + PostgreSQL (Supabase)**, incluyendo variables, migraciones,
cifrado, respaldo, integridad de PDF y CI.

> **Regla de oro:** antes de cualquier migración sobre datos reales ejecute un
> respaldo y conserve la `FERNET_KEY`. Sin esa clave, los campos cifrados no se
> pueden recuperar.

---

## 1. Arquitectura de despliegue

```
Navegador
   │ HTTPS
   ▼
Streamlit (app.py)
   │ psycopg2 (escrituras) + SQLAlchemy (lecturas)
   ▼
PostgreSQL / Supabase
```

- La aplicación no guarda estado de sesión en la base: usa `st.session_state`.
- Los PDFs y las firmas temporales se escriben en `storage/`.
- La explicación y las tres firmas se guardan **cifradas** con Fernet.
- El PDF oficial se sella con SHA-256 y el sello se persiste en
  `solicitud.pdf_hash`.

---

## 2. Requisitos

| Componente | Versión / nota |
|---|---|
| Python | 3.13 |
| PostgreSQL | 14 o superior (Supabase cumple) |
| Dependencias | `requirements.txt` |
| Navegador | Chrome, Edge o Firefox actualizado |

Dependencias relevantes para los RNF:

- `cryptography==50.0.2` — cifrado Fernet.
- `SQLAlchemy==2.1.6` — motor de lectura para pandas.
- `psycopg2-binary==2.9.13` — escrituras transaccionales.

---

## 3. Variables de configuración

La aplicación busca cada variable primero en el **entorno** (`.env` o variables
del sistema) y, si no existe, en los **secrets de Streamlit** (`st.secrets`).

### 3.1 `DATABASE_URL`

Cadena de conexión de PostgreSQL. En Supabase:

1. Abra **Project Settings → Database → Connection string**.
2. Para la aplicación use la cadena del **connection pooler** (puerto `6543`),
   que tolera mejor las conexiones cortas de Streamlit.
3. Para ejecutar migraciones/DDL use la conexión **directa** (puerto `5432`).

Ejemplo:

```text
postgresql://usuario:password@host:6543/postgres?sslmode=require
```

### 3.2 `FERNET_KEY`

Clave simétrica usada para cifrar la explicación y las firmas. Genérela una sola
vez:

```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Guárdela en `.env` (local) o en los secrets del proveedor (producción):

```text
FERNET_KEY="clave-generada"
```

Consideraciones:

- **No la versione.** `.env` y `.streamlit/secrets.toml` están en `.gitignore`.
- **No la rote** sin volver a cifrar los datos; una clave distinta produce
  `CifradoError: la FERNET_KEY no coincide`.
- Si se pierde, los campos cifrados son irrecuperables. Conserve una copia en el
  gestor de secretos de la organización.

### 3.3 Ejemplo de `.env` local

```dotenv
DATABASE_URL="postgresql://usuario:password@host:6543/postgres?sslmode=require"
FERNET_KEY="clave-generada"
```

### 3.4 Ejemplo de `.streamlit/secrets.toml`

Streamlit Community Cloud **no** convierte los secrets en variables de entorno;
la aplicación los lee directamente con `st.secrets`.

```toml
DATABASE_URL = "postgresql://usuario:password@host:6543/postgres?sslmode=require"
FERNET_KEY = "clave-generada"
```

No suba `secrets.toml` al repositorio.

---

## 4. Puesta en marcha local

```powershell
# 1. Entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Dependencias
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. Configuración
Copy-Item .env.example .env
# Edite .env con DATABASE_URL y FERNET_KEY

# 4. Aplicación
.\venv\Scripts\streamlit run app.py
```

La app queda disponible en `http://localhost:8501`.

---

## 5. Preparación de la base de datos

### 5.1 Base nueva

Ejecute el DDL completo:

```powershell
psql "$env:DATABASE_URL" -f docs/schema.sql
```

Esto crea roles, usuarios, solicitudes, historial, vigencia, feriados, índices y
la semilla de feriados 2025–2027. Los usuarios deben crearse aparte con
`src.core.security.hash_password()` o mediante el script de contraseñas.

### 5.2 Base existente: orden obligatorio

```powershell
# 0. Respaldo lógico (obligatorio antes de migrar)
.\venv\Scripts\python.exe scripts\backup_datos.py

# 1. Historial y normalización de estados
.\venv\Scripts\python.exe scripts\migracion_fase1.py

# 2. Vigencia y auditoría
.\venv\Scripts\python.exe scripts\migracion_fase3.py

# 3. Vacaciones y feriados
.\venv\Scripts\python.exe scripts\migracion_fase5.py

# 4. Columnas de sello + cifrado de registros heredados
.\venv\Scripts\python.exe scripts\migracion_fase6.py --cifrar-existentes
```

La migración de Fase 6:

- agrega `solicitud.pdf_hash` y `solicitud.pdf_hash_fecha`;
- con `--cifrar-existentes`, cifra `explicacion` y las firmas que aún estén en
  texto claro;
- sella los PDFs existentes que tengan ruta pero no hash.

Es idempotente. En ejecuciones posteriores use el script **sin**
`--cifrar-existentes` para no volver a recorrer datos ya cifrados:

```powershell
.\venv\Scripts\python.exe scripts\migracion_fase6.py
```

> El respaldo JSON anterior a la migración contiene los datos en claro. Guárdelo
> en un lugar seguro y con acceso restringido.

---

## 6. Cifrado en reposo

| Campo | Tratamiento |
|---|---|
| `solicitud.explicacion` | Fernet, prefijo `fernet:` |
| `solicitud.firma_empleado` | Fernet, prefijo `fernet:` |
| `solicitud.firma_jefe_gtc` | Fernet, prefijo `fernet:` |
| `solicitud.firma_gerencia` | Fernet, prefijo `fernet:` |

- El prefijo permite distinguir datos cifrados de registros heredados en claro.
- La lectura descifra solo al mostrar o generar el PDF; la base conserva el
  texto cifrado.
- Las pruebas unitarias verifican el ciclo cifrar/descifrar y el rechazo con una
  clave distinta.
- El respaldo posterior a la migración contiene los valores cifrados; el
  respaldo anterior contiene texto claro.

---

## 7. Integridad del PDF

Cada vez que se genera un PDF oficial:

1. Se calcula su SHA-256.
2. Se guarda en `solicitud.pdf_hash` y `solicitud.pdf_hash_fecha`.
3. Se escribe un sidecar `*.pdf.sha256` junto al archivo.
4. El dashboard muestra si el archivo coincide con el sello.

Verificación manual en Linux/macOS:

```bash
cd storage/pdf
sha256sum -c accion_8_Ricardo_Arias_1d.pdf.sha256
```

En PowerShell:

```powershell
Get-FileHash storage\pdf\archivo.pdf -Algorithm SHA256
# Compare con solicitud.pdf_hash
```

Si el estado es `alterado`, regenere el PDF desde el dashboard o con
`generar_pdf_solicitud(id_solicitud)`; el nuevo archivo se vuelve a sellar.

> En Streamlit Community Cloud el sistema de archivos es efímero. Un PDF puede
> desaparecer tras un reinicio; la aplicación lo regenera desde la base. Para
> conservar archivos entre despliegues use un volumen persistente o almacenamiento
> externo.

---

## 8. Despliegue en Streamlit Community Cloud

1. Suba el repositorio a GitHub (sin `.env` ni `secrets.toml`).
2. En Streamlit Cloud, cree una app apuntando a `app.py`.
3. Seleccione Python 3.13.
4. En **Settings → Secrets**, pegue:

   ```toml
   DATABASE_URL = "..."
   FERNET_KEY = "..."
   ```

5. Despliegue y abra la URL pública.
6. Ejecute una vez las migraciones desde un entorno con acceso a la base
   (no es necesario hacerlo desde la app).

Recomendaciones:

- Use la conexión *pooler* de Supabase para la app.
- No ejecute DDL desde Streamlit Cloud.
- Programe respaldos de Supabase y copie los JSON fuera del proyecto.
- Revise `storage/logs/setesa.log` solo en entornos con disco persistente; en
  Streamlit Cloud los logs se pierden al reiniciar. Consulte también los logs del
  panel de Streamlit.

---

## 9. Despliegue en servidor propio, VM o contenedor

Requisitos:

- Python 3.13 y dependencias instaladas.
- Variables de entorno `DATABASE_URL` y `FERNET_KEY`.
- Disco persistente para `storage/` si desea conservar PDFs y logs.

Ejemplo con systemd (Linux):

```ini
[Unit]
Description=SETESA Workflow
After=network.target

[Service]
WorkingDirectory=/opt/setesa/proyecto_setesa
EnvironmentFile=/opt/setesa/.env
ExecStart=/opt/setesa/venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
User=setesa

[Install]
WantedBy=multi-user.target
```

Detrás de un proxy inverso (Nginx/Caddy), habilite HTTPS y reenvíe a
`127.0.0.1:8501`.

---

## 10. Integración continua (GitHub Actions)

El workflow `.github/workflows/ci.yml` se ejecuta en cada push o pull request a
`main`:

1. instala dependencias;
2. compila `src`, `tests`, `scripts` y `app.py`;
3. ejecuta `pytest`.

Sin `DATABASE_URL`, las pruebas de integración se **omiten** automáticamente.
`tests/conftest.py` genera una `FERNET_KEY` efímera para las pruebas unitarias,
por lo que el CI no necesita secretos.

Para ejecutar la suite completa con base real, hágalo localmente o en un entorno
controlado:

```powershell
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe tests\smoke_test.py
```

---

## 11. Checklist de puesta en producción

- [ ] `DATABASE_URL` y `FERNET_KEY` configuradas fuera del repositorio.
- [ ] Respaldo previo a cualquier migración.
- [ ] Migraciones 1, 3, 5 y 6 ejecutadas en orden.
- [ ] `scripts/migracion_fase6.py --cifrar-existentes` ejecutado una vez.
- [ ] Clave Fernet respaldada en el gestor de secretos.
- [ ] Al menos un usuario por rol con contraseña PBKDF2.
- [ ] Smoke test en verde contra la base de producción/staging.
- [ ] CI en verde en GitHub Actions.
- [ ] Respaldo automático de Supabase programado.
- [ ] Logs y PDFs con retención definida.
- [ ] HTTPS habilitado y acceso al panel restringido.

---

## 12. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| «Falta DATABASE_URL en .env o en los secrets» | Variable ausente | Configurar `.env` o `st.secrets` |
| `CifradoError: falta FERNET_KEY` | Clave ausente | Generar y configurar `FERNET_KEY` |
| `CifradoError: la FERNET_KEY no coincide` | Clave distinta a la usada al cifrar | Restaurar la clave original; no hay recuperación sin ella |
| `malformed array literal` | Consulta con array incompatible | Actualizar al código de Fase 6 (roles protegidos con `NOT IN`) |
| El PDF figura como `alterado` | Archivo modificado o reemplazado | Regenerar el PDF y verificar el nuevo sello |
| El PDF desapareció tras reiniciar | Filesystem efímero | Regenerar desde el dashboard o usar disco persistente |
| `pandas only supports SQLAlchemy...` | Conexión DBAPI2 antigua | Verificar que las lecturas usen `get_engine()` |
| Login rechazado | `estado_vigencia = FALSE` | Reactivar desde el panel de Gerencia |
| Las pruebas de integración se omiten | No hay `DATABASE_URL` | Configurar la variable y repetir |

---

## 13. Referencias internas

- `README.md` — instalación y uso.
- `docs/ESTRUCTURA.md` — arquitectura y módulos.
- `docs/CHECKLIST_AVANCE.md` — estado, hallazgos y evidencias.
- `docs/schema.sql` — DDL completo.
- `scripts/backup_datos.py` — respaldo lógico.
- `scripts/migracion_fase6.py` — sello y cifrado.
