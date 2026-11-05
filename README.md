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
| Documentos | FPDF + sello SHA-256 |
| Seguridad | PBKDF2 + Fernet (`cryptography`) |
| Datos | PostgreSQL (Supabase) + SQLAlchemy |
| Pruebas | pytest + AppTest + smoke test E2E + GitHub Actions |

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
│   │   ├── database.py        # PostgreSQL: psycopg2 + SQLAlchemy
│   │   ├── security.py        # PBKDF2 + RBAC
│   │   ├── crypto.py          # Cifrado Fernet de datos sensibles
│   │   ├── logging_config.py  # Logging rotativo en storage/logs
│   │   ├── workflow.py        # Estados y transiciones
│   │   ├── solicitudes.py     # Servicio transaccional + historial
│   │   ├── vigencia.py        # Baja lógica, auditoría y reactivación
│   │   ├── catalogos.py       # Tipos de ausencia
│   │   ├── reportes.py        # Filtros, KPIs y exportación CSV
│   │   ├── feriados.py        # Catálogo de feriados
│   │   ├── vacaciones.py      # Saldo de vacaciones
│   │   ├── validaciones.py    # Reglas de fechas y saldo
│   │   ├── usuarios.py        # Usuarios por rol
│   │   ├── recordatorios.py   # Recordatorios al banco (R-11)
│   │   ├── gestion_usuarios.py # Altas, edición, bajas y auditoría (Fase 9)
│   │   ├── utils.py           # Días hábiles
│   │   └── config.py          # Rutas y variables de entorno/secrets
│   ├── features/
│   │   ├── registro.py        # Panel del Consultor
│   │   ├── coordinador.py     # Portal de aprobaciones GTC
│   │   ├── dashboard.py       # Panel gerencial + filtros + descargas
│   │   ├── feriados.py        # Administración de feriados
│   │   ├── vigencia.py        # Panel de auditoría y baja semestral
│   │   └── gestion_usuarios.py # Panel de IT: cuentas y auditoría (Fase 9)
│   └── services/
│       ├── documentos.py      # PDF desde la BD + ruta_pdf + descarga
│       ├── motor_pdf.py       # Generación del PDF oficial
│       └── utils_firma.py     # Canvas <-> Base64 <-> PNG
├── scripts/
│   ├── backup_datos.py        # Respaldo lógico en JSON
│   ├── migracion_fase1.py     # Historial + normalización de estados
│   ├── migracion_fase3.py     # vigencia_log + restricciones
│   ├── migracion_fase5.py     # saldo de vacaciones + feriados
│   ├── migracion_fase6.py     # sello SHA-256 + cifrado de datos heredados
│   ├── migracion_fase7.py     # rol Contabilidad (HU-03) + cuenta demo opcional
│   ├── migracion_fase8.py     # tabla recordatorio (R-11)
│   ├── migracion_fase9.py     # rol IT + usuario_log + cuenta demo opcional
│   ├── vigencia_semestral.py  # Ejecución programada (cron/Task Scheduler)
│   └── hash_passwords.py      # Migración de contraseñas a PBKDF2
├── tests/
│   ├── test_utils.py
│   ├── test_workflow.py
│   ├── test_security.py
│   ├── test_crypto.py         # Cifrado/descifrado y clave incorrecta
│   ├── test_utils_firma.py
│   ├── test_solicitudes_integration.py
│   ├── test_documentos.py
│   ├── test_vigencia.py
│   ├── test_reportes.py       # Filtros, KPIs y CSV
│   ├── test_dashboard_integration.py  # Repositorio + PDF final
│   ├── test_feriados.py       # Catálogo de feriados
│   ├── test_vacaciones.py     # Saldo de vacaciones
│   ├── test_validaciones.py   # Reglas de fechas y saldo
│   ├── test_app_smoke.py
│   ├── test_rbac_contabilidad.py  # HU-03: panel de solo lectura
│   ├── test_recordatorios.py      # R-11: envío, cooldown y atención
│   ├── test_gestion_usuarios.py   # Fase 9: altas, edición, bajas y auditoría
│   └── smoke_test.py          # Prueba E2E manual
├── docs/
│   ├── ESTRUCTURA.md
│   ├── CHECKLIST_AVANCE.md    # Estado y plan por fases
│   ├── DESPLIEGUE.md          # Guía de producción y secrets
│   ├── schema.sql             # DDL completo
│   └── evidencias/
├── .github/workflows/ci.yml   # Compilación + pytest en cada push
├── storage/
│   ├── pdf/                   # PDFs emitidos + sellos .sha256
│   ├── firmas/                # Firmas temporales
│   ├── logs/                  # Logs rotativos (no versionar)
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

