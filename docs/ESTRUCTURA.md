# Estructura del Proyecto — SETESA Workflow

Organización por capas (Arquitectura Web de Tres Capas, según el documento del
proyecto). Los módulos están en sus paquetes, con `import` absolutos,
credenciales externalizadas y utilidades de prueba.

Estado actual: **Fases 0, 1, 2, 3, 4, 5 y 6 completadas** (ver `docs/CHECKLIST_AVANCE.md`).

## Árbol

```
proyecto_setesa/
├── app.py                     # Punto de entrada (enrutador por rol)
├── requirements.txt           # Dependencias
├── pytest.ini                 # Configuración de pruebas
├── README.md                  # Guía de instalación y uso
├── .env                       # DATABASE_URL + FERNET_KEY (NO versionar)
├── .env.example               # Plantilla de variables de entorno
├── .gitignore
├── .github/workflows/ci.yml   # Compilación + pytest
│
├── src/
│   ├── __init__.py
│   ├── core/                  # Núcleo (config, datos, seguridad, dominio)
│   │   ├── database.py        # PostgreSQL: psycopg2 (escrituras) + SQLAlchemy (lecturas)
│   │   ├── auth.py            # Login con hash + RBAC
│   │   ├── security.py        # Hashing PBKDF2 + rol_autorizado()
│   │   ├── crypto.py          # Fernet: cifrado en reposo de datos sensibles
│   │   ├── logging_config.py  # Logger rotativo en storage/logs
│   │   ├── workflow.py        # Estados y transiciones permitidas
│   │   ├── solicitudes.py     # Servicio transaccional + historial
│   │   ├── vigencia.py        # Baja lógica, auditoría y reactivación
│   │   ├── catalogos.py       # Catálogo de tipos de ausencia
│   │   ├── reportes.py        # Filtros, KPIs y exportación CSV (RF-04)
│   │   ├── feriados.py        # Catálogo de feriados (RF-01 / D-04)
│   │   ├── vacaciones.py      # Saldo asignado − usado (RF-01 / D-03)
│   │   ├── validaciones.py    # Reglas de fechas y saldo en servidor
│   │   ├── usuarios.py        # Usuarios por rol (jefe GTC)
│   │   ├── utils.py           # Lógica pura (calcular_dias_habiles)
│   │   └── config.py          # Rutas y variables (.env o st.secrets)
│   ├── features/              # Módulos funcionales por rol
│   │   ├── registro.py        # Formulario del Consultor (CU-02)
│   │   ├── coordinador.py     # Panel Coordinador GTC (CU-04)
│   │   ├── dashboard.py       # Panel gerencial + filtros + descargas (CU-05)
│   │   ├── feriados.py        # Administración de feriados (Gerencia)
│   │   └── vigencia.py        # Baja lógica semestral (CU-06)
│   └── services/              # Servicios de soporte
│       ├── documentos.py      # PDF oficial desde la BD + ruta_pdf + descarga
│       ├── motor_pdf.py       # Generación de PDF (RF-03)
│       └── utils_firma.py     # Firma canvas <-> Base64 (RF-06)
│
├── scripts/
│   ├── backup_datos.py        # Respaldo lógico JSON
│   ├── migracion_fase1.py     # Historial + normalización de estados
│   ├── migracion_fase3.py     # vigencia_log + restricciones
│   ├── migracion_fase5.py     # saldo de vacaciones + catálogo de feriados
│   ├── migracion_fase6.py     # sello SHA-256 + cifrado de datos heredados
│   ├── vigencia_semestral.py  # Ejecución programada (cron/Task Scheduler)
│   └── hash_passwords.py      # Migración de contraseñas a hash
│
├── tests/
│   ├── conftest.py            # sys.path + .env + FERNET_KEY de pruebas
│   ├── test_utils.py          # Días hábiles
│   ├── test_workflow.py       # Catálogo y transiciones
│   ├── test_security.py       # PBKDF2 y migración
│   ├── test_crypto.py         # Cifrado Fernet y clave incorrecta
│   ├── test_utils_firma.py    # Canvas/Base64, nombres únicos y limpieza
│   ├── test_solicitudes_integration.py  # BD real (skip sin DATABASE_URL)
│   ├── test_documentos.py     # PDF con 3 firmas + ruta_pdf (BD real)
│   ├── test_vigencia.py       # Baja lógica, auditoría y reactivación (BD real)
│   ├── test_reportes.py       # Filtros, KPIs y CSV del dashboard (unitarias)
│   ├── test_dashboard_integration.py  # Repositorio + PDF final (BD real)
│   ├── test_feriados.py       # Catálogo de feriados (BD real)
│   ├── test_vacaciones.py     # Saldo asignado − usado (BD real)
│   ├── test_validaciones.py   # Reglas de fechas y saldo
│   ├── test_app_smoke.py      # Renderizado con AppTest + login inactivo
│   └── smoke_test.py          # Prueba E2E manual (rollback/limpieza)
│
├── docs/
│   ├── ESTRUCTURA.md          # Este archivo
│   ├── CHECKLIST_AVANCE.md    # Estado y plan por fases
│   ├── DESPLIEGUE.md          # Producción, secrets y operación
│   ├── schema.sql             # DDL completo del esquema
│   └── evidencias/            # Salidas de pruebas y capturas
│
├── assets/                    # Recursos estáticos
├── storage/
│   ├── pdf/                   # PDFs emitidos + sellos .pdf.sha256
│   ├── firmas/                # Imágenes temporales de firmas
│   ├── logs/                  # Logs rotativos (no versionar)
│   └── backups/               # Respaldos JSON (no versionar)
└── proyecto_doc/              # Documento del proyecto (PDF)
```

