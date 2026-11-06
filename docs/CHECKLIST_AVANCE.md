# Checklist de Avance y Plan de Continuación — Proyecto SETESA

> **Documento de trabajo** elaborado a partir de la lectura completa de
> `proyecto_doc/Proyecto de Graduación II - Proyecto SETESA - Ricardo Arias.pdf`
> (220 páginas) y de la inspección del código, la base de datos PostgreSQL
> (Supabase) y las pruebas existentes.
> Fecha de corte: **04/11/2026**.
>
> Este archivo es la guía viva para continuar el desarrollo. Se actualiza al
> cerrar cada fase.

---

## 1. Resumen ejecutivo

El proyecto tiene una **base sólida y funcional**: los 7 módulos existen, el
flujo Consultor → Coordinador → Gerencia → PDF se ejecuta de extremo a extremo y
la prueba E2E actual pasa **57/57**. La arquitectura de tres capas está
respetada, la seguridad de contraseñas (PBKDF2) está resuelta y, tras las fases
0–6, el workflow es trazable, las **tres firmas** se capturan y se estampan, la
**vigencia semestral** es automática, auditable y reversible, el **dashboard**
permite filtrar por nombre, fecha y tipo, ver KPIs, descargar el PDF final,
verificar su integridad y exportar los resultados, y el consultor ve su **saldo
de vacaciones** con **feriados** descontados y validaciones de servidor.

La inspección inicial encontró brechas de coherencia entre lo que la tesis
declara y lo que el sistema realmente hace. **Todos los defectos P0, P1 y P2
están cerrados:**

1. ~~`ultima_actividad` nunca se actualiza~~ **Resuelto Fase 3:** se actualiza en
   login y en cada escritura relevante; los usuarios vigentes ya no corren riesgo
   de baja masiva.
2. ~~El estado legado fuera de catálogo~~ **Resuelto Fase 1.**
3. ~~Las firmas de Coordinador y Gerencia no se capturaban~~ **Resuelto Fase 2**
   (PR-06 cerrado).
4. ~~Datos sensibles y firmas en claro~~ **Resuelto Fase 6:** Fernet con clave
   fuera de la base.
5. ~~PDF sin sello de integridad~~ **Resuelto Fase 6:** SHA-256 persistido y
   verificado desde el dashboard.

**Conclusión:** el sistema está **100 % funcional** y con los RNF verificables
cubiertos. Quedan únicamente **D-06** (rechazo/devolución, fuera del alcance) y
el endurecimiento del login (límite de intentos), que no forma parte del alcance
mínimo de la tesis.

### Registro de avance

| Fecha | Fase | Resultado |
|---|---|---|
| 27/10/2026 | **Fase 0** | `docs/schema.sql`, `README.md`, `pytest.ini`, backup JSON y pruebas automatizadas. |
| 27/10/2026 | **Fase 1** | `solicitud_historial`, transiciones centralizadas, decisión D-01 (opción C), `CHECK` + índices, estado legado migrado y dashboard sin saltos. |
| 27/10/2026 | **Fase 2** | Canvas y firma obligatoria de Coordinador y Gerencia, PDF con 3 firmas, `ruta_pdf`, nombres únicos y limpieza de temporales. **PR-06 cerrado.** |
| 27/10/2026 | **Fase 3** | `ultima_actividad` en login/acciones, `vigencia_log`, protección de Administrador, ejecución automática semestral, reactivación e invalidación de sesiones. **H-01/H-06 cerrados; QA-01/QA-06/PR-05 completos.** |
| 27/10/2026 | **Fase 4** | Filtros por nombre, estado, tipo y rango de fechas; KPIs completos; alertas; paginación; descarga del PDF final y exportación CSV. **H-08/H-09, D-10/D-11/D-13 cerrados.** |
| 27/10/2026 | **Fase 5** | Saldo de vacaciones (asignado − usado), catálogo de feriados administrable, validación de fechas y saldo en servidor, jefe GTC desde usuarios. **H-07/H-16/H-17/H-18 y D-03/D-04 cerrados.** |
| 27/10/2026 | **Fase 6** | Cifrado Fernet, sello SHA-256, SQLAlchemy, logging rotativo, CI y guía de despliegue. **H-11/H-13/H-19/H-20/H-21/H-23 y D-05 cerrados.** |
| 04/11/2026 | **Fase 7** | Rol **Contabilidad** de solo lectura (HU-03): panel propio, filtros, trazabilidad y descarga del PDF final, sin autorización ni administración. **D-02 cerrado.** |
| 04/11/2026 | **Fase 8** | Recordatorio auditable del consultor al Coordinador GTC (R-11): botón en el historial, bandeja de recordatorios, enlace de correo `mailto` y cooldown de 24 h. **R-11 cerrado.** |
| 04/11/2026 | **Fase 9** | Rol **IT** y gestión de usuarios: altas, edición, bajas/reactivaciones, reseteo de contraseña, auditoría en `usuario_log` y protecciones. |

**Evidencias:** `docs/evidencias/2026-10-27_fase0-1.md`,
`docs/evidencias/2026-10-27_fase2.md`,
`docs/evidencias/2026-10-27_fase3.md`,
`docs/evidencias/2026-10-27_fase4.md`,
`docs/evidencias/2026-10-27_fase5.md` y
`docs/evidencias/2026-10-27_fase6.md`; **Fase 7** en
`docs/evidencias/2026-11-04_fase7.md`, **Fase 8** en
`docs/evidencias/2026-11-04_fase8.md` y **Fase 9** en
`docs/evidencias/2026-11-04_fase9.md`.
**Pruebas al cierre:** `pytest` 118/118 y smoke test 57/57, sin datos de prueba
residuales en la base.

**Hallazgos cerrados:** H-01, H-02, H-03, H-04, H-05, H-06, H-07, H-08, H-09,
H-10, H-11, H-12, H-13, H-14, H-15, H-16, H-17, H-18, H-19, H-20, H-21, H-22,
H-23, D-01, D-02, D-03, D-04, D-05 y R-11.
**Hallazgos que siguen abiertos:** solo D-06 (rechazo/devolución, fuera del
alcance acordado).

---

## 2. Fuente de verdad: qué exige la tesis

### 2.1 Requerimientos funcionales (RF)

| ID | Requerimiento | Criterio de aceptación |
|---|---|---|
| RF-01 | Autenticación RBAC | Login enruta por rol y bloquea `estado_vigencia = FALSE`; el consultor ve sus datos y **saldo de días de vacaciones** |
| RF-02 | Registro de ausencia | Formulario validado; la solicitud queda en BD (estado `Ingresada`) y calcula días hábiles en < 5 min |
| RF-03 | PDF oficial | FPDF genera el documento fiel a la plantilla SETESA con datos inyectados |
| RF-04 | Workflow + Dashboard | Estados trazables; dashboard con filtros por **nombre, fecha y tipo**; KPIs en tiempo real |
| RF-05 | Vigencia semestral | Baja lógica (`estado_vigencia = FALSE`) tras 6 meses sin actividad, sin borrar historial |
| RF-06 | Firmas Canvas/Base64 | Canvas en **Consultor, Coordinador GTC y Administrador**; firma en Base64 estampada en el PDF según el estado |

### 2.2 Requerimientos no funcionales (RNF)

| ID | Requerimiento | Implicación técnica |
|---|---|---|
| RNF-01 | Seguridad y confidencialidad | Datos médicos/luto **cifrados** y restringidos a Gerencia; RBAC bloquea expedientes de terceros |
| RNF-02 | Integridad transaccional (ACID) | Sin registros huérfanos; persistencia e historial a largo plazo |
| — | Cumplimiento legal | Código de Trabajo (Dto. 1441) y Ley de Firmas Electrónicas (Dto. 47-2008) |
| — | Usabilidad | Solicitud en **< 5 minutos** (línea base: 30–45 min) |
| — | Persistencia histórica | Baja lógica, nunca borrado físico |

### 2.3 Estados del workflow (tesis, sección 1.7.3 / 4.9.2)

1. `Ingresada`
2. `Pendiente de Firma Coordinador`
3. `Pendiente de Aprobación Gerencia`
4. `Finalizada`

### 2.4 Casos de uso, historias y pruebas

- **CU-01** Autenticar · **CU-02** Registrar · **CU-03** Generar PDF
- **CU-04/CU-05** Workflow y aprobación · **CU-06** Vigencia
- **HU-01** Consultor registra · **HU-02** Gerencia depura · **HU-03** Contabilidad descarga PDF final
- **QA-01…QA-06** (6/6 declaradas aprobadas)
- **PR-01…PR-06** (6/6 completadas; PR-06 cerrado en la Fase 2)

### 2.5 Los 7 módulos declarados (Tabla 25)

`auth.py` · `registro.py` · `motor_pdf.py` · `coordinador.py` · `vigencia.py` ·
`dashboard.py` · `utils_firma.py`

---

## 3. Cómo se verificó el estado actual

| Verificación | Resultado |
|---|---|
| Lectura completa de la tesis (211 pp.) | Requerimientos, diseño, criterios y pruebas extraídos |
| Inspección de los 12 archivos `.py` | 7 módulos + núcleo + pruebas |
| Consulta al esquema real en Supabase | 3 tablas (`rol`, `usuario`, `solicitud`), 5 usuarios, 2 solicitudes |
| `python tests/smoke_test.py` | **14/14 OK** en la línea base (hoy 57/57) |
| Búsqueda de actualizaciones de `ultima_actividad` | **0 ocurrencias** de `UPDATE` |
| Búsqueda de escritura de `firma_jefe_gtc` / `firma_gerencia` | **0 ocurrencias** de escritura |
| Búsqueda de escritura de `ruta_pdf` | **0 ocurrencias** de escritura |
| Catálogo de estados vs. datos reales | 1 registro con estado fuera de catálogo |

