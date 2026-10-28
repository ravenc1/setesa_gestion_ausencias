# Checklist de Avance y Plan de Continuación — Proyecto SETESA

> **Documento de trabajo** elaborado a partir de la lectura completa de
> `proyecto_doc/PG2 - Proyecto SETESA.pdf` (211 páginas) y de la inspección del
> código, la base de datos PostgreSQL (Supabase) y las pruebas existentes.
> Fecha de corte: **27/10/2026**.
>
> Este archivo es la guía viva para continuar el desarrollo. Se actualiza al
> cerrar cada fase.

---

## 1. Resumen ejecutivo

El proyecto tiene una **base sólida y funcional**: los 7 módulos existen, el
flujo Consultor → Coordinador → Gerencia → PDF se ejecuta de extremo a extremo y
la prueba E2E actual pasa **38/38**. La arquitectura de tres capas está
respetada, la seguridad de contraseñas (PBKDF2) está resuelta y, tras las fases
0–3, el workflow es trazable, las **tres firmas** se capturan y se estampan, y
la **vigencia semestral** es automática, auditable y reversible.

La inspección inicial encontró brechas de coherencia entre lo que la tesis
declara y lo que el sistema realmente hace. **Todos los defectos P0 están
cerrados:**

1. ~~`ultima_actividad` nunca se actualiza~~ **Resuelto Fase 3:** se actualiza en
   login y en cada escritura relevante; los usuarios vigentes ya no corren riesgo
   de baja masiva.
2. ~~El estado legado fuera de catálogo~~ **Resuelto Fase 1.**
3. ~~Las firmas de Coordinador y Gerencia no se capturaban~~ **Resuelto Fase 2**
   (PR-06 cerrado).

Quedan brechas **P1/P2** ya planificadas: dashboard completo (filtros, KPIs,
descarga y exportación), saldo de vacaciones, feriados, cifrado en reposo y sello
de integridad del PDF.

**Conclusión:** el sistema está ~90 % funcional y ~88 % de cumplimiento
verificable contra la tesis. Con las fases 4 a 6 (aprox. 4.5 días de trabajo) se
puede cerrar al 100 % con evidencia de QA.

### Registro de avance

| Fecha | Fase | Resultado |
|---|---|---|
| 27/10/2026 | **Fase 0** | `docs/schema.sql`, `README.md`, `pytest.ini`, backup JSON y pruebas automatizadas. |
| 27/10/2026 | **Fase 1** | `solicitud_historial`, transiciones centralizadas, decisión D-01 (opción C), `CHECK` + índices, estado legado migrado y dashboard sin saltos. |
| 27/10/2026 | **Fase 2** | Canvas y firma obligatoria de Coordinador y Gerencia, PDF con 3 firmas, `ruta_pdf`, nombres únicos y limpieza de temporales. **PR-06 cerrado.** |
| 27/10/2026 | **Fase 3** | `ultima_actividad` en login/acciones, `vigencia_log`, protección de Administrador, ejecución automática semestral, reactivación e invalidación de sesiones. **H-01/H-06 cerrados; QA-01/QA-06/PR-05 completos.** |

**Evidencias:** `docs/evidencias/2026-10-27_fase0-1.md`,
`docs/evidencias/2026-10-27_fase2.md` y
`docs/evidencias/2026-10-27_fase3.md`.
**Pruebas al cierre:** `pytest` 50/50 y smoke test 38/38, sin datos de prueba
residuales en la base.

**Hallazgos cerrados:** H-01, H-02, H-03, H-04, H-05, H-06, H-10, H-12, H-14,
H-15 y D-01.
**Hallazgos que siguen abiertos:** H-07…H-09, H-11 y H-13 (Fases 4–6).

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
| `python tests/smoke_test.py` | **14/14 OK** en la línea base (hoy 38/38) |
| Búsqueda de actualizaciones de `ultima_actividad` | **0 ocurrencias** de `UPDATE` |
| Búsqueda de escritura de `firma_jefe_gtc` / `firma_gerencia` | **0 ocurrencias** de escritura |
| Búsqueda de escritura de `ruta_pdf` | **0 ocurrencias** de escritura |
| Catálogo de estados vs. datos reales | 1 registro con estado fuera de catálogo |