# 4. Generar la clave de cifrado y agregarla a .env como FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> `.env` está en `.gitignore`. **Nunca** se versionan credenciales ni la
> `FERNET_KEY`. Si se pierde la clave, los datos cifrados no se recuperan.
> Para Streamlit Community Cloud, defina `DATABASE_URL` y `FERNET_KEY` en
> **Secrets**; la app también los lee desde `st.secrets`.

---

## Base de datos

### Opción A — Base nueva

```powershell
psql "$env:DATABASE_URL" -f docs/schema.sql
```

Crea `rol`, `usuario`, `solicitud`, `solicitud_historial`, `recordatorio`,
`usuario_log`, `vigencia_log`, `feriado`, índices, los cinco roles base y la
semilla de feriados. Los usuarios se crean aparte (ver
`scripts/hash_passwords.py` o el panel de IT).

### Opción B — Base existente (recomendado para este repositorio)

```powershell
# 1. Respaldo lógico previo (obligatorio)
.\venv\Scripts\python.exe scripts\backup_datos.py

# 2. Migración idempotente: historial, estados legados, CHECK e índices
.\venv\Scripts\python.exe scripts\migracion_fase1.py

# 3. Migración de vigencia: vigencia_log, CHECK e índices
.\venv\Scripts\python.exe scripts\migracion_fase3.py

# 4. Migración de vacaciones y feriados: columna, tabla y semilla
.\venv\Scripts\python.exe scripts\migracion_fase5.py

# 5. Sello SHA-256 y cifrado de registros heredados (una sola vez)
.\venv\Scripts\python.exe scripts\migracion_fase6.py --cifrar-existentes

# 6. Recordatorios al banco (R-11)
.\venv\Scripts\python.exe scripts\migracion_fase8.py

# 7. Rol IT y auditoría de usuarios; con --usuario-demo crea la cuenta de prueba
.\venv\Scripts\python.exe scripts\migracion_fase9.py --usuario-demo
```

La migración de la Fase 1:
- crea `solicitud_historial`;
- normaliza estados fuera de catálogo;
- registra el estado inicial de las solicitudes existentes;
- agrega `NOT NULL`, `CHECK` e índices sobre `estado_workflow`.

La migración de la Fase 5:
- agrega `usuario.dias_vacaciones_asignados` (15 por defecto, `CHECK >= 0`);
- crea la tabla `feriado` con fecha única;
- siembra los feriados nacionales de 2025–2027.

La migración de la Fase 3:
- crea `vigencia_log` para auditar depuraciones y reactivaciones;
- agrega el `CHECK` de acciones y el índice por fecha;
- garantiza que `usuario.ultima_actividad` sea `NOT NULL`.

La migración de la Fase 6:
- agrega `solicitud.pdf_hash` y `solicitud.pdf_hash_fecha`;
- con `--cifrar-existentes`, cifra `explicacion` y las firmas en texto claro;
- sella los PDFs existentes que tengan ruta pero no hash.
- Es idempotente; en ejecuciones posteriores use el script sin el flag.

La migración de la Fase 7:
- crea el rol `Contabilidad` (idempotente);
- con `--usuario-demo`, agrega una cuenta de prueba de solo lectura.

La migración de la Fase 8:
- crea la tabla `recordatorio` y sus índices;
- no siembra datos: los recordatorios nacen de la operación real.