**Línea base de calidad:** el smoke test valida el camino feliz y, tras la
Fase 4, también los filtros combinados, la exportación CSV y la descarga del PDF
final. **Falta** prueba RBAC negativa entre roles. La vigencia y el login
inactivo cuentan con pruebas específicas (Fase 3).

---

## 4. Checklist por módulo

Leyenda: ✅ completo y verificado · 🟡 parcial / en proceso · 🔴 pendiente ·
🔧 funciona pero requiere mejora

### 4.1 Núcleo e infraestructura

| # | Ítem | Estado | Evidencia / brecha | Acción |
|---|---|---|---|---|
| N-01 | Conexión PostgreSQL vía `.env` | ✅ | `src/core/database.py` | — |
| N-02 | Rutas centralizadas (`storage/`) | ✅ | `src/core/config.py` | — |
| N-03 | Catálogo de estados | ✅ | `workflow.py` + `CHECK` en BD; los 4 estados están en uso | — |
| N-04 | Catálogo de tipos de ausencia | ✅ | `catalogos.py` (22 opciones, alineadas al formato) | — |
| N-05 | Cálculo de días hábiles | ✅ | `utils.py` cuenta lun–vie y excluye feriados del catálogo | — |
| N-06 | Hashing PBKDF2 + migración | ✅ | `security.py`, `scripts/hash_passwords.py` | — |
| N-07 | RBAC por módulo | ✅ | `rol_autorizado()` + revalidación de vigencia en cada rerun (`app.py`) | — |
| N-08 | **Esquema SQL versionado** | ✅ | `docs/schema.sql` validado en esquema temporal | — |
| N-09 | README de instalación/ejecución | ✅ | `README.md` | — |
| N-10 | Pruebas automatizadas (pytest) | ✅ | 118 pruebas (unitarias, integración, PDF, cifrado, vigencia, reportes, feriados, vacaciones, recordatorios, gestión de usuarios y AppTest) | — |
| N-11 | Advertencia `pd.read_sql_query` | ✅ | Lecturas migradas a `get_engine()` (SQLAlchemy) | H-21 |
| N-12 | Limpieza de firmas temporales | ✅ | `utils_firma.eliminar_archivo` + `finally` en el motor; verificado por `test_documentos` | — |
| N-13 | Logging de errores | ✅ | Logger rotativo `setesa` en `storage/logs/setesa.log` | H-23 |
| N-14 | Gestión de usuarios con auditoría | ✅ | **Fase 9**: rol IT, `gestion_usuarios.py`, tabla `usuario_log`, protecciones y política de contraseña | — |

### 4.2 Módulo `auth.py` (RF-01 / RNF-01)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| A-01 | Login con correo + contraseña | ✅ | Verifica hash y auto-migra texto plano |
| A-02 | Bloqueo de usuario inactivo | ✅ | Mensaje “Usuario inactivo (Baja Lógica)” |
| A-03 | Enrutamiento por rol | ✅ | `app.py` → Consultor / Coordinador GTC / Administrador / Contabilidad / IT |
| A-04 | **Actualizar `ultima_actividad`** | ✅ | Login y acciones relevantes (`marcar_actividad`); solo usuarios vigentes |
| A-05 | Normalizar correo (trim/lower) | ✅ | `login_user` normaliza entrada y compara con `LOWER(...)` |
| A-06 | Revalidar vigencia en sesión activa | ✅ | `app.py` expulsa sesiones dadas de baja en cada rerun |
| A-07 | Sesión con `id_rol` y expiración | 🔧 | Solo guarda nombre/rol/id |
| A-08 | Recuperación de contraseña | 🔴 | Fuera del alcance mínimo; documentar como límite |

### 4.3 Módulo `registro.py` (RF-02 / RF-03 / RF-06 / HU-01)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| R-01 | Formulario de Acción de Personal | ✅ | Jefe, puesto, código, fechas, naturaleza, explicación |
| R-02 | Cálculo de días hábiles en vivo | ✅ | `st.metric` + validación de rango; descuenta feriados del catálogo |
| R-03 | Canvas de firma del consultor | ✅ | `streamlit-drawable-canvas`, Base64, recorte y fondo blanco |
| R-04 | Inserción transaccional | ✅ | `commit` correcto; el PDF se genera desde la BD y persiste `ruta_pdf` |
| R-05 | Generación y descarga del PDF | ✅ | Se genera al firmar y se descarga |
| R-06 | Historial personal + PDF actualizado | ✅ | Consulta filtrada por `id_usuario` (RBAC de datos) |
| R-07 | **Saldo de días de vacaciones** | ✅ | **RF-01**: asignados − usados en el panel; validación de saldo en el servidor |
| R-08 | Estado inicial según tesis | ✅ | Opción C: `Ingresada` → `Pendiente de Firma Coordinador` en la misma transacción | — |
| R-09 | Validar `fecha_fin >= fecha_inicio` | ✅ | Validación en UI y en `validaciones.validar_fechas` (servidor) |
| R-10 | Guardar `ruta_pdf` | ✅ | `services/documentos.py` actualiza la columna tras cada generación |
| R-11 | Alertas/recordatorios al banco | ✅ | **Fase 8**: botón en el historial, tabla `recordatorio`, bandeja del Coordinador, enlace `mailto` y cooldown de 24 h | — |
| R-12 | Seleccionar jefe GTC desde usuarios | ✅ | `selectbox` con los usuarios vigentes del rol Coordinador GTC |
| R-13 | Feriados de Guatemala | ✅ | Catálogo `feriado` administrable desde Gerencia |

### 4.4 Módulo `motor_pdf.py` (RF-03 / RF-06 / QA-05)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| P-01 | Plantilla oficial (encabezado, datos, cuadrícula) | ✅ | Fiel al formato, 22 naturalezas |
| P-02 | Inyección de datos | ✅ | Nombre, jefe, puesto, código, fechas, días, explicación |
| P-03 | Firma del consultor | ✅ | Imagen Base64 estampada |
| P-04 | **Firma del coordinador** | ✅ | `firma_jefe_gtc` se captura, persiste y estampa |
| P-05 | **Firma de gerencia** | ✅ | `firma_gerencia` se captura, persiste y estampa |
| P-06 | Nombres de archivo temporales | ✅ | `uuid` por firma; sin colisiones concurrentes |
| P-07 | Nombre único del PDF | ✅ | `accion_{id_solicitud}_{nombre}_{dias}d.pdf` (determinista) |
| P-08 | Documento “inalterable” | ✅ | SHA-256 en `solicitud.pdf_hash` + sidecar; el dashboard detecta alteraciones |
| P-09 | Limpieza de imágenes temporales | ✅ | Se eliminan en `finally` tras generar el PDF |
| P-10 | Centralizar `limpiar_nombre` | 🔧 | Lógica de presentación dentro del motor |

### 4.5 Módulo `coordinador.py` (CU-04 / RF-04 / RF-06 / PR-04)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| C-01 | Bandeja de solicitudes | ✅ | Filtra por `Pendiente de Firma Coordinador`, orden FIFO |
| C-02 | Transición a “Pendiente de Aprobación Gerencia” | ✅ | `UPDATE` + `commit` |
| C-03 | **Canvas de firma del coordinador** | ✅ | `st_canvas` obligatorio antes de aprobar |
| C-04 | **Persistir `firma_jefe_gtc`** | ✅ | `cambiar_estado(..., firma_b64=...)` en la misma transacción |
| C-05 | Validar transición permitida | ✅ | `cambiar_estado` bloquea con `FOR UPDATE` + grafo de transiciones | — |
| C-06 | Ver el PDF antes de firmar | 🔴 | No hay vista previa del expediente |
| C-07 | Asignación por equipo/coordinador | ✅ | Fase 11: `solicitud.id_coordinador`; la bandeja muestra solo sus expedientes y solo él puede firmarlos |
| C-08 | Rechazo / devolución con motivo | ✅ | Fase 16: el Coordinador GTC o Gerencia deniegan con motivo y firma (D-06 revisada) |
| C-09 | Evidencia de auditoría | ✅ | `solicitud_historial` registra actor, fecha y observación | — |
| C-10 | Bandeja de recordatorios | ✅ | **R-11**: aviso y tabla de recordatorios pendientes; se marcan atendidos al firmar | — |