**Línea base de calidad:** el smoke test valida el camino feliz, pero **no**
prueba RBAC negativo entre roles, ni filtros del dashboard. La vigencia y el
login inactivo ya cuentan con pruebas específicas (Fase 3).

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
| N-05 | Cálculo de días hábiles | 🟡 | `utils.py` cuenta lun–vie; **no excluye feriados** | H-26 |
| N-06 | Hashing PBKDF2 + migración | ✅ | `security.py`, `scripts/hash_passwords.py` | — |
| N-07 | RBAC por módulo | ✅ | `rol_autorizado()` + revalidación de vigencia en cada rerun (`app.py`) | — |
| N-08 | **Esquema SQL versionado** | ✅ | `docs/schema.sql` validado en esquema temporal | — |
| N-09 | README de instalación/ejecución | ✅ | `README.md` | — |
| N-10 | Pruebas automatizadas (pytest) | ✅ | 50 pruebas (unitarias, integración, PDF, vigencia y AppTest) | — |
| N-11 | Advertencia `pd.read_sql_query` | 🔧 | Pandas exige SQLAlchemy | H-31 |
| N-12 | Limpieza de firmas temporales | ✅ | `utils_firma.eliminar_archivo` + `finally` en el motor; verificado por `test_documentos` | — |
| N-13 | Logging de errores | 🔴 | Se usa `st.error()` dentro de la capa de datos | H-32 |

### 4.2 Módulo `auth.py` (RF-01 / RNF-01)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| A-01 | Login con correo + contraseña | ✅ | Verifica hash y auto-migra texto plano |
| A-02 | Bloqueo de usuario inactivo | ✅ | Mensaje “Usuario inactivo (Baja Lógica)” |
| A-03 | Enrutamiento por rol | ✅ | `app.py` → Consultor / Coordinador GTC / Administrador |
| A-04 | **Actualizar `ultima_actividad`** | ✅ | Login y acciones relevantes (`marcar_actividad`); solo usuarios vigentes |
| A-05 | Normalizar correo (trim/lower) | ✅ | `login_user` normaliza entrada y compara con `LOWER(...)` |
| A-06 | Revalidar vigencia en sesión activa | ✅ | `app.py` expulsa sesiones dadas de baja en cada rerun |
| A-07 | Sesión con `id_rol` y expiración | 🔧 | Solo guarda nombre/rol/id |
| A-08 | Recuperación de contraseña | 🔴 | Fuera del alcance mínimo; documentar como límite |

### 4.3 Módulo `registro.py` (RF-02 / RF-03 / RF-06 / HU-01)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| R-01 | Formulario de Acción de Personal | ✅ | Jefe, puesto, código, fechas, naturaleza, explicación |
| R-02 | Cálculo de días hábiles en vivo | ✅ | `st.metric` + validación de rango |
| R-03 | Canvas de firma del consultor | ✅ | `streamlit-drawable-canvas`, Base64, recorte y fondo blanco |
| R-04 | Inserción transaccional | ✅ | `commit` correcto; el PDF se genera desde la BD y persiste `ruta_pdf` |
| R-05 | Generación y descarga del PDF | ✅ | Se genera al firmar y se descarga |
| R-06 | Historial personal + PDF actualizado | ✅ | Consulta filtrada por `id_usuario` (RBAC de datos) |
| R-07 | **Saldo de días de vacaciones** | 🔴 | **RF-01** lo exige; no existe campo ni cálculo |
| R-08 | Estado inicial según tesis | ✅ | Opción C: `Ingresada` → `Pendiente de Firma Coordinador` en la misma transacción | — |
| R-09 | Validar `fecha_fin >= fecha_inicio` | 🔧 | Si el usuario mueve el inicio, el fin no se reajusta; mensaje engañoso |
| R-10 | Guardar `ruta_pdf` | ✅ | `services/documentos.py` actualiza la columna tras cada generación |
| R-11 | Alertas/recordatorios al banco | 🔴 | Diseño (Tabla 9) lo menciona; no implementado |
| R-12 | Seleccionar jefe GTC desde usuarios | 🔧 | Hoy es texto libre; puede asignarse a cualquiera |
| R-13 | Feriados de Guatemala | 🔧 | Solo fines de semana |

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
| P-08 | Documento “inalterable” | 🔴 | No hay sello/hash de integridad (RNF / Dto. 47-2008) |
| P-09 | Limpieza de imágenes temporales | ✅ | Se eliminan en `finally` tras generar el PDF |
| P-10 | Centralizar `limpiar_nombre` | 🔧 | Lógica de presentación dentro del motor |

