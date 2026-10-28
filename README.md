# SETESA Workflow

Sistema web para la digitalización de solicitudes de ausencia laboral
(«Acción de Personal») y el control de vigencia de usuarios de **SETESA**.

Implementa el flujo **Consultor Técnico → Coordinador GTC (banco) → Gerencia
SETESA**, genera el PDF oficial, captura firmas manuscritas digitalizadas y
aplica la baja lógica semestral de usuarios inactivos.

> Proyecto de graduación — Universidad Mariano Gálvez de Guatemala (PG2).
> El documento completo de la tesis está en `proyecto_doc/`.

---

## Stack

| Capa | Tecnología |
|---|---|
| Presentación | Streamlit + `streamlit-drawable-canvas` |
| Lógica de negocio | Python 3.13 |
| Documentos | FPDF |
| Datos | PostgreSQL (Supabase) |
| Pruebas | pytest + AppTest + smoke test E2E |

---

## Estructura

```
proyecto_setesa/
├── app.py                     # Punto de entrada y enrutador por rol
├── requirements.txt
├── pytest.ini
├── .env.example
├── src/
│   ├── core/
│   │   ├── auth.py            # Login y sesión
│   │   ├── database.py        # Conexión a PostgreSQL
│   │   ├── security.py        # PBKDF2 + RBAC
│   │   ├── workflow.py        # Estados y transiciones
│   │   ├── solicitudes.py     # Servicio transaccional + historial
│   │   ├── vigencia.py        # Baja lógica, auditoría y reactivación
│   │   ├── catalogos.py       # Tipos de ausencia
│   │   ├── utils.py           # Días hábiles
│   │   └── config.py          # Rutas de storage
│   ├── features/
│   │   ├── registro.py        # Panel del Consultor
│   │   ├── coordinador.py     # Portal de aprobaciones GTC
│   │   ├── dashboard.py       # Panel gerencial
│   │   └── vigencia.py        # Panel de auditoría y baja semestral
│   └── services/
│       ├── documentos.py      # PDF desde la BD + ruta_pdf
│       ├── motor_pdf.py       # Generación del PDF oficial
│       └── utils_firma.py     # Canvas <-> Base64 <-> PNG
├── scripts/
│   ├── backup_datos.py        # Respaldo lógico en JSON
│   ├── migracion_fase1.py     # Historial + normalización de estados
│   ├── migracion_fase3.py     # vigencia_log + restricciones
│   ├── vigencia_semestral.py  # Ejecución programada (cron/Task Scheduler)
│   └── hash_passwords.py      # Migración de contraseñas a PBKDF2
├── tests/
│   ├── test_utils.py
│   ├── test_workflow.py
│   ├── test_security.py
│   ├── test_utils_firma.py
│   ├── test_solicitudes_integration.py
│   ├── test_documentos.py
│   ├── test_vigencia.py
│   ├── test_app_smoke.py
│   └── smoke_test.py          # Prueba E2E manual
├── docs/
│   ├── ESTRUCTURA.md
│   ├── CHECKLIST_AVANCE.md    # Estado y plan por fases
│   ├── schema.sql             # DDL completo
│   └── evidencias/
├── storage/
│   ├── pdf/                   # PDFs emitidos
│   ├── firmas/                # Firmas temporales
│   └── backups/               # Respaldos JSON (no versionar)
└── proyecto_doc/              # Documento de tesis
```

---

## Requisitos

- Python **3.13**
- PostgreSQL 14+ (o una instancia de Supabase)
- Windows PowerShell (los comandos también funcionan en Linux/macOS)

---

## Instalación

```powershell
# 1. Crear y activar el entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar credenciales
Copy-Item .env.example .env
# Editar .env y colocar la cadena real de conexión:
# DATABASE_URL="postgresql://usuario:password@host:5432/basedatos"
```

> `.env` está en `.gitignore`. **Nunca** se versionan credenciales.

---

## Base de datos

### Opción A — Base nueva

```powershell
psql "$env:DATABASE_URL" -f docs/schema.sql
```

Crea `rol`, `usuario`, `solicitud`, `solicitud_historial`, `vigencia_log`,
índices y los tres roles base. Los usuarios se crean aparte (ver
`scripts/hash_passwords.py`).

### Opción B — Base existente (recomendado para este repositorio)

```powershell
# 1. Respaldo lógico previo (obligatorio)
.\venv\Scripts\python.exe scripts\backup_datos.py

# 2. Migración idempotente: historial, estados legados, CHECK e índices
.\venv\Scripts\python.exe scripts\migracion_fase1.py

# 3. Migración de vigencia: vigencia_log, CHECK e índices
.\venv\Scripts\python.exe scripts\migracion_fase3.py
```

La migración de la Fase 1:
- crea `solicitud_historial`;
- normaliza estados fuera de catálogo;
- registra el estado inicial de las solicitudes existentes;
- agrega `NOT NULL`, `CHECK` e índices sobre `estado_workflow`.

La migración de la Fase 3:
- crea `vigencia_log` para auditar depuraciones y reactivaciones;
- agrega el `CHECK` de acciones y el índice por fecha;
- garantiza que `usuario.ultima_actividad` sea `NOT NULL`.

---

## Ejecución

```powershell
.\venv\Scripts\streamlit run app.py
```

La aplicación abre en `http://localhost:8501`.

### Roles

| Rol | Panel | Acciones |
|---|---|---|
| `Consultor` | Formulario + historial | Registra, firma y descarga su solicitud |
| `Coordinador GTC` | Portal de aprobaciones | Otorga el visto bueno del banco |
| `Administrador` | Dashboard + vigencia | Autoriza, consulta métricas y depura usuarios |