### 4.6 Módulo `dashboard.py` (RF-04 / HU-03 / QA-04)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| D-01 | KPIs completos | ✅ | Total, Ingresadas, Pendientes Coordinador, Pendientes Gerencia y Finalizadas (`calcular_kpis`) |
| D-02 | Filtro por nombre | ✅ | `str.contains` sin distinguir mayúsculas (`filtrar_solicitudes`) |
| D-03 | Filtro por estado | ✅ | Selector dinámico sobre `ESTADOS_WORKFLOW` |
| D-04 | **Filtro por fecha (rango)** | ✅ | **RF-04** cumplido: solapamiento con `[fecha_inicio, fecha_fin]` |
| D-05 | **Filtro por tipo de incidencia** | ✅ | **RF-04** cumplido: selector construido desde la base |
| D-06 | **Descarga del PDF final** | ✅ | **HU-03** cumplido: `preparar_pdf_descarga` reutiliza `ruta_pdf` o regenera |
| D-07 | **Canvas de firma de gerencia** | ✅ | `st_canvas` obligatorio antes de finalizar |
| D-08 | **Persistir `firma_gerencia`** | ✅ | `cambiar_estado(..., firma_b64=...)` en la misma transacción |
| D-09 | Transiciones válidas (no saltos) | ✅ | Solo `Pendiente de Aprobación Gerencia` → `Finalizada` desde Gerencia | — |
| D-10 | Exportar métricas (CSV/Excel) | ✅ | CSV UTF-8 con BOM, compatible con Excel (`exportar_csv`) |
| D-11 | Alertas de pendientes | ✅ | Aviso in-app con conteo de coordinador y gerencia (4.12.3) |
| D-12 | Rol Contabilidad (solo lectura) | ✅ | Resuelto en Fase 7: panel propio con filtros, trazabilidad y descarga del PDF final |
| D-13 | Paginación | ✅ | Selector de filas por página y de página (10/25/50/100) |
| D-14 | Distribución de resultados | ✅ | Conteo por estado y por tipo dentro de la selección filtrada |

### 4.7 Módulo `vigencia.py` (RF-05 / CU-06 / QA-06)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| V-01 | Detección de > 6 meses | ✅ | `ultima_actividad < CURRENT_DATE - INTERVAL '6 months'` |
| V-02 | Baja lógica sin borrado | ✅ | `UPDATE estado_vigencia = FALSE` |
| V-03 | Reporte de afectados | ✅ | DataFrame con los desactivados |
| V-04 | **Dependencia de `ultima_actividad`** | ✅ | Se actualiza en login y escrituras; cubierto por `test_vigencia` |
| V-05 | Salvaguarda de administradores | ✅ | `ROLES_PROTEGIDOS` excluye Administrador e IT; también se excluye al ejecutor |
| V-06 | Auditoría de la depuración | ✅ | `vigencia_log` registra fecha, ejecutor, acción, afectados y detalle |
| V-07 | Ejecución automática semestral | ✅ | Al login de Gerencia + `scripts/vigencia_semestral.py` (`--forzar`) |
| V-08 | Reactivación de usuario | ✅ | Panel de Gerencia con reactivación auditada |
| V-09 | Notificación al afectado | 🔴 | No aplica (sin correo); documentar como límite |

### 4.8 Módulo `utils_firma.py` (RF-06 / QA-05)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| F-01 | Canvas → Base64 | ✅ | Recorte por alfa + ratio 3:1 + fondo blanco |
| F-02 | Base64 → PNG para FPDF | ✅ | Escribe en `storage/firmas` |
| F-03 | Nombre único por firma | ✅ | `uuid4` en `base64_to_image` |
| F-04 | Cifrado de la firma en BD | ✅ | Fernet con prefijo `fernet:`; se descifra solo al mostrar o generar el PDF |
| F-05 | Validación de tamaño/formato | 🔧 | No limita peso ni valida PNG |
| F-06 | Limpieza posterior | ✅ | `eliminar_archivo` tras generar el PDF |

### 4.9 Servicios de negocio de la Fase 5 (RF-01 / H-16 / H-17 / H-18)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| B-01 | Catálogo de feriados | ✅ | `src/core/feriados.py` + tabla `feriado` (fecha única) |
| B-02 | Semilla de feriados | ✅ | 2025–2027, incluida la Semana Santa |
| B-03 | Administración de feriados | ✅ | Pestaña **Feriados** del panel de Gerencia (alta/baja) |
| B-04 | Saldo de vacaciones | ✅ | `src/core/vacaciones.py` (asignados − usados del año) |
| B-05 | Días asignados por usuario | ✅ | `usuario.dias_vacaciones_asignados` (15 por defecto, `CHECK >= 0`) |
| B-06 | Validación de saldo en servidor | ✅ | `validaciones.validar_saldo_vacaciones` dentro de `registrar_solicitud` |
| B-07 | Validación de fechas en servidor | ✅ | `validaciones.validar_fechas` |
| B-08 | Jefe GTC desde usuarios | ✅ | `usuarios.listar_coordinadores` + `selectbox` |
| B-09 | Recálculo de días con feriados | ✅ | El servicio recalcula y rechaza discrepancias con la UI |

### 4.10 Servicios de la Fase 6 (RNF / H-11 / H-13 / H-19 / H-20 / H-21 / H-23)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| S-01 | Cifrado en reposo | ✅ | `src/core/crypto.py`; Fernet sobre explicación y tres firmas |
| S-02 | Clave fuera de la base | ✅ | `FERNET_KEY` en `.env` o `st.secrets`; nunca versionada |
| S-03 | Migración de datos heredados | ✅ | `scripts/migracion_fase6.py --cifrar-existentes` (idempotente) |
| S-04 | Sello SHA-256 del PDF | ✅ | `solicitud.pdf_hash`, `pdf_hash_fecha` y sidecar `.pdf.sha256` |
| S-05 | Verificación de integridad | ✅ | `verificar_integridad_pdf` + estado visible en el dashboard |
| S-06 | Lecturas con SQLAlchemy | ✅ | `get_engine()` con `pool_pre_ping`; sin warning de pandas |
| S-07 | Logging rotativo | ✅ | `logging_config.py`; login, workflow, PDF y vigencia |
| S-08 | CI | ✅ | `.github/workflows/ci.yml`: compileall + pytest |
| S-09 | Guía de despliegue | ✅ | `docs/DESPLIEGUE.md` (Supabase, Streamlit Cloud, respaldo y operación) |
| S-10 | Configuración unificada | ✅ | `config.obtener_variable`: entorno o `st.secrets` |

### 4.11 Gestión de usuarios (Fase 9)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| G-01 | Rol IT separado | ✅ | Solo ve el panel de usuarios; sin dashboard, firmas, vigencia ni feriados |
| G-02 | Alta de usuarios | ✅ | Nombre, correo, rol, días de vacaciones y contraseña inicial |
| G-03 | Edición | ✅ | Nombre, correo, rol y días; no permite cambiar el rol propio |
| G-04 | Baja lógica y reactivación | ✅ | Sin borrar historial; bloquea la autodesactivación y al último Administrador/IT |
| G-05 | Reseteo de contraseña | ✅ | PBKDF2-SHA256, mínimo 8 con letra y número |
| G-06 | Auditoría | ✅ | Tabla `usuario_log` con ejecutor, afectado, fecha, acción y detalle |
| G-07 | Vigencia | ✅ | IT queda protegido de la baja automática semestral |
| G-08 | Migración y pruebas | ✅ | `scripts/migracion_fase9.py` y `tests/test_gestion_usuarios.py` (13 pruebas) |

---

## 5. Checklist de pruebas y evidencias

| ID | Caso | Estado declarado en tesis | Estado real verificado | Brecha |
|---|---|---|---|---|
| QA-01 | Login usuario inactivo | Aprobado | ✅ `test_login_usuario_inactivo_es_rechazado` (AppTest) | — |
| QA-02 | Enrutamiento por rol | Aprobado | ✅ AppTest renderiza los 5 paneles | — |
| QA-03 | Registro + ACID | Aprobado | ✅ Smoke test + test de integración | — |
| QA-04 | Flujo de aprobación | Aprobado | ✅ Smoke test + transiciones inválidas rechazadas | — |
| QA-05 | Motor documental | Aprobado | ✅ Smoke test + `test_documentos` validan 3 firmas | — |
| QA-06 | Vigencia | Aprobado | ✅ `test_vigencia` (6 pruebas) + smoke test con fechas controladas | — |
| PR-01 | Login y RBAC | Completado | ✅ | — |
| PR-02 | Cálculo y registro | Completado | ✅ | — |
| PR-03 | PDF oficial | Completado | ✅ | — |
| PR-04 | Aprobación coordinador | Completado | ✅ Historial, validación y firma persistida | — |
| PR-05 | Baja lógica | Completado | ✅ `vigencia_log`, salvaguarda, reactivación y expulsión de sesión | — |
| PR-06 | Firma incrustada | En proceso | ✅ Completado: 3 firmas capturadas, persistidas y estampadas | — |

**Cobertura automatizada actual:** 118 pruebas pytest + 57 checks del smoke test.
Cubren: días hábiles con feriados, seguridad, transiciones válidas/inválidas,
historial, firma obligatoria y persistida, PDF con 3 imágenes, `ruta_pdf`,
limpieza de temporales, integración contra BD real, render de los 3 paneles,
login inactivo (QA-01), vigencia con fechas controladas (QA-06), filtros
combinados del dashboard, KPIs, exportación CSV, descarga del PDF final
(RF-04 / HU-03), saldo de vacaciones (RF-01), catálogo de feriados, validaciones
de fechas/saldo, cifrado/descifrado Fernet, datos cifrados en reposo, sello
SHA-256 y detección de alteraciones. El CI compila y ejecuta la suite en cada
push.
**Pendiente no funcional:** prueba RBAC negativa entre roles (mejora futura; el
RBAC positivo ya está cubierto por AppTest).

---

## 6. Hallazgos priorizados (backlog)

### P0 — Bloqueantes de coherencia (deben resolverse primero)