La migración de la Fase 9:
- crea el rol `IT` y la tabla `usuario_log` con sus índices;
- con `--usuario-demo`, agrega una cuenta IT temporal de prueba;
  cámbiela o elimínela antes de la entrega.

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
| `Administrador` | Dashboard + vigencia + feriados | Autoriza, consulta métricas, depura usuarios y administra feriados |
| `Contabilidad` | Repositorio de expedientes (solo lectura) | Consulta, filtra y descarga el PDF final con las tres firmas; no autoriza ni administra |
| `IT` | Gestión de usuarios | Crea y edita cuentas, aplica bajas/reactivaciones, resetea contraseñas y consulta la auditoría; no accede a firmas ni catálogos |

> Las contraseñas se almacenan con PBKDF2-SHA256. Las cuentas se crean desde el
> panel de **IT**; para migraciones masivas también puede usarse
> `src.core.security.hash_password()`.
>
> El **correo registrado** es el identificador de acceso y el destino de los
> recordatorios. Puede ser de SETESA (`@setesagt.com`), del banco (coordinadores
> GTC) o personal; no se exige un dominio específico. Las cuentas las crea
> IT, no hay autorregistro, y cada persona debe tener la suya para que
> su firma sea atribuible.

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
  guarda la ruta en `solicitud.ruta_pdf` y su sello SHA-256 en
  `solicitud.pdf_hash`.
- La explicación y las tres firmas se guardan **cifradas con Fernet** en la base;
  se descifran solo al mostrarlas o generar el PDF.
- Cada login y cada escritura relevante actualizan `usuario.ultima_actividad`.

---

## Recordatorio al banco (R-11)

- El consultor lo envía desde **Mis Solicitudes → Recordatorio al banco**,
  únicamente mientras el expediente está en `Pendiente de Firma Coordinador`.
- Se guarda en la tabla `recordatorio` con emisor, destinatario, correo
  histórico, mensaje, fecha y estado de atención. El mensaje se cifra con Fernet
  en reposo (RNF-01) y se descifra solo al mostrarlo.
- El Coordinador GTC ve un aviso con contador y la tabla de recordatorios en su
  bandeja; al firmar, quedan **atendidos** en la misma transacción.
- Se ofrece un enlace `mailto:` con asunto y cuerpo prellenados hacia el correo
  registrado del coordinador. No se envía correo automático: el sistema no
  depende de un servidor SMTP.
- **Cooldown de 24 h** por expediente para evitar duplicados.
- Los coordinadores del banco pueden registrarse con su correo corporativo o
  personal; el campo `correo_institucional` es el identificador de acceso y el
  destino de las notificaciones. Las cuentas las crea IT/Gerencia, nunca por
  autorregistro.

---

## Gestión de usuarios (Fase 9)

- Solo el rol **IT** accede al panel **👥 Gestión de Usuarios**; el resto de
  roles no ve la pestaña.
- **Usuarios**: listado con rol, vigencia, última actividad, días de vacaciones
  asignados/usados/disponibles; edición de nombre, correo, rol y días.
- **Crear usuario**: nombre, correo registrado (cualquier dominio válido), rol,
  días de vacaciones y contraseña inicial.
- **Acceso**: baja lógica y reactivación (la reactivación actualiza la última
  actividad para que la vigencia no lo dé de baja de inmediato) y reseteo de
  contraseña.
- **Auditoría**: cada acción se registra en `usuario_log` con ejecutor,
  afectado, fecha, acción y detalle.
- **Protecciones**: nadie puede desactivarse a sí mismo ni cambiarse el rol; no
  se puede dejar el sistema sin Administrador ni sin IT activo.
- **Política de contraseña**: mínimo 8 caracteres, con al menos una letra y un
  número.
- **IT está protegido** de la baja automática semestral, igual que Gerencia.

---

## Dashboard gerencial (RF-04 / HU-03)

- Filtros combinables por **nombre**, **estado**, **tipo de incidencia** y
  **rango de fechas** (se conservan las solicitudes cuyo periodo de ausencia se
  solapa con el rango elegido).
- Panel compartido: **Gerencia** autoriza y firma; **Contabilidad** solo consulta
  y descarga (HU-03), sin acceso a Vigencia ni Feriados.
- KPIs: total, ingresadas, pendientes de coordinador, pendientes de gerencia y
  finalizadas; distribución por estado y por tipo.