> Las contraseñas se almacenan con PBKDF2-SHA256. Para crear usuarios, usar el
> hash generado por `src.core.security.hash_password()`.

---

## Flujo del workflow

```
Ingresada
   │  (registro del consultor, misma transacción)
   ▼
Pendiente de Firma Coordinador
   │  (visto bueno del Coordinador GTC)
   ▼
Pendiente de Aprobación Gerencia
   │  (autorización final de Gerencia)
   ▼
Finalizada
```

Reglas:

- Las transiciones están centralizadas en `src/core/workflow.py`.
- No se permiten saltos ni retrocesos.
- Cada cambio se registra en `solicitud_historial` con usuario, fecha y
  observación.
- El estado `Ingresada` es transitorio: se confirma junto con el paso a
  `Pendiente de Firma Coordinador` (decisión D-01, opción C).
- El Coordinador GTC y Gerencia deben **firmar en el canvas**: sin firma, la
  transición se rechaza (`FirmaRequerida`).
- El PDF oficial se genera desde la base con `src/services/documentos.py`, que
  guarda la ruta en `solicitud.ruta_pdf`.
- Cada login y cada escritura relevante actualizan `usuario.ultima_actividad`.

---

## Vigencia semestral (RF-05 / CU-06)

- Un usuario **activo** con más de 6 meses sin actividad pasa a baja lógica
  (`estado_vigencia = FALSE`); su historial y solicitudes se conservan.
- El rol `Administrador` y el usuario que ejecuta la depuración quedan
  excluidos, para no dejar el sistema sin acceso.
- Cada ejecución y reactivación se registra en `vigencia_log` (fecha, ejecutor,
  acción, afectados y detalle).
- La depuración se ejecuta automáticamente al iniciar sesión Gerencia si pasaron
  6 meses desde la última. También puede programarse:
  ```powershell
  .\venv\Scripts\python.exe scripts\vigencia_semestral.py
  ```
- Gerencia puede revisar candidatos, ejecutar el algoritmo, reactivar usuarios y
  consultar el historial desde el panel **Módulo de Auditoría y Vigencia**.
- Una sesión abierta de un usuario dado de baja se expulsa en el siguiente
  rerun de la aplicación.

---

## Pruebas

```powershell
# Suite automatizada (unitaria + integración + interfaz)
.\venv\Scripts\python.exe -m pytest

# Prueba E2E manual (workflow, PDF, historial; limpia sus datos)
.\venv\Scripts\python.exe tests\smoke_test.py
```

- Las pruebas de integración se **omiten** si no hay `DATABASE_URL`.
- `tests/test_app_smoke.py` usa `AppTest` de Streamlit para verificar que el
  login y los tres paneles se rendericen sin excepciones.
- `tests/test_documentos.py` verifica que el PDF final tenga las tres firmas y
  que `ruta_pdf` quede persistida.
- `tests/test_vigencia.py` cubre baja lógica, salvaguarda de administradores,
  auditoría, reactivación y login bloqueado con fechas controladas.
- `tests/test_app_smoke.py` incluye el rechazo de login de un usuario inactivo
  (QA-01).
- `tests/test_utils_firma.py` verifica nombres temporales únicos y limpieza.
- El smoke test crea y elimina sus propios registros; no deja datos de prueba.

---

## Scripts

| Script | Uso |
|---|---|
| `scripts/backup_datos.py` | Exporta `rol`, `usuario` y `solicitud` a `storage/backups/*.json` |
| `scripts/migracion_fase1.py` | Migración idempotente de la Fase 1 |
| `scripts/migracion_fase3.py` | Crea `vigencia_log` y sus restricciones |
| `scripts/vigencia_semestral.py` | Ejecuta la baja lógica si venció el semestre (`--forzar` para pruebas) |
| `scripts/hash_passwords.py` | Convierte contraseñas heredadas a PBKDF2 |

---

## Seguridad

- Contraseñas con PBKDF2-SHA256 (240 000 iteraciones, sal aleatoria).
- RBAC en la aplicación: cada módulo valida el rol antes de renderizar.
- Consultas del consultor filtradas por `id_usuario` (no accede a terceros).
- `.env` y `storage/` fuera del control de versiones.

> **Pendiente (Fase 6):** cifrado en reposo de motivos sensibles y firmas, y
> sello de integridad SHA-256 del PDF. Ver `docs/CHECKLIST_AVANCE.md`.

---

## Estado del proyecto

El avance detallado, las brechas y el plan por fases están en
**[`docs/CHECKLIST_AVANCE.md`](docs/CHECKLIST_AVANCE.md)**.

Fases completadas: **0 (línea base)**, **1 (coherencia del workflow)**,
**2 (firmas completas)** y **3 (vigencia robusta: baja lógica auditable,
ejecución semestral y reactivación)**.
Siguiente: **Fase 4 — dashboard completo (filtros, KPIs, descarga y exportación)**.

---

## Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| «Falta la variable DATABASE_URL» | Crear `.env` a partir de `.env.example` |
| Error al importar `streamlit_drawable_canvas` | Debe ejecutarse con `streamlit run`, no con `python app.py` |
| `pandas only supports SQLAlchemy...` | Advertencia conocida; se resuelve en la Fase 6 migrando a SQLAlchemy |
| Usuario bloqueado | `estado_vigencia = FALSE` (baja lógica); Gerencia puede reactivarlo desde el panel de vigencia |