| ID | Hallazgo | Impacto | Módulo |
|---|---|---|---|
| ~~H-01~~ ✅ | ~~`ultima_actividad` nunca se actualiza~~ **Resuelto Fase 3** | Login y acciones relevantes actualizan la fecha; solo usuarios vigentes | auth / vigencia |
| ~~H-02~~ ✅ | ~~Firmas de coordinador y gerencia no se capturan ni persisten~~ **Resuelto Fase 2** | Canvas, `FirmaRequerida`, persistencia transaccional y PDF con 3 firmas | coordinador / dashboard / motor_pdf |
| ~~H-03~~ ✅ | ~~Estado legado `"En revisión por jefe inmediato GTC"` fuera de catálogo~~ **Resuelto Fase 1** | Migrado a `Pendiente de Firma Coordinador`; `CHECK` impide estados inválidos | BD / workflow |
| ~~H-04~~ ✅ | ~~Dashboard permite saltos arbitrarios de estado~~ **Resuelto Fase 1** | `workflow.py` centraliza el grafo y `cambiar_estado` lo valida | dashboard |
| ~~H-05~~ ✅ | ~~No existe historial de estados~~ **Resuelto Fase 1** | `solicitud_historial` con actor, fecha y observación | BD |
| ~~H-06~~ ✅ | ~~`vigencia` puede desactivar a Gerencia/Admin~~ **Resuelto Fase 3** | Rol Administrador protegido, ejecutor excluido y `vigencia_log` auditable | vigencia |

### P1 — Cumplimiento funcional incompleto

| ID | Hallazgo | Detalle | Requerimiento |
|---|---|---|---|
| ~~H-07~~ ✅ | ~~Falta saldo de días de vacaciones~~ **Resuelto Fase 5** | `vacaciones.py` + `usuario.dias_vacaciones_asignados` y validación de saldo | RF-01 |
| ~~H-08~~ ✅ | ~~Faltan filtros por fecha y tipo en el dashboard~~ **Resuelto Fase 4** | `filtrar_solicitudes` con solapamiento de fechas y selector de tipo | RF-04 |
| ~~H-09~~ ✅ | ~~Falta descarga del PDF final desde el dashboard~~ **Resuelto Fase 4** | `preparar_pdf_descarga` + botón en el panel gerencial | HU-03 |
| ~~H-10~~ ✅ | ~~`ruta_pdf` nunca se guarda~~ **Resuelto Fase 2** | `services/documentos.py` persiste la ruta | RF-03 / trazabilidad |
| ~~H-11~~ ✅ | ~~Datos sensibles y firmas sin cifrar~~ **Resuelto Fase 6** | Fernet sobre explicación y firmas; clave en `.env`/`st.secrets` | RNF-01 |
| ~~H-12~~ ✅ | ~~Esquema SQL no versionado~~ **Resuelto Fase 0** | `docs/schema.sql` validado en esquema temporal | Reproducibilidad / defensa |
| ~~H-13~~ ✅ | ~~PDF sin sello de integridad~~ **Resuelto Fase 6** | SHA-256 persistido + sidecar + verificación en dashboard | “Inalterable” / Dto. 47-2008 |

### P2 — Calidad, robustez y acabado

| ID | Hallazgo |
|---|---|
| ~~H-14~~ ✅ | ~~Nombres de PDF y de firmas temporales colisionan~~ **Resuelto Fase 2** |
| ~~H-15~~ ✅ | ~~Sin limpieza de archivos temporales~~ **Resuelto Fase 2** |
| ~~H-16~~ ✅ | ~~Validación de fechas y mensajes de error~~ **Resuelto Fase 5**: validación en UI y servidor |
| ~~H-17~~ ✅ | ~~Feriados de Guatemala no considerados~~ **Resuelto Fase 5**: catálogo `feriado` administrable |
| ~~H-18~~ ✅ | ~~Jefe GTC como texto libre~~ **Resuelto Fase 5**: se elige entre los usuarios Coordinador GTC |
| ~~H-19~~ ✅ | ~~Falta CI~~ **Resuelto Fase 6**: GitHub Actions compila y ejecuta pytest |
| ~~H-20~~ ✅ | ~~Falta guía de despliegue~~ **Resuelto Fase 6**: `docs/DESPLIEGUE.md` |
| ~~H-21~~ ✅ | ~~Advertencia de pandas / SQLAlchemy~~ **Resuelto Fase 6**: lecturas con `get_engine()` |
| ~~H-22~~ ✅ | ~~Sin paginación ni exportación~~ **Resuelto Fase 4**: paginación y CSV compatible con Excel |
| ~~H-23~~ ✅ | ~~Sin logging estructurado~~ **Resuelto Fase 6**: logger rotativo `setesa` |

---

## 7. Decisiones que requieren tu confirmación

| ID | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D-01** | Estado al registrar una solicitud | (A) `Ingresada` y el coordinador firma desde ahí · (B) `Pendiente de Firma Coordinador` desde el inicio · (C) registrar `Ingresada` y transicionar en la misma transacción, dejando historial de ambos | **C**: cumple HU-01/QA-03 y el paso 3 de 4.12.3, y hace que los 4 estados existan de verdad |
| **D-02** | Rol “Contabilidad” | (A) Crear rol de solo lectura · (B) mantener solo Administrador | **A confirmada** (Fase 7): panel de solo lectura con filtros, trazabilidad y descarga del PDF final |
| **D-03** | Origen del saldo de vacaciones | (A) campo `dias_vacaciones_asignados` en `usuario` · (B) cálculo por año a partir de solicitudes · (C) ambos | **C confirmada**: asignado − usado = disponible (Fase 5) |
| **D-04** | Feriados | (A) tabla `feriado` administrable · (B) lista fija en código | **A confirmada**: tabla `feriado` con panel de Gerencia (Fase 5) |
| **D-05** | Cifrado de datos sensibles | (A) Fernet en la app · (B) `pgcrypto` en PostgreSQL | **A confirmada** (clave en `.env`/`st.secrets`, sin exponerla a la BD) |
| **D-06** | Rechazo/devolución | (A) agregar estado `Devuelta` con motivo · (B) fuera de alcance | **Revisada el 04/11/2026:** se mantienen los 4 estados; *Finalizada* lleva resolución Aprobada/Denegada (Fase 16) |

> **Nota:** la tesis es internamente ambigua en D-01: HU-01/QA-03 dicen
> `Ingresada`, mientras 4.12.3 paso 3 dice `Pendiente de Firma Coordinador`.
> La opción C concilia ambas sin contradecir ninguna.

---

## 8. Plan de trabajo por fases

> Orden pensado para **no romper lo que ya funciona**: primero se blinda la base,
> luego se corrige la coherencia del flujo, después se completan las firmas y la
> vigencia, y al final se amplía el dashboard y se endurecen los RNF.

### Fase 0 — Blindaje de la línea base (0.5 día)

- [x] **F0.1** Crear `docs/schema.sql` con DDL, PK/FK, `UNIQUE`, `CHECK` y seed de roles.
- [x] **F0.2** Crear `README.md` (requisitos, `.env`, ejecución, usuarios de prueba, pruebas).
- [x] **F0.3** Añadir `pytest` y pruebas unitarias puras: días hábiles, transiciones, seguridad.
- [x] **F0.4** Backup lógico de `rol`, `usuario`, `solicitud` antes de migrar datos.
- [x] **F0.5** Congelar evidencia: salida de `pytest`, smoke test y AppTest documentadas en `docs/evidencias/`.

**Criterio de aceptación:** `pytest` corre en verde y el esquema se puede recrear
desde cero con `schema.sql`. ✅ **Cumplido.**

### Fase 1 — Coherencia del workflow (1.5 días) · P0

- [x] **H-05** Crear `solicitud_historial` (`id_historial`, `id_solicitud`, `estado_anterior`, `estado_nuevo`, `id_usuario`, `fecha`, `observacion`).
- [x] **H-04** Centralizar transiciones en `workflow.py` (`puede_transicionar`, `siguiente_estado`) y usarlas en todos los módulos.
- [x] **D-01** Implementar el estado inicial acordado y registrar el historial en la misma transacción.
- [x] **H-03** Migrar la solicitud `#8` al estado correcto y agregar `CHECK` a `estado_workflow`.
- [x] **H-04** Quitar del dashboard los saltos arbitrarios; solo permitir la transición válida y con firma.
- [x] **C-05** Validar estado actual antes de firmar en el coordinador.
- [x] Pruebas: transición válida, transición inválida rechazada, historial completo.

**Criterio de aceptación:** no se puede llegar a `Finalizada` sin pasar por los
estados intermedios, y cada cambio queda registrado con usuario y fecha.
✅ **Cumplido.**

### Fase 2 — Firmas completas (1.5 días) · P0 · cierra PR-06

- [x] **H-02/C-03** Canvas de firma en el panel del Coordinador GTC.
- [x] **H-02/C-04** Guardar `firma_jefe_gtc` al aprobar.
- [x] **H-02/D-07** Canvas de firma en el Dashboard (Gerencia).
- [x] **H-02/D-08** Guardar `firma_gerencia` al finalizar.
- [x] **P-04/P-05** Pasar ambas firmas al PDF y estamparlas; leyenda solo si faltan.
- [x] **H-14** Nombres únicos (`uuid`) para imágenes temporales y PDF por `id_solicitud`.
- [x] **H-15** Limpiar temporales tras generar.
- [x] **H-10** Guardar `ruta_pdf` en la solicitud.
- [x] Prueba PR-06: PDF con las 3 firmas visibles y descargable.

**Criterio de aceptación:** el PDF final contiene las tres firmas reales y PR-06
pasa de “en proceso” a “completado” con evidencia. ✅ **Cumplido** (43 pruebas,
28 checks y `test_documentos` verificando 3 imágenes en el PDF).

### Fase 3 — Vigencia robusta (1 día) · P0