### 4.5 Módulo `coordinador.py` (CU-04 / RF-04 / RF-06 / PR-04)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| C-01 | Bandeja de solicitudes | ✅ | Filtra por `Ingresada`, orden FIFO |
| C-02 | Transición a “Pendiente de Aprobación Gerencia” | ✅ | `UPDATE` + `commit` |
| C-03 | **Canvas de firma del coordinador** | ✅ | `st_canvas` obligatorio antes de aprobar |
| C-04 | **Persistir `firma_jefe_gtc`** | ✅ | `cambiar_estado(..., firma_b64=...)` en la misma transacción |
| C-05 | Validar transición permitida | ✅ | `cambiar_estado` bloquea con `FOR UPDATE` + grafo de transiciones | — |
| C-06 | Ver el PDF antes de firmar | 🔴 | No hay vista previa del expediente |
| C-07 | Asignación por equipo/coordinador | 🔧 | Ve todas las solicitudes, no solo “las de su equipo” |
| C-08 | Rechazo / devolución con motivo | 🔴 | No definido en la tesis; decidir D-06 |
| C-09 | Evidencia de auditoría | ✅ | `solicitud_historial` registra actor, fecha y observación | — |

### 4.6 Módulo `dashboard.py` (RF-04 / HU-03 / QA-04)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| D-01 | KPIs básicos | 🟡 | Total, Ingresadas, Finalizadas (faltan pendientes y por tipo) |
| D-02 | Filtro por nombre | ✅ | `str.contains` |
| D-03 | Filtro por estado | ✅ | Selector dinámico |
| D-04 | **Filtro por fecha (rango)** | 🔴 | **RF-04** lo exige |
| D-05 | **Filtro por tipo de incidencia** | 🔴 | **RF-04** lo exige |
| D-06 | **Descarga del PDF final** | 🔴 | **HU-03** lo exige; hoy no hay botón |
| D-07 | **Canvas de firma de gerencia** | ✅ | `st_canvas` obligatorio antes de finalizar |
| D-08 | **Persistir `firma_gerencia`** | ✅ | `cambiar_estado(..., firma_b64=...)` en la misma transacción |
| D-09 | Transiciones válidas (no saltos) | ✅ | Solo `Pendiente de Aprobación Gerencia` → `Finalizada` desde Gerencia | — |
| D-10 | Exportar métricas (CSV/Excel) | 🔴 | La tesis lo menciona como mejora en curso |
| D-11 | Alertas de pendientes | 🔴 | “Gerencia recibe alerta” (4.12.3) |
| D-12 | Rol Contabilidad (solo lectura) | 🔴 | Tabla 9 y HU-03 lo mencionan; no existe el rol (D-02) |
| D-13 | Paginación | 🔧 | Con muchos registros la tabla se vuelve pesada |

### 4.7 Módulo `vigencia.py` (RF-05 / CU-06 / QA-06)

| # | Ítem | Estado | Detalle |
|---|---|---|---|
| V-01 | Detección de > 6 meses | ✅ | `ultima_actividad < CURRENT_DATE - INTERVAL '6 months'` |
| V-02 | Baja lógica sin borrado | ✅ | `UPDATE estado_vigencia = FALSE` |
| V-03 | Reporte de afectados | ✅ | DataFrame con los desactivados |
| V-04 | **Dependencia de `ultima_actividad`** | ✅ | Se actualiza en login y escrituras; cubierto por `test_vigencia` |
| V-05 | Salvaguarda de administradores | ✅ | `ROLES_PROTEGIDOS` excluye Administrador; también se excluye al ejecutor |
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
| F-04 | Cifrado de la firma en BD | 🔴 | Se guarda Base64 en claro (RNF-01) |
| F-05 | Validación de tamaño/formato | 🔧 | No limita peso ni valida PNG |
| F-06 | Limpieza posterior | ✅ | `eliminar_archivo` tras generar el PDF |

---

## 5. Checklist de pruebas y evidencias