- Alertas in-app con el número de expedientes pendientes de firma.
- Tabla paginada (10/25/50/100 filas por página).
- **Descarga del PDF final** con las tres firmas (HU-03); si el archivo no
  existe, se regenera desde la base.
- **Verificación de integridad**: muestra si el PDF coincide con el sello
  SHA-256 registrado, si fue alterado o si aún no tiene sello.
- **Exportación CSV** del resultado filtrado, con BOM UTF-8 para abrirlo
  directamente en Excel.

La lógica de filtros, KPIs y exportación vive en `src/core/reportes.py`, sin
dependencias de Streamlit, y está cubierta por pruebas unitarias.

---

## Vacaciones y feriados (RF-01)

- Cada usuario tiene `dias_vacaciones_asignados` (15 por defecto) y el panel del
  consultor muestra **asignados, usados y disponibles** del año.
- El saldo se calcula como asignados menos los días solicitados como `VACACION`
  en el año de la solicitud.
- El catálogo `feriado` (tabla con fecha única) se excluye del cálculo de días
  hábiles. Gerencia lo administra desde la pestaña **Feriados**.
- La migración siembra los feriados nacionales de 2025, 2026 y 2027 (incluida la
  Semana Santa). Los años siguientes se agregan desde el panel.
- El servidor valida `fecha_fin >= fecha_inicio` y el saldo de vacaciones antes
  de insertar; el formulario muestra los mismos mensajes.
- El jefe GTC se selecciona entre los usuarios vigentes con rol Coordinador GTC.

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
  login y los cinco paneles se rendericen sin excepciones.
- `tests/test_crypto.py` cubre el ciclo cifrar/descifrar, la no recifra, los
  valores heredados en claro y el rechazo con una clave distinta.
- `tests/test_documentos.py` verifica que el PDF final tenga las tres firmas,
  que `ruta_pdf` quede persistida, que el sello SHA-256 detecte alteraciones y
  que la explicación/firma se guarden cifradas en reposo.
- `tests/test_vigencia.py` cubre baja lógica, salvaguarda de administradores,
  auditoría, reactivación y login bloqueado con fechas controladas.
- `tests/test_reportes.py` cubre los filtros (nombre, estado, tipo y rango de
  fechas), los KPIs y la exportación CSV.
- `tests/test_dashboard_integration.py` verifica el repositorio, los filtros
  sobre datos reales y la descarga del PDF final con tres firmas.
- `tests/test_feriados.py` cubre la semilla, el alta/baja y la actualización de
  nombre del catálogo.
- `tests/test_vacaciones.py` verifica el saldo, el descuento por solicitud, el
  rechazo por saldo insuficiente y la separación por año.
- `tests/test_validaciones.py` cubre fechas invertidas, nulas y rangos sin días
  hábiles.
- `tests/test_app_smoke.py` incluye el rechazo de login de un usuario inactivo
  (QA-01).
- `tests/test_rbac_contabilidad.py` verifica que Contabilidad solo consulte y
  descargue, sin autorizar ni acceder a Vigencia/Feriados (HU-03).
- `tests/test_recordatorios.py` cubre el envío al banco, el cooldown, la
  propiedad del expediente, el estado permitido y la atención al firmar (R-11).
- `tests/test_gestion_usuarios.py` cubre la política de correo/contraseña, el
  alta, la edición, la baja/reactivación, el reseteo, las protecciones y la
  auditoría (Fase 9).
- `tests/test_utils_firma.py` verifica nombres temporales únicos y limpieza.
- El smoke test crea y elimina sus propios registros; no deja datos de prueba.

---

## Scripts