- [x] **H-01/A-04** Actualizar `ultima_actividad` en login y en cada acción relevante.
- [x] **H-06** Excluir roles administrativos (o al usuario en sesión) de la baja automática.
- [x] **V-06** Registrar ejecuciones en `vigencia_log` (fecha, ejecutor, afectados).
- [x] **V-07** Ejecución automática: script `scripts/vigencia_semestral.py` + verificación al iniciar sesión de Gerencia.
- [x] **V-08** Reactivación manual desde el panel.
- [x] **A-05/A-06** Normalizar el correo y expulsar sesiones dadas de baja en cada rerun.
- [x] Pruebas: 181 días → baja; 179 días → activo; admin → nunca baja; login posterior → bloqueado.

**Criterio de aceptación:** un usuario activo **no** es dado de baja; uno inactivo
sí, con evidencia en `vigencia_log`, y puede reactivarse. ✅ **Cumplido**
(50 pruebas, 38 checks y `test_vigencia` con fechas controladas; base sin
residuos).

### Fase 4 — Dashboard completo (2 días) · P1

- [x] **H-08** Filtros por rango de fechas y por tipo de incidencia (además de nombre y estado).
- [x] **D-01** KPIs completos: total, ingresadas, pendientes de coordinador, pendientes de gerencia y finalizadas.
- [x] **H-09** Botón de descarga del PDF final con todas las firmas (HU-03).
- [x] **D-10** Exportación CSV compatible con Excel del resultado filtrado.
- [x] **D-11** Alertas in-app de solicitudes pendientes.
- [x] **D-02** Rol Contabilidad de solo lectura (resuelto en Fase 7).
- [x] **D-13** Paginación del repositorio.
- [x] Pruebas: cada filtro por separado y combinados; descarga con firmas; exportación.

**Criterio de aceptación:** Gerencia/Contabilidad pueden encontrar un expediente
por nombre, fecha y tipo, ver sus KPIs y descargar el PDF final. ✅ **Cumplido**
(64 pruebas, 43 checks y `test_dashboard_integration` verificando 3 firmas en el
PDF; rol Contabilidad completado en Fase 7).

### Fase 5 — RF-01 y validaciones de negocio (1 día) · P1

- [x] **H-07/D-03** Saldo de vacaciones: días asignados, usados y disponibles en el panel del consultor.
- [x] **H-16** Validar `fecha_fin >= fecha_inicio` en servidor y corregir mensajes.
- [x] **H-17/D-04** Descontar feriados de Guatemala (catálogo administrable).
- [x] **H-18** Seleccionar al jefe GTC desde los usuarios con rol Coordinador.
- [x] **R-11** Recordatorio al banco (cerrado en la Fase 8: tabla `recordatorio`, bandeja del Coordinador y enlace `mailto`).
- [x] Pruebas: saldo correcto tras varias solicitudes; fechas inválidas rechazadas; feriado descontado.

**Criterio de aceptación:** RF-01 se cumple de punta a punta y las validaciones
no permiten datos imposibles. ✅ **Cumplido al cierre de Fase 5** (83 pruebas,
52 checks y `test_vacaciones`/`test_feriados` con datos temporales; R-11 se
cerró después, en la Fase 8).

### Fase 6 — RNF, cierre y documentación (1.5 días) · P1/P2

- [x] **H-11/D-05** Cifrar `explicacion` y firmas en reposo.
- [x] **H-13** Sello SHA-256 del PDF + registro para verificación de integridad.
- [x] **H-21** Migrar a SQLAlchemy (elimina warning y mejora pool).
- [x] **H-23** Logging centralizado.
- [x] **H-19** Suite de pruebas completa (unitaria + integración + E2E) y CI.
- [x] **H-20** README, `docs/ESTRUCTURA.md`, `docs/DESPLIEGUE.md` y evidencias.
- [x] Regresión completa QA-01…QA-06 y PR-01…PR-06 (118 pytest + 57 smoke).
- [ ] Transcribir el estado final a las tablas 25, 26 y 27 del PDF de la tesis.

**Criterio de aceptación:** 6/6 QA y 6/6 PR con evidencia; documentación
reproducible; RNF verificables. ✅ **Cumplido** (la transcripción al PDF es una
tarea documental del autor; el mapeo está en la evidencia de Fase 6).

### Fase 7 — Rol Contabilidad (0.5 día) · cierra HU-03 / D-02

- [x] **D-02** Crear el rol `Contabilidad` (id 4) en la base y en `docs/schema.sql`.
- [x] **HU-03** Panel de Contabilidad de solo lectura: KPIs, filtros, tabla paginada, trazabilidad y descarga del PDF final con verificación SHA-256.
- [x] **RBAC** Ocultar la gestión de workflow (firma y autorización) y las pestañas de Vigencia y Feriados para Contabilidad.
- [x] **Migración** `scripts/migracion_fase7.py` idempotente, con cuenta demo opcional (`--usuario-demo`).
- [x] Pruebas: `tests/test_rbac_contabilidad.py` (panel, solo lectura y regresión de Gerencia).
- [x] Documentación: README, checklist y evidencia `docs/evidencias/2026-11-04_fase7.md`.

**Criterio de aceptación:** un usuario con rol Contabilidad entra a su panel,
consulta y descarga expedientes finalizados y **no** puede autorizar, firmar ni
administrar catálogos. ✅ **Cumplido.**

### Fase 8 — Recordatorio al banco (0.5 día) · cierra R-11

- [x] **R-11** Botón «Recordar al banco» en el historial del consultor, solo para expedientes en `Pendiente de Firma Coordinador`.
- [x] **Auditoría** Tabla `recordatorio` con emisor, destinatario, correo histórico, mensaje, fecha y estado de atención.
- [x] **Bandeja del Coordinador** Aviso con contador y tabla de recordatorios pendientes.
- [x] **Correo** Enlace `mailto:` con asunto y cuerpo prellenados hacia el correo registrado del coordinador (sin SMTP).
- [x] **Cooldown** Un recordatorio por expediente cada 24 h para evitar duplicados.
- [x] **Atención automática** La firma del Coordinador marca los recordatorios como atendidos en la misma transacción.
- [x] **Migración** `scripts/migracion_fase8.py` idempotente y prueba `tests/test_recordatorios.py`.
- [x] Documentación: README, checklist y evidencia `docs/evidencias/2026-11-04_fase8.md`.

**Criterio de aceptación:** el consultor envía un recordatorio desde su
historial, el Coordinador GTC lo ve en su bandeja y, al firmar, el recordatorio
queda atendido. ✅ **Cumplido.**

### Fase 9 — Gestión de usuarios (1 día) · rol IT

- [x] **Rol IT** separado, con acceso solo al panel de usuarios.
- [x] **Listado** con rol, vigencia, última actividad y vacaciones asignadas/usadas/disponibles.
- [x] **Alta** con nombre, correo registrado (cualquier dominio), rol, días y contraseña inicial.
- [x] **Edición** de nombre, correo, rol y días.
- [x] **Baja lógica y reactivación**, sin borrar historial.
- [x] **Reseteo de contraseña** con PBKDF2 y política mínima.
- [x] **Auditoría** en `usuario_log` con ejecutor, afectado, fecha, acción y detalle.
- [x] **Protecciones**: sin autodesactivación, sin cambio de rol propio y sin dejar el sistema sin Administrador ni IT activo.
- [x] **Migración** `scripts/migracion_fase9.py` y pruebas `tests/test_gestion_usuarios.py` (13).
- [x] Documentación: README, checklist y evidencia `docs/evidencias/2026-11-04_fase9.md`.

**Criterio de aceptación:** IT crea una cuenta, la edita, la da de baja, la
reactiva y le restablece la contraseña, y cada operación queda auditada; ningún
otro rol puede gestionar usuarios. ✅ **Cumplido.**

---

### Fase 10 — Versionamiento controlado · `v0.10.0`

- [x] Repositorio público en GitHub con ramas por fase, pull requests y CI.
- [x] Convención documentada en `docs/VERSIONAMIENTO.md`; etiquetas `v0.9.0` y `v0.10.0`.
- [x] Logo de SETESA versionado en `assets/`; la plantilla Excel interna queda fuera de Git.

### Fase 11 — Bandeja del Coordinador por equipo · cierra C-07

- [x] **FK** `solicitud.id_coordinador` → `usuario` (el nombre sigue en `jefe_gtc` para el PDF).
- [x] **Registro**: el consultor elige a su jefe entre los Coordinadores GTC vigentes; ya no se escribe a mano.
- [x] **Bandeja** (Tabla 9): cada coordinador ve solo los expedientes que le fueron asignados.
- [x] **Firma**: `cambiar_estado` rechaza el visto bueno de un coordinador distinto al asignado (`CoordinadorNoAsignado`).
- [x] **Recordatorios (R-11)**: van solo al coordinador asignado, sin reenvío a otro.
- [x] **Migración** `scripts/migracion_fase11.py` (con `--simular` y `--asignar-sin-match ID`).
- [x] Pruebas `tests/test_coordinador_equipo.py` (4 unitarias y 2 de integración).

**Criterio de aceptación:** dos coordinadores no ven ni pueden firmar los
expedientes del otro. ✅ **Cumplido.**

---

### Fase 12 — Reasignación de Coordinador GTC por Gerencia