| ID | Caso | Estado declarado en tesis | Estado real verificado | Brecha |
|---|---|---|---|---|
| QA-01 | Login usuario inactivo | Aprobado | ✅ `test_login_usuario_inactivo_es_rechazado` (AppTest) | — |
| QA-02 | Enrutamiento por rol | Aprobado | ✅ AppTest renderiza los 3 paneles | — |
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

**Cobertura automatizada actual:** 50 pruebas pytest + 38 checks del smoke test.
Cubren: días hábiles, seguridad, transiciones válidas/inválidas, historial,
firma obligatoria y persistida, PDF con 3 imágenes, `ruta_pdf`, limpieza de
temporales, integración contra BD real, render de los 3 paneles, login inactivo
(QA-01) y vigencia con fechas controladas (QA-06). **Faltan:** RBAC negativo
entre roles, filtros del dashboard, cifrado y sello del PDF.

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

| ID | Hallazgo | Requerimiento |
|---|---|---|
| H-07 | Falta saldo de días de vacaciones | RF-01 |
| H-08 | Faltan filtros por fecha y tipo en el dashboard | RF-04 |
| H-09 | Falta descarga del PDF final desde el dashboard | HU-03 |
| ~~H-10~~ ✅ | ~~`ruta_pdf` nunca se guarda~~ **Resuelto Fase 2** | `services/documentos.py` persiste la ruta | RF-03 / trazabilidad |
| H-11 | Datos sensibles y firmas sin cifrar | RNF-01 |
| ~~H-12~~ ✅ | ~~Esquema SQL no versionado~~ **Resuelto Fase 0** | `docs/schema.sql` validado en esquema temporal | Reproducibilidad / defensa |
| H-13 | PDF sin sello de integridad | “Inalterable” / Dto. 47-2008 |

### P2 — Calidad, robustez y acabado

| ID | Hallazgo |
|---|---|
| ~~H-14~~ ✅ | ~~Nombres de PDF y de firmas temporales colisionan~~ **Resuelto Fase 2** |
| ~~H-15~~ ✅ | ~~Sin limpieza de archivos temporales~~ **Resuelto Fase 2** |
| H-16 | Validación de fechas y mensajes de error |
| H-17 | Feriados de Guatemala no considerados |
| H-18 | Jefe GTC como texto libre |
| H-19 | 🟡 Suite unitaria + integración + AppTest lista; falta CI |
| H-20 | 🟡 README listo; falta guía de despliegue |
| H-21 | Advertencia de pandas / SQLAlchemy |
| H-22 | Sin paginación ni exportación |
| H-23 | Sin logging estructurado |

---

## 7. Decisiones que requieren tu confirmación

| ID | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D-01** | Estado al registrar una solicitud | (A) `Ingresada` y el coordinador firma desde ahí · (B) `Pendiente de Firma Coordinador` desde el inicio · (C) registrar `Ingresada` y transicionar en la misma transacción, dejando historial de ambos | **C**: cumple HU-01/QA-03 y el paso 3 de 4.12.3, y hace que los 4 estados existan de verdad |
| **D-02** | Rol “Contabilidad” | (A) Crear rol de solo lectura · (B) mantener solo Administrador | **A** si la defensa exige HU-03; **B** si se prioriza tiempo |
| **D-03** | Origen del saldo de vacaciones | (A) campo `dias_vacaciones_asignados` en `usuario` · (B) cálculo por año a partir de solicitudes · (C) ambos | **C** (asignado – usado = disponible) |
| **D-04** | Feriados | (A) tabla `feriado` administrable · (B) lista fija en código | **A** (más auditable) |
| **D-05** | Cifrado de datos sensibles | (A) Fernet en la app · (B) `pgcrypto` en PostgreSQL | **A** (clave en `.env`, sin exponerla a la BD) |
| **D-06** | Rechazo/devolución | (A) agregar estado `Devuelta` con motivo · (B) fuera de alcance | **B** para no ampliar el alcance de la tesis; documentarlo como límite |

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