| Script | Uso |
|---|---|
| `scripts/backup_datos.py` | Exporta `rol`, `usuario` y `solicitud` a `storage/backups/*.json` |
| `scripts/migracion_fase1.py` | Migración idempotente de la Fase 1 |
| `scripts/migracion_fase3.py` | Crea `vigencia_log` y sus restricciones |
| `scripts/migracion_fase5.py` | Agrega el saldo de vacaciones y el catálogo de feriados |
| `scripts/migracion_fase6.py` | Agrega columnas de sello; con `--cifrar-existentes` cifra datos heredados |
| `scripts/migracion_fase7.py` | Crea el rol Contabilidad; con `--usuario-demo` añade la cuenta de prueba (HU-03) |
| `scripts/migracion_fase8.py` | Crea la tabla `recordatorio` y sus índices (R-11) |
| `scripts/migracion_fase9.py` | Crea el rol IT y `usuario_log`; con `--usuario-demo` añade la cuenta IT de prueba (Fase 9) |
| `scripts/instalar_produccion.py` | Instalador limpio de producción (Fase 26): esquema, migraciones sin cuentas demo, bucket y primer usuario IT |
| `docs/DESPLIEGUE.md` §8b | Despliegue del prototipo en Render (plan gratuito) |
| `scripts/respaldo.py` | `respaldar` / `restaurar CARPETA --confirmar-reemplazo [--simular]`: respaldo completo de tablas y archivos (Fase 26) |
| `scripts/vigencia_semestral.py` | Ejecuta la baja lógica si venció el semestre (`--forzar` para pruebas) |
| `scripts/hash_passwords.py` | Convierte contraseñas heredadas a PBKDF2 |

---

## Seguridad e integridad

- Contraseñas con PBKDF2-SHA256 (240 000 iteraciones, sal aleatoria).
- RBAC en la aplicación: cada módulo valida el rol antes de renderizar.
- Consultas del consultor filtradas por `id_usuario` (no accede a terceros).
- **Cifrado en reposo** de `explicacion`, `firma_empleado`, `firma_jefe_gtc` y
  `firma_gerencia` con Fernet (AES-128-CBC + HMAC-SHA256). El prefijo `fernet:`
  distingue los datos cifrados de los heredados.
- La clave `FERNET_KEY` vive en `.env` o en los secrets del proveedor, nunca en
  la base ni en el repositorio.
- **Sello SHA-256** del PDF oficial, persistido en `solicitud.pdf_hash` y en un
  archivo `.pdf.sha256`; el dashboard detecta alteraciones.
- `.env`, `.streamlit/secrets.toml` y `storage/` fuera del control de versiones.
- Logging rotativo en `storage/logs/setesa.log` para login, workflow, PDF y
  vigencia.

> La guía de producción, custodia de la clave y despliegue está en
> **[`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md)**.

---

## Estado del proyecto

El avance detallado, las brechas y el plan por fases están en
**[`docs/CHECKLIST_AVANCE.md`](docs/CHECKLIST_AVANCE.md)**.

Fases completadas: **0 (línea base)**, **1 (coherencia del workflow)**,
**2 (firmas completas)**, **3 (vigencia robusta: baja lógica auditable,
ejecución semestral y reactivación)**, **4 (dashboard completo: filtros, KPIs,
alertas, descarga del PDF final y exportación CSV)**, **5 (saldo de vacaciones,
feriados administrables, validaciones de servidor y jefe GTC desde usuarios)**,
**6 (RNF: cifrado Fernet, sello SHA-256, SQLAlchemy, logging, CI y guía de
despliegue)**, **7 (rol Contabilidad de solo lectura, HU-03)**, **8
(recordatorio auditable al banco, R-11)** y **9 (rol IT y gestión de usuarios
con auditoría)**.

Cierre actual de calidad: **118 pruebas pytest** y **57/57** checks del smoke test,
sin datos de prueba residuales en la base. El workflow de GitHub Actions compila
y ejecuta la suite en cada push a `main`.

---

## Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| «Falta la variable DATABASE_URL» | Crear `.env` a partir de `.env.example` |
| Error al importar `streamlit_drawable_canvas` | Debe ejecutarse con `streamlit run`, no con `python app.py` |
| `pandas only supports SQLAlchemy...` | Las lecturas deben usar `get_engine()`; ya migradas en Fase 6 |
| `CifradoError: la FERNET_KEY no coincide` | Se cambió la clave; restaure la original o los datos cifrados no se recuperan |
| Usuario bloqueado | `estado_vigencia = FALSE` (baja lógica); Gerencia puede reactivarlo desde el panel de vigencia |