- [x] **Pestaña** «Reasignar Coordinador» en el panel de Gerencia.
- [x] Lista los expedientes que esperan el visto bueno del banco y resalta los de coordinadores dados de baja.
- [x] **Reasignación** solo a un Coordinador GTC vigente, con motivo obligatorio; el estado no cambia.
- [x] **Historial**: el movimiento queda en `solicitud_historial` con el coordinador anterior, el nuevo y el motivo.
- [x] **Recordatorios (R-11)** sin atender pasan al nuevo coordinador.
- [x] **Aviso a IT**: al dar de baja a un coordinador con expedientes pendientes se indica que Gerencia debe reasignarlos.
- [x] Pruebas `tests/test_reasignacion.py` (4 unitarias y 1 de integración). Sin cambios de esquema.

**Criterio de aceptación:** un expediente del coordinador A pasa a la bandeja
del coordinador B; A ya no puede firmarlo y B sí. ✅ **Cumplido.**

---

### Fase 13 — Triggers de PostgreSQL · tesis 3.6

- [x] **Vigencia automática** (`trg_usuario_vigencia`): si un usuario no protegido lleva más de 6 meses sin actividad, el próximo intento de registrarle actividad aplica la baja lógica y la audita en `vigencia_log`.
- [x] **Depuración diaria** `setesa_depurar_vigencia()` programada con pg_cron (09:00 UTC).
- [x] **Registro** (`trg_solicitud_insert`): nace en *Ingresada*, sin firmas de banco ni Gerencia, de un usuario vigente y hacia un Coordinador GTC vigente.
- [x] **Transiciones** (`trg_solicitud_update`): solo las del workflow, cada una con su firma; las firmas estampadas no cambian; la reasignación solo va a un coordinador vigente.
- [x] **Finalizada inalterable**: solo admite el sello del PDF (`ruta_pdf`, `pdf_hash`, `pdf_hash_fecha`).
- [x] **Sin borrados** de expedientes ni de historial (`trg_solicitud_delete`, `trg_historial_inmutable`); las pruebas usan `SET LOCAL setesa.permitir_borrado = 'on'`.
- [x] **Sin huérfanos** (`trg_solicitud_con_historial`, diferido): toda solicitud confirmada tiene historial.
- [x] **Historial coherente** (`trg_historial_insert`): refleja el estado real y lo registra el actor de cada etapa (consultor dueño, coordinador asignado, Gerencia), siempre vigente.
- [x] El login relee la vigencia después de marcar actividad.
- [x] SQL en `docs/triggers.sql`, migración `scripts/migracion_fase13.py` (`--simular`, `--sin-cron`) y pruebas `tests/test_triggers.py` (15, en una transacción que se revierte).

**Criterio de aceptación:** las reglas del workflow y de vigencia se cumplen
aunque se escriba directamente en la base. ✅ **Cumplido.**

**Nota:** `scripts/migracion_fase6.py` ya no puede reescribir expedientes
finalizados; si se necesitara, debe correr con `setesa.permitir_borrado`.

---

### Fase 14 — «Mis datos» y vigencia por actualización de datos · tesis 1.5 y objetivo c

- [x] **Mis datos** (Consultor y Contabilidad y RR.HH.): el consultor confirma puesto, código de empleado y teléfono; Contabilidad, puesto y teléfono. Nombre, correo y rol siguen a cargo de IT.
- [x] **Plazo de 6 meses** desde `usuario.fecha_actualizacion_datos`; cada confirmación lo renueva (ciclo repetitivo).
- [x] **Aviso** en cada pantalla desde 30 días antes del vencimiento.
- [x] **Vigencia**: la baja lógica automática (app, trigger y pg_cron) aplica solo a quien no actualizó sus datos en 6 meses. Coordinador GTC, Administrador e IT no vencen: IT los da de baja manualmente.
- [x] **IT**: pestañas «Reasignar Coordinador» (también disponible para Gerencia) y «Por vencer», con enlace de correo; la lista de usuarios muestra el plazo de cada uno.
- [x] **Reactivación** (IT o Gerencia) reinicia el plazo de 6 meses.
- [x] El teléfono se guarda cifrado; la auditoría (`ACTUALIZACION_DATOS` en `usuario_log`) registra qué campos cambiaron, sin sus valores.
- [x] El formulario de ausencia precarga puesto y código desde «Mis datos».
- [x] Migración `scripts/migracion_fase14.py` (`--simular`): los usuarios existentes inician su plazo el día de la migración.
- [x] Pruebas: `tests/test_perfil.py` (16) y `tests/test_triggers.py` (20).

**Criterio de aceptación:** quien actualiza sus datos antes del plazo sigue
activo; quien no, pasa a baja lógica sin perder su historial. ✅ **Cumplido.**

**Diferencia con la tesis:** RF-06 habla de "6 meses sin actividad"; por
decisión del 05/11/2026 se mide por la actualización de datos (sección 1.5 y
objetivo c) y los coordinadores del banco quedan fuera de la baja automática.

---

### Fase 15 — Correo automático de recordatorio

- [x] **Envío SMTP** desde la cuenta de SETESA con contraseña de aplicación (`src/services/correo.py`).
- [x] **Etapas** 30, 15, 7 y 1 día(s) antes del plazo; a Consultores y a Contabilidad y RR.HH. vigentes.
- [x] **Sin duplicados** (`aviso_actualizacion`, único por usuario, plazo y etapa); si la tarea no corre un día, al siguiente envía solo la etapa en curso.
- [x] **Tarea diaria** en GitHub Actions (`.github/workflows/recordatorios.yml`, 08:00 de Guatemala) con ejecución manual en modo simulación.
- [x] **Panel de IT**: últimos correos enviados o fallidos en «Por vencer».
- [x] Guía `docs/CORREO.md` (contraseña de aplicación, pooler de Supabase y secretos de GitHub).
- [x] Migración `scripts/migracion_fase15.py` y pruebas `tests/test_avisos.py` (21).

**Criterio de aceptación:** un consultor con el plazo por vencer recibe un
correo por etapa sin entrar al sistema. ✅ **Cumplido** (pendiente de cargar
los secretos de la cuenta de SETESA en GitHub).

---

### Fase 16 — Aprobar o denegar · cierra D-06 / C-08

- [x] **Resolución** al finalizar: *Aprobada* o *Denegada* (`solicitud.resolucion`); se mantienen los 4 estados de la tesis.
- [x] **Coordinador GTC** puede denegar (el banco no otorga el permiso) y cierra el flujo; **Gerencia** aprueba o deniega.
- [x] La denegación exige **motivo** (cifrado) y la **firma** de quien deniega; el motivo no se copia al historial.
- [x] **Saldo de vacaciones**: las solicitudes denegadas no descuentan días (se devuelven).
- [x] **PDF**: recuadro «RESOLUCIÓN: APROBADA / DENEGADA POR …» con el motivo; la firma de Gerencia figura como «(No aplica)» si deniega el banco.
- [x] **Dashboard** con columna de resolución y conteo de aprobadas y denegadas; el consultor ve resolución y motivo en su historial.
- [x] **Triggers**: denegación solo desde las etapas permitidas, por el actor asignado, con motivo y firma; la resolución solo se registra al finalizar.
- [x] Migración `scripts/migracion_fase16.py` (`--simular`) y pruebas `tests/test_denegacion.py` (10) y `tests/test_triggers.py` (27).

**Criterio de aceptación:** una solicitud denegada por el banco o por Gerencia
queda finalizada con su motivo y devuelve los días al saldo. ✅ **Cumplido.**

---

### Fase 17 — Repositorio persistente de expedientes · tesis objetivo d

- [x] **Supabase Storage** (bucket privado `expedientes`) como repositorio de los PDF; Render no conserva archivos entre reinicios. Sin configuración se usa `storage/repositorio/` (desarrollo y pruebas).
- [x] **Borrador** (`pdf/<id>/borrador.pdf`) regenerable mientras el expediente está en trámite.
- [x] **PDF final** (`pdf/<id>/final_<sello>.pdf`) generado una sola vez al resolver el expediente; no se sobrescribe ni se regenera, así su SHA-256 no cambia.
- [x] **Trigger**: con `pdf_inmutable = TRUE` el expediente y su PDF son inalterables; un borrador no puede marcarse como final.
- [x] **Descargas** desde el repositorio (consultor, Gerencia y Contabilidad); verificación de integridad contra el sello.
- [x] El PDF temporal se borra del disco del servidor tras subirse.
- [x] Migración `scripts/migracion_fase17.py` (crea el bucket y sube los PDF locales existentes) y pruebas `tests/test_almacenamiento.py` (10), `tests/test_documentos.py` y `tests/test_triggers.py` (29).

**Criterio de aceptación:** un PDF final sigue disponible e idéntico (mismo
sello) después de reiniciar el servidor. ✅ **Cumplido** (pendiente de cargar
la llave de Supabase).

---

### Fase 18 — Evidencias y aviso a Contabilidad y RR.HH. · tesis figura 43, tabla 65 y 4.12.3 paso 6

- [x] **Evidencias** PDF/JPG/PNG de hasta 5 MB (tipo verificado por contenido) al registrar o mientras la solicitud está en trámite; se guardan en el bucket privado con su SHA-256.
- [x] **SUSPENSIÓN IGSS** exige al menos una evidencia (app y trigger diferido).
- [x] **Acceso**: consultor dueño, Contabilidad y RR.HH. y Gerencia; el Coordinador GTC no las ve. Se verifican contra su sello al descargarlas.
- [x] **Triggers**: evidencias inmutables, solo del dueño vigente y no en expedientes finalizados.
- [x] **Aviso al finalizar** (`trg_solicitud_notificar`): notificación para Contabilidad y RR.HH. y para el consultor, sin el motivo; sección «🔔 Avisos» con contador y enlace mailto al consultor. Del aviso solo cambia «leída».
- [x] **Nombre visible** «Contabilidad y RR.HH.» (y «Administrador (Gerencia)») en menú, títulos y panel de IT; en la base el rol sigue como `Contabilidad`.
- [x] Migración `scripts/migracion_fase18.py` y pruebas `tests/test_evidencias.py` (21) y `tests/test_triggers.py` (34).