## Catálogo de estados (`src/core/workflow.py`)

| Constante | Valor |
|---|---|
| `ESTADO_INGRESADA` | `Ingresada` |
| `ESTADO_PENDIENTE_FIRMA_COORDINADOR` | `Pendiente de Firma Coordinador` |
| `ESTADO_PENDIENTE_APROBACION_GERENCIA` | `Pendiente de Aprobación Gerencia` |
| `ESTADO_FINALIZADA` | `Finalizada` |

## Transiciones permitidas

```
Ingresada
   └─► Pendiente de Firma Coordinador
          └─► Pendiente de Aprobación Gerencia
                 └─► Finalizada
```

- `workflow.puede_transicionar(origen, destino)` valida el cambio.
- `workflow.siguiente_estado(actual)` devuelve el único paso permitido.
- No se permiten saltos ni retrocesos.
- Cada cambio se audita en `solicitud_historial`.

### Decisión D-01 (opción C)

El registro inserta la solicitud como `Ingresada` y, **en la misma transacción**,
la pasa a `Pendiente de Firma Coordinador`. El historial conserva ambos eventos.
Así se concilian HU-01/QA-03 (que exigen `Ingresada`) y la sección 4.12.3 de la
tesis (que exige `Pendiente de Firma Coordinador`).

## Cómo ejecutar

Antes de arrancar, `.env` debe tener `DATABASE_URL` y `FERNET_KEY` (o definir
ambas en los secrets de Streamlit). La guía completa está en
`docs/DESPLIEGUE.md`.

```powershell
# Instalar dependencias
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Respaldo previo (si la base ya tiene datos)
.\venv\Scripts\python.exe scripts\backup_datos.py

# Migración de esquema/datos (idempotente)
.\venv\Scripts\python.exe scripts\migracion_fase1.py
.\venv\Scripts\python.exe scripts\migracion_fase3.py
.\venv\Scripts\python.exe scripts\migracion_fase5.py
.\venv\Scripts\python.exe scripts\migracion_fase6.py --cifrar-existentes

# Vigencia semestral programada (solo si venció el periodo)
.\venv\Scripts\python.exe scripts\vigencia_semestral.py
# Forzar una ejecución (pruebas / cierre de semestre)
.\venv\Scripts\python.exe scripts\vigencia_semestral.py --forzar

# App
.\venv\Scripts\streamlit run app.py

# Suite automatizada
.\venv\Scripts\python.exe -m pytest

# Prueba E2E (no deja datos de prueba)
.\venv\Scripts\python.exe tests\smoke_test.py

# Migración de contraseñas heredadas a hash
.\venv\Scripts\python.exe scripts\hash_passwords.py
```

## Arreglos aplicados

1. **Canvas / Streamlit**: alineado a `streamlit==1.66.0`. El error de
   `streamlit-drawable-canvas` solo ocurría al importarlo **fuera** del runtime;
   bajo `streamlit run` funciona.
2. **Rutas de salida**: `motor_pdf.py` escribe en `storage/pdf/` y
   `utils_firma.py` en `storage/firmas/`, vía `src/core/config.py`.
3. **Seguridad**: contraseñas migradas a PBKDF2-SHA256 (`scripts/hash_passwords.py`);
   `auth.py` valida con `security.verify_or_upgrade` y auto-migra al iniciar sesión.
   Se agregó RBAC por módulo (`rol_autorizado`).
4. **Fase 0 (línea base)**: `docs/schema.sql`, `README.md`, `pytest.ini`,
   34 pruebas automatizadas iniciales y respaldo JSON (hoy 83).
5. **Fase 1 (coherencia del workflow)**:
   - `src/core/solicitudes.py` centraliza registro y cambios de estado.
   - `solicitud_historial` audita cada transición.
   - `CHECK` en `estado_workflow`, `NOT NULL` e índices.
   - Migración del estado legado `"En revisión por jefe inmediato GTC"`.
   - El dashboard ya no permite saltos arbitrarios: Gerencia solo finaliza
     expedientes en `Pendiente de Aprobación Gerencia`.
   - Los paneles muestran el historial de estados.