- [ ] **H-08** Filtros por rango de fechas y por tipo de incidencia (además de nombre y estado).
- [ ] **D-01** KPIs completos: por estado, por tipo, pendientes de coordinador, pendientes de gerencia.
- [ ] **H-09** Botón de descarga del PDF final con todas las firmas (HU-03).
- [ ] **D-10** Exportación CSV/Excel del resultado filtrado.
- [ ] **D-11** Alertas in-app de solicitudes pendientes.
- [ ] **D-02** Rol Contabilidad de solo lectura (si se aprueba).
- [ ] **D-13** Paginación del repositorio.
- [ ] Pruebas: cada filtro por separado y combinados; descarga con firmas; permisos del rol.

**Criterio de aceptación:** Gerencia/Contabilidad pueden encontrar un expediente
por nombre, fecha y tipo, ver sus KPIs y descargar el PDF final.

### Fase 5 — RF-01 y validaciones de negocio (1 día) · P1

- [ ] **H-07/D-03** Saldo de vacaciones: días asignados, usados y disponibles en el panel del consultor.
- [ ] **H-16** Validar `fecha_fin >= fecha_inicio` en servidor y corregir mensajes.
- [ ] **H-17/D-04** Descontar feriados de Guatemala.
- [ ] **H-18** Seleccionar al jefe GTC desde los usuarios con rol Coordinador.
- [ ] **R-11** Recordatorio al banco (registro de alerta o enlace `mailto`).
- [ ] Pruebas: saldo correcto tras varias solicitudes; fechas inválidas rechazadas; feriado descontado.

**Criterio de aceptación:** RF-01 se cumple de punta a punta y las validaciones
no permiten datos imposibles.

### Fase 6 — RNF, cierre y documentación (1.5 días) · P1/P2

- [ ] **H-11/D-05** Cifrar `explicacion` y firmas en reposo.
- [ ] **H-13** Sello SHA-256 del PDF + registro para verificación de integridad.
- [ ] **H-21** Migrar a SQLAlchemy (elimina warning y mejora pool).
- [ ] **H-23** Logging centralizado.
- [ ] **H-19** Suite de pruebas completa (unitaria + integración + E2E) y comando único.
- [ ] **H-20** README, `docs/ESTRUCTURA.md` actualizado y capturas finales.
- [ ] Regresión completa QA-01…QA-06 y PR-01…PR-06.
- [ ] Actualizar tablas 25, 26 y 27 de la tesis con el estado real final.

**Criterio de aceptación:** 6/6 QA y 6/6 PR con evidencia; documentación
reproducible; RNF verificables.

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
| Cifrado rompe PDFs históricos | Baja | Medio | Cifrar solo datos nuevos y migrar con script; probar con expedientes de ejemplo |
| Cambios de alcance (rechazos, correo, nómina) | Media | Medio | Registrarlos como “límites” (sección 1.8 de la tesis) y no implementarlos sin aprobación |

---

## 11. Estado global (semáforo)

| Área | Cumplimiento estimado | Estado |
|---|---|---|
| Autenticación / RBAC | 95 % | 🟢 |
| Registro de solicitudes | 90 % | 🟢 |
| Motor PDF | 90 % | 🟢 |
| Workflow / trazabilidad | 90 % | 🟢 |
| Firmas (3 roles) | 95 % | 🟢 |
| Dashboard / métricas | 45 % | 🔴 |
| Vigencia | 95 % | 🟢 |
| Seguridad RNF | 55 % | 🟡 |
| Pruebas / evidencias | 90 % | 🟢 |
| Documentación técnica | 90 % | 🟢 |
| **Total ponderado** | **~88 %** | 🟡 |

---

## 12. Próximo paso recomendado

Continuar con la **Fase 4 — Dashboard completo**:

1. Filtros por rango de fechas y por tipo de incidencia, además de nombre y
   estado (**H-08**).
2. KPIs completos: por estado, por tipo, pendientes de coordinador y de
   gerencia.
3. Descarga del PDF final desde el dashboard (**H-09**, HU-03).
4. Exportación CSV/Excel del resultado filtrado (**D-10**).
5. Alertas in-app de solicitudes pendientes (**D-11**).
6. Evaluar el rol Contabilidad de solo lectura (**D-02**).
7. Pruebas: cada filtro por separado y combinados; descarga con firmas; permisos.

Con las Fases 0–3 cerradas, la Fase 4 completa RF-04 y HU-03, y deja el módulo
de auditoría listo para la defensa.

---

*Documento generado como parte del análisis del proyecto. Se actualizará al
cerrar cada fase.*