**Criterio de aceptación:** una SUSPENSIÓN IGSS no se registra sin constancia,
y al finalizar un expediente Contabilidad y RR.HH. recibe el aviso. ✅ **Cumplido.**

---

### Fase 19 — PDF fiel a la plantilla Excel oficial

- [x] **Geometría de la plantilla** (`Accion Personal - Solicitud de Ausencias - SETESA.xlsx`): anchos de columna A–I, alto de filas, bordes, fuentes Arial 9/20 y escala de impresión del 95 %.
- [x] **Logo de SETESA** en C1 (aplanado sobre blanco) y título «ACCION DE PERSONAL» en C7:I8.
- [x] **Campos** DE, PARA, CODIGO, PUESTO y FECHA en sus posiciones, con línea y valor.
- [x] **Cuadrícula** de 3 bloques con casillas, en el orden de la hoja; la opción elegida se marca con «X».
- [x] **Fechas** dd/mm/aaaa («Del … al …», FECHA) y «Cantidad de dias».
- [x] **Recuadro de explicación** de 8 filas con la NOTA de RR.HH.; el texto se ajusta (9 → 7 pt) y la app limita la explicación a 1200 caracteres.
- [x] **Firmas** sobre las líneas de JEFE INMEDIATO GTC, EMPLEADO QUE SE LE APLICA y SETESA, con el nombre debajo.
- [x] Diferencias deliberadas: filas 49–50 más altas para las firmas digitales; resolución y pie con el número de expediente debajo de las firmas.
- [x] Pruebas `tests/test_motor_pdf.py` (10); conteos de imágenes actualizados (logo + firmas).

**Criterio de aceptación:** el PDF generado reproduce la hoja oficial con los
datos de la solicitud. ✅ **Cumplido.**

---

### Fase 20 — Seguridad de sesión · tesis 4.2 (OWASP, sesiones seguras)

- [x] **Límite de intentos**: 5 contraseñas incorrectas seguidas bloquean el acceso 15 minutos; durante el bloqueo ni la contraseña correcta sirve. El conteo vive en la base (`intento_login`), no en la sesión, así que otra pestaña o navegador no lo reinicia.
- [x] **Sin enumeración de cuentas**: el conteo es por correo escrito, exista o no, con el mismo mensaje y un tiempo de respuesta parejo (hash de relleno).
- [x] **Expiración de sesión**: 30 minutos de inactividad o 8 horas de duración máxima (`SESSION_IDLE_MINUTES`, `SESSION_MAX_HOURS`); al vencer se cierra la sesión y se pide iniciar de nuevo.
- [x] **IT** ve los accesos bloqueados y puede desbloquearlos (auditado como `DESBLOQUEO`); restablecer la contraseña también levanta el bloqueo.
- [x] Migración `scripts/migracion_fase20.py` y pruebas `tests/test_seguridad_sesion.py` (19; las de base de datos corren en una transacción que se revierte).

**Criterio de aceptación:** tras 5 intentos fallidos el acceso se bloquea y una
sesión inactiva se cierra sola. ✅ **Cumplido.**

**Límite conocido:** Streamlit solo evalúa la expiración cuando el usuario
interactúa; una pestaña abandonada se cierra en su siguiente clic.

---

### Fase 21 — Indicadores del dashboard y catálogo de motivos · tesis (variables) y 6.4.4

- [x] **Tiempo promedio de aprobación** (de la solicitud a su resolución), por etapa (banco y Gerencia) y por resolución (aprobadas y denegadas).
- [x] **Usuarios vigentes e inactivos**, porcentaje de inactivos y usuarios por vencer en 30 días; visibles para Gerencia y Contabilidad y RR.HH.
- [x] **Catálogo de motivos mantenible** (`motivo_ausencia`), con Gerencia como responsable: agrega motivos y activa o desactiva; los 22 de la plantilla oficial no se renombran ni se eliminan.
- [x] **VACACION** y **SUSPENSIÓN IGSS** tienen regla propia y no se desactivan.
- [x] **Lista cerrada** también en la base: un trigger rechaza motivos que no estén en el catálogo o estén desactivados; las solicitudes anteriores los conservan.
- [x] Un motivo nuevo no tiene casilla en la hoja oficial: el PDF marca «OTROS» y escribe su nombre.
- [x] El formulario de ausencia lee los motivos activos del catálogo (con la lista de la plantilla como respaldo).
- [x] Migración `scripts/migracion_fase21.py` (siembra los 22 motivos) y pruebas `tests/test_fase21.py` (25) y `tests/test_triggers.py` (42).

**Criterio de aceptación:** Gerencia agrega un motivo y aparece en el
formulario; el dashboard muestra tiempos promedio y usuarios inactivos. ✅ **Cumplido.**

---

### Fase 22 — Prueba del flujo completo (antes de producción)

- [x] `tests/test_flujo_completo.py`: 30 pasos con los cinco roles contra la base de pruebas (datos temporales que se borran al terminar; repositorio de archivos en una carpeta temporal y correo simulado).
- [x] **Cubre**: alta de usuarios por IT y sus validaciones; inicio de sesión, bloqueo a los 5 intentos y desbloqueo; expiración de sesión; «Mis datos» (teléfono cifrado); catálogo de motivos; vacaciones con descuento de saldo; bandeja del coordinador asignado; recordatorio al banco; visto bueno y aprobación; avisos a Contabilidad y al consultor; PDF final inmutable con sello estable y detección de alteración; expediente finalizado inalterable.
- [x] **Denegaciones** por el banco y por Gerencia (motivo y firma obligatorios, días devueltos al saldo, motivo ausente del aviso); **evidencias** (IGSS obligatoria y acceso por rol); motivo nuevo impreso como «OTROS»; **reasignación** al salir un coordinador.
- [x] **Vigencia** (baja por no actualizar datos, reactivación con plazo nuevo, roles sin vencimiento) y **recordatorio por correo** una vez por etapa; **dashboard** e indicadores.
- [x] **Pantallas** de los cinco roles (AppTest), inicio de sesión por formulario y arranque real del servidor de Streamlit.
- [x] `docs/PRUEBA_MANUAL.md`: guion de 5 a 10 minutos para lo que solo se comprueba en un navegador (firma dibujada, archivos y aspecto).

**Resultado:** 30 de 30 pasos en verde; la base de pruebas quedó limpia.
Dos ajustes en la propia prueba (firma de ejemplo con fondo blanco, como las
reales, y asignación de la sesión de IT); ningún defecto en la aplicación.

### Fase 23 — Identidad visual de SETESA (azul y blanco)

- [x] **Tema** (`.streamlit/config.toml`): azul marino `#203868` y celeste `#68B0D8` del logo, fondo blanco y bordes redondeados; encabezado de tablas en azul; barra lateral azul; menú reducido de Streamlit.
- [x] **Estilos propios** (`src/ui/estilos.py`): banner degradado en cada panel, tarjetas de indicadores con borde azul, pestañas, formularios, botones y fondo suaves. Si un estilo fallara, la aplicación sigue funcionando.
- [x] **Inicio de sesión**: logo, tarjeta centrada y botón azul; el mensaje de error indica el límite de intentos.
- [x] **Barra lateral**: logo de SETESA, tarjeta del usuario con su rol (nombre visible, p. ej. «Contabilidad y RR.HH.») y «Cerrar Sesión»; arranca expandida.
- [x] **Tablas** del dashboard con los estados y resoluciones resaltados; sin «None» en las columnas sin dato.
- [x] **Ícono de la pestaña** con el emblema de SETESA y pie de página.
- [x] Los textos que vienen de la base se escapan antes de mostrarse como HTML (nombre del usuario, títulos).
- [x] Se reemplazó el ícono 🪪 (no existe en Windows 10) por 👤.
- [x] Pruebas `tests/test_estilos.py` (8); la prueba del flujo completo, las pantallas por rol y el control de acceso siguen en verde.
- [x] Revisión con capturas reales en Edge (inicio de sesión y los cinco roles).

**Límites de Streamlit:** el recuadro donde se dibuja la firma y el selector de
archivos son componentes del propio Streamlit (textos y aspecto internos); los
estilos usan sus selectores `data-testid`, por eso la versión está fijada en
`requirements.txt`.

---

### Fase 24 — Ajustes tras las pruebas manuales

- [x] **Rendimiento** (la app tardaba 10–16 s por clic desde Guatemala): el cuello de botella no era Streamlit sino los viajes a la base de datos (una conexión nueva a Supabase cuesta ~1 s y cada consulta ~0,25 s).
  - **Reserva de conexiones** reutilizables (`src/core/database.py`): la conexión reutilizada cuesta 0 ms; las inactivas se validan antes de usarse.
  - **Guardado temporal de lecturas** (`src/core/cache.py`, 15 a 300 s): catálogos, perfil, indicadores, listas y bandejas. Toda función que escribe (`@escritura`) invalida lo guardado. Las validaciones de negocio (p. ej. el saldo de vacaciones al registrar) leen siempre directo de la base.
  - **Pestañas perezosas** en Gerencia e IT: solo se ejecuta la pestaña visible.
  - Vigencia de la sesión revisada cada 30 s (no en cada clic); el PDF final se descarga y verifica una sola vez; el historial del consultor ya no trae ni descifra las firmas.
  - **Resultado medido:** cualquier clic del consultor, coordinador e IT pasa de 11 / 2 / 5 s a ~0,1 s; Gerencia y Contabilidad de ~10 s a ~1 s.