6. **Fase 2 (firmas completas)**:
   - Canvas y firma obligatoria en el panel del Coordinador GTC
     (`firma_jefe_gtc`) y en el Dashboard de Gerencia (`firma_gerencia`).
   - `cambiar_estado(..., firma_b64=...)` exige y persiste la firma en la misma
     transacción (`FirmaRequerida` si falta).
   - `src/services/documentos.py` genera el PDF desde la BD, con las firmas
     disponibles, y guarda `solicitud.ruta_pdf`.
   - El PDF imprime `(Pendiente Autorización)` solo cuando falta la firma.
   - Nombres temporales con `uuid` y PDF determinista por `id_solicitud`;
     limpieza automática de imágenes temporales.
7. **Fase 3 (vigencia robusta)**:
   - `src/core/vigencia.py` centraliza detección, baja lógica, auditoría,
     reactivación y ejecución automática.
   - `ultima_actividad` se actualiza en login y en registro/firma de solicitudes
     (`marcar_actividad`); un usuario dado de baja no recupera actividad al
     intentar entrar.
   - El rol `Administrador` y el ejecutor quedan excluidos de la baja.
   - `vigencia_log` registra `DEPURACION`, `AUTOMATICA` y `REACTIVACION` con
     fecha, ejecutor, afectados y detalle.
   - Al iniciar sesión Gerencia se ejecuta la depuración si pasaron 6 meses;
     `scripts/vigencia_semestral.py` permite programarla fuera de la app.
   - `app.py` revalida la vigencia en cada rerun y expulsa sesiones dadas de baja.
   - El panel de Gerencia muestra candidatos, ejecución, reactivación e historial.
8. **Fase 4 (dashboard completo)**:
   - `src/core/reportes.py` concentra la lógica pura del panel: filtros por
     nombre, estado, tipo y rango de fechas (por solapamiento con el periodo de
     ausencia), KPIs, distribución por tipo y exportación CSV con BOM.
   - `dashboard.py` muestra alertas de pendientes, cinco KPIs, distribución por
     estado/tipo, tabla paginada y descarga del PDF final (HU-03).
   - `services/documentos.py::preparar_pdf_descarga` reutiliza `solicitud.ruta_pdf`
     o regenera el PDF si el archivo no existe.
   - Exportación CSV compatible con Excel (no requiere `openpyxl`).
9. **Fase 5 (saldo de vacaciones y feriados)**:
   - `usuario.dias_vacaciones_asignados` (15 por defecto, `CHECK >= 0`).
   - `src/core/vacaciones.py` calcula asignados − usados del año; el panel del
     consultor muestra los tres valores (RF-01).
   - `src/core/feriados.py` + tabla `feriado` (fecha única); Gerencia administra
     el catálogo desde la pestaña **Feriados**.
   - `calcular_dias_habiles` excluye feriados; el registro recalcula los días en
     el servidor y rechaza discrepancias.
   - `src/core/validaciones.py` valida fechas y saldo antes de insertar; el
     formulario replica los mensajes.
   - El jefe GTC se elige desde los usuarios vigentes con rol Coordinador GTC.
   - `scripts/migracion_fase5.py` es idempotente y siembra 2025–2027.
10. **Fase 6 (RNF y cierre)**:
    - `src/core/crypto.py` cifra con Fernet la explicación y las tres firmas; el
      prefijo `fernet:` distingue los datos cifrados de los heredados.
    - `src/core/database.py` usa psycopg2 para escrituras transaccionales y
      SQLAlchemy (`get_engine`) para las lecturas con pandas; ya no hay
      advertencias de DBAPI2.
    - `src/core/logging_config.py` escribe un log rotativo en
      `storage/logs/setesa.log` y registra login, workflow, PDF y vigencia.
    - `src/services/documentos.py` calcula el SHA-256 del PDF, lo persiste en
      `solicitud.pdf_hash` y deja un sidecar `.pdf.sha256`; el dashboard verifica
      la integridad.
    - `scripts/migracion_fase6.py` agrega las columnas, cifra datos heredados con
      `--cifrar-existentes` y sella PDFs existentes.
    - `.github/workflows/ci.yml` compila y ejecuta `pytest` en cada push.
    - `docs/DESPLIEGUE.md` documenta Supabase, Streamlit Cloud, secrets,
      respaldos y operación.

## Módulo Consultor

- `registro.py` usa import perezoso del canvas (`st_canvas`) dentro de
  `mostrar_formulario`, por lo que el módulo es importable sin runtime.
- Cubierto por `tests/smoke_test.py`, `test_solicitudes_integration.py` y
  `test_app_smoke.py`.

## Pendientes conocidos

- **D-02**: rol Contabilidad de solo lectura (diferido; la tesis usa
  Administrador como beneficiario del dashboard).
- **R-11**: recordatorio al banco (diferido; sin correo institucional).
- **D-06**: rechazo/devolución con motivo (diferido; fuera del alcance acordado).
- **Transcripción documental**: llevar el estado final de la Fase 6 a las tablas
  25, 26 y 27 del PDF de la tesis y preparar la defensa.

Los RNF de cifrado, integridad, logging y CI quedaron cerrados en la Fase 6. La
advertencia de pandas desapareció al migrar las lecturas a SQLAlchemy.
