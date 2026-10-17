# Estructura del Proyecto — SETESA Workflow

Organización por capas (Arquitectura Web de Tres Capas, según el documento del proyecto).
Los módulos están en sus paquetes, con `import` absolutos, credenciales externalizadas
y utilidades de prueba.

## Árbol

```
proyecto_setesa/
├── app.py                     # Punto de entrada (enrutador por rol)
├── requirements.txt           # Dependencias
├── .env                       # DATABASE_URL (NO versionar)
├── .env.example               # Plantilla de variables de entorno
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── core/                  # Núcleo (config, datos, seguridad, dominio)
│   │   ├── database.py        # Conexión a PostgreSQL (lee .env)
│   │   ├── auth.py            # Login con hash + RBAC
│   │   ├── security.py        # Hashing PBKDF2 + rol_autorizado()
│   │   ├── workflow.py        # Catálogo único de estados
│   │   ├── catalogos.py       # Catálogo de tipos de ausencia
│   │   ├── utils.py           # Lógica pura (calcular_dias_habiles)
│   │   └── config.py          # Rutas centralizadas (storage/)
│   ├── features/              # Módulos funcionales por rol
│   │   ├── registro.py        # Formulario del Consultor (CU-02)
│   │   ├── coordinador.py     # Panel Coordinador GTC (CU-04)
│   │   ├── dashboard.py       # Panel gerencial (CU-05)
│   │   └── vigencia.py        # Baja lógica semestral (CU-06)
│   └── services/              # Servicios de soporte
│       ├── motor_pdf.py       # Generación de PDF (RF-04)
│       └── utils_firma.py     # Firma canvas <-> Base64 (RF-06)
│
├── scripts/
│   └── hash_passwords.py      # Migración de contraseñas a hash
├── tests/
│   └── smoke_test.py          # Prueba E2E del workflow (rollback)
│
├── assets/                    # Recursos estáticos
├── storage/
│   ├── pdf/                   # PDFs emitidos
│   └── firmas/                # Imágenes temporales de firmas
├── docs/
└── proyecto_doc/              # Documento del proyecto (PDF)
```

## Catálogo de estados (`src/core/workflow.py`)

| Constante | Valor |
|---|---|
| `ESTADO_INGRESADA` | `Ingresada` |
| `ESTADO_PENDIENTE_FIRMA_COORDINADOR` | `Pendiente de Firma Coordinador` |
| `ESTADO_PENDIENTE_APROBACION_GERENCIA` | `Pendiente de Aprobación Gerencia` |
| `ESTADO_FINALIZADA` | `Finalizada` |

## Cómo ejecutar

```powershell
# App
venv\Scripts\streamlit run app.py

# Prueba E2E (no persiste datos: usa ROLLBACK)
venv\Scripts\python tests\smoke_test.py

# Migración de contraseñas heredadas a hash
venv\Scripts\python scripts\hash_passwords.py
```

## Arreglos aplicados

1. **Canvas / Streamlit**: alineado a `streamlit==1.66.0`. El error de
   `streamlit-drawable-canvas` solo ocurría al importarlo **fuera** del runtime;
   bajo `streamlit run` (que ejecuta la exploración de componentes) funciona.
2. **Rutas de salida**: `motor_pdf.py` escribe en `storage/pdf/` y
   `utils_firma.py` en `storage/firmas/`, vía `src/core/config.py`.
3. **Prueba E2E**: `tests/smoke_test.py` valida workflow, conexión y PDF (11/11 OK).
4. **Seguridad**: contraseñas migradas a PBKDF2-SHA256 (`scripts/hash_passwords.py`);
   `auth.py` valida con `security.verify_or_upgrade` y auto-migra al iniciar sesión.
   Se agregó RBAC por módulo (`rol_autorizado`) como defensa en profundidad.

## Módulo Consultor — finalizado

- `registro.py` usa import perezoso del canvas (`st_canvas`) dentro de
  `mostrar_formulario`, por lo que el módulo es importable sin runtime (testeable).
- Cubierto por `tests/smoke_test.py` (registro + historial + PDF) y por la prueba
  de UI (login → llenar formulario → "Firmar Electrónicamente" → canvas sin errores).

## Limpieza aplicada

- Eliminados artefactos viejos: `temp_pdf/` y `temp_firma_emp.png`.
- `motor_pdf.py` usa el catálogo de estados (eliminado el literal `"Aprobada"`).
- Migrado `use_container_width` → `width="stretch"` en todo el proyecto.
- Eliminados imports sin uso (`os`, `numpy`) en `registro.py` y `utils_firma.py`.

## Pendientes conocidos

- Flujo del Coordinador: hoy pasa directo a `Pendiente de Aprobación Gerencia`; el
  estado `ESTADO_PENDIENTE_FIRMA_COORDINADOR` aún no se usa (decisión de negocio).
- Advertencia de pandas: `pd.read_sql_query` con conexión DBAPI2 (considerar SQLAlchemy).
- `motor_pdf.py`: `limpiar_nombre`/plantilla con literales propios; revisar si se
  centralizan.