- [x] **Filtros del repositorio histórico** (Gerencia y Contabilidad y RR.HH.): selector con todos los colaboradores (los inactivos marcados; al elegir uno se avisa que está inactivo) y todos los motivos del catálogo en «Tipo de incidencia».
- [x] **Soporte**: contacto de IT (`soporte-it@setesagt.com`, configurable con `SOPORTE_CORREO`) en el pie de todas las pantallas, incluido el inicio de sesión, y en el mensaje de bloqueo.
- [x] **Cambio de contraseña**: «🔑 Mi contraseña» para todos los roles. IT asigna una contraseña **temporal** (al crear la cuenta o al restablecerla) y el usuario **debe cambiarla** al iniciar sesión antes de usar el sistema. Los fallos al verificar la contraseña actual cuentan para el bloqueo; queda auditado (`CAMBIO_PASSWORD`).
- [x] Solo IT restablece contraseñas y desbloquea accesos.
- [x] Migración `scripts/migracion_fase24.py` y pruebas `tests/test_fase24.py` (26).

**Para el despliegue:** la latencia que se nota hoy es de tu equipo hacia Oregón; si
Render se crea en la región de Oregón (junto a Supabase, `us-west-2`) la distancia a
la base de datos es de pocos milisegundos.

### Fase 25 — Retiro de solicitudes y avisos por correo del flujo

- [x] **Retirar solicitud** (extensión que no está en la tesis; se informa al usuario): el consultor dueño puede retirar su solicitud mientras no tenga el visto bueno del banco. El expediente queda *Finalizado* con resolución **Retirada** (se mantienen los 4 estados), con motivo obligatorio cifrado y registro en el historial.
- [x] Los días de vacaciones vuelven al saldo; no se genera PDF oficial; no cuenta en los tiempos de resolución ni avisa a Contabilidad como resolución.
- [x] La base lo exige (triggers): solo el dueño, solo en esas etapas, con motivo; migración `scripts/migracion_fase25.py`.
- [x] **Avisos por correo** (`src/core/avisos_flujo.py`): solicitud nueva → Coordinador GTC; visto bueno → Gerencia; retiro → Coordinador GTC; resolución → consultor y Contabilidad. Solo número, persona, tipo y fechas (nunca explicación, motivo ni firmas); mejor esfuerzo y en segundo plano: si el correo falla, el flujo sigue.
- [x] Pruebas `tests/test_fase25.py` (15); las pruebas nunca envían correo real (`SETESA_SIN_CORREO`).

---

### Fase 26 — Despliegue del prototipo (EN CURSO)

- [x] Proyecto Supabase de producción independiente (`setesa_produccion`, us-west-2), base vacía; secretos propios y nuevos (`FERNET_KEY`, llave secreta) en `.env.produccion` (ignorado por git).
- [x] `scripts/instalar_produccion.py`: instalador limpio (esquema + migraciones estructurales sin cuentas de demostración + bucket privado + único usuario IT con cambio de contraseña obligatorio). Se niega a correr sobre una base con usuarios o igual a la de pruebas.
- [x] `render.yaml`: Render en Oregón, plan gratuito (temporal, mientras SETESA aprueba el presupuesto).
- [x] Instalador ejecutado en producción (2026-11-05): 13 tablas, 27 triggers, pg_cron, bucket privado `expedientes`, 22 motivos, 30 feriados y un único usuario IT. Esquema comparado con la base de pruebas: columnas, restricciones, índices, triggers, funciones y roles idénticos.
- [x] `scripts/respaldo.py`: respaldo completo (13 tablas en .jsonl + archivos del bucket con SHA-256 + manifiesto) y restauración transaccional (todo o nada, con `--simular`). Ensayado con rollback en pruebas y en producción.
- [x] Cuenta de Render con plan gratuito creada por el usuario (2026-11-05).
- [x] `docs/DESPLIEGUE.md`: sección 8b (Render, instalador, respaldo, plan gratuito).
- [x] Publicado en Render mediante Blueprint (2026-11-05): servicio en línea, ingreso de IT y cambio de contraseña obligatorio verificados en la URL real.
- [x] Ensayo del flujo (2026-11-05): registro, visto bueno, aprobación, contabilidad/RR.HH., PDF con firmas y retiro funcionan en la URL real.
- [x] Corrección de fechas del PDF: el servidor está en UTC y tras las 18:00 marcaba el día siguiente. `TZ=America/Guatemala` (config y `render.yaml`) + migración 26 (zona horaria de la base).
- [x] Comando de la migración 26 con `--env .env.produccion` (evita fallos por saltos de línea de Windows al leer el archivo).
- [x] Migración 26 aplicada en producción (2026-11-05): zona horaria de la base = America/Guatemala. Verificado por el usuario con un flujo nuevo: el PDF lleva la fecha actual.
- [ ] Solución exprés para la presentación (2026-11-05): Brevo por SMTP puerto 2525 con remitente verificado, solo variables de Render (sin código). Pendiente que el usuario la configure y pruebe.
- [ ] Después de la presentación: dominio propio (subdominio vía DNS de setesagt.com, hoy solo el dominio está en Hostinger, sin hosting ni VPS), botón de Avisos con remitente correcto, lentitud (plan Starter o consultas).
- [ ] Correos automáticos no llegan (Render gratuito bloquea los puertos SMTP 25/465/587): cambiar de proveedor/puerto.
- [ ] Botón de recordatorio de «Avisos» (mailto) no usa el correo del usuario que lo envía.
- [ ] Lentitud de la app en el plan gratuito.
- [ ] Ensayar el flujo completo en la URL real (usuarios de cada rol, solicitud de extremo a extremo, correos SMTP, PDF y firmas).
- [ ] Etiqueta `v1.0.0` tras el ensayo.

---

## 9. Definición de “terminado” (DoD) para cada fase

Una tarea se considera cerrada solo si:

1. El código compila y la app arranca (`streamlit run app.py`).
2. La prueba automatizada de la tarea pasa.
3. El smoke test completo sigue en verde (**sin regresiones**).
4. Se actualizó este checklist y, si aplica, la evidencia en `docs/`.
5. No quedan datos de prueba en la base.

---

## 10. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Migrar estados rompe datos existentes | Media | Alto | Backup + migración idempotente + `CHECK` después de limpiar |
| La firma de gerencia no tiene autorización formal de SETESA | Alta | Medio | Mantener leyenda “Pendiente Autorización” hasta autorización; documentar como condición administrativa (ya previsto en la tesis) |
| El algoritmo de vigencia bloquea cuentas clave | Media | Alto | Salvaguarda de roles + `vigencia_log` + reactivación |
| Cifrado rompe PDFs históricos | Baja | Medio | Migración idempotente, respaldo previo y pruebas de descifrado con expedientes reales |
| Pérdida o rotación accidental de `FERNET_KEY` | Baja | Alto | Custodia en gestor de secretos; no rotar sin recifrar; el respaldo previo contiene texto claro |
| Cambios de alcance (rechazos, correo, nómina) | Media | Medio | Registrarlos como “límites” (sección 1.8 de la tesis) y no implementarlos sin aprobación |

---

## 11. Estado global (semáforo)

| Área | Cumplimiento estimado | Estado |
|---|---|---|
| Autenticación / RBAC | 100 % | 🟢 |
| Gestión de usuarios | 100 % | 🟢 |
| Registro de solicitudes | 100 % | 🟢 |
| Motor PDF | 90 % | 🟢 |
| Workflow / trazabilidad | 90 % | 🟢 |
| Firmas (3 roles) | 95 % | 🟢 |
| Dashboard / métricas | 100 % | 🟢 |
| Vigencia | 95 % | 🟢 |
| Vacaciones / feriados | 100 % | 🟢 |
| Seguridad RNF | 100 % | 🟢 |
| Pruebas / evidencias | 100 % | 🟢 |
| Documentación técnica | 100 % | 🟢 |
| **Total ponderado** | **~99 %** | 🟢 |

El 1 % restante corresponde a D-06 (rechazo/devolución, fuera de alcance). El
endurecimiento del login es una mejora adicional, no un requisito pendiente de
la tesis.

---

## 12. Próximo paso recomendado

Las fases 0–9 están cerradas. Para la entrega y defensa:

1. ~~Transcribir a las tablas 25, 26 y 27 del PDF de la tesis el estado final~~
   **No aplica:** el documento de tesis quedó cerrado el 04/11/2026 y no se
   modifica; las mejoras posteriores se documentan solo en este repositorio.
2. Preparar la demostración: login por rol (incluidos **Contabilidad** e **IT**),
   registro con firma, aprobación GTC, autorización de Gerencia, descarga del PDF
   sellado y verificación SHA-256.
3. Mostrar la evidencia de calidad: 118 pruebas pytest, 57 checks E2E y CI en
   GitHub Actions.
4. Confirmar la custodia de `FERNET_KEY` y el respaldo de Supabase antes de la
   presentación.
5. Siguiente mejora acordada: **endurecimiento del login** (límite de intentos
   fallidos y bloqueo temporal).

Con las Fases 0–9 cerradas, el proyecto queda listo para la defensa con evidencia
de QA y RNF verificables.

---

*Documento generado como parte del análisis del proyecto. Se actualizará al
cerrar cada fase.*
