-- ============================================================================
-- Esquema de la base de datos — Proyecto SETESA
-- Motor: PostgreSQL (Supabase)
--
-- Este archivo refleja el esquema real del sistema y permite recrearlo desde
-- cero. Para bases ya existentes, usar scripts/migracion_fase1.py.
--
-- Uso:
--   psql "$DATABASE_URL" -f docs/schema.sql
--
-- NOTA: no se incluyen contraseñas. Los usuarios se crean con
-- scripts/hash_passwords.py o con un INSERT que use security.hash_password().
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Catálogo de roles (RBAC)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rol (
    id_rol          SERIAL PRIMARY KEY,
    nombre_rol      VARCHAR(50) NOT NULL UNIQUE,
    descripcion_rol TEXT
);

-- ---------------------------------------------------------------------------
-- Usuarios del sistema
--   estado_vigencia: baja lógica (TRUE = activo, FALSE = dado de baja)
--   ultima_actividad: la usa el algoritmo semestral de vigencia (RF-05)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuario (
    id_usuario           SERIAL PRIMARY KEY,
    id_rol               INTEGER NOT NULL REFERENCES rol(id_rol),
    nombre_completo      VARCHAR(150) NOT NULL,
    correo_institucional VARCHAR(150) NOT NULL UNIQUE,
    password_hash        VARCHAR(255) NOT NULL,
    estado_vigencia      BOOLEAN DEFAULT TRUE,
    ultima_actividad     TIMESTAMP NOT NULL,
    dias_vacaciones_asignados INTEGER NOT NULL DEFAULT 15,
    -- Fase 14: "Mis datos" (actualización cada 6 meses; teléfono cifrado).
    puesto               VARCHAR(150),
    codigo_empleado      VARCHAR(50),
    telefono             TEXT,
    fecha_actualizacion_datos TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT usuario_dias_vacaciones_check CHECK (
        dias_vacaciones_asignados >= 0
    )
);

-- ---------------------------------------------------------------------------
-- Solicitudes de ausencia (Acción de Personal)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS solicitud (
    id_solicitud     SERIAL PRIMARY KEY,
    id_usuario       INTEGER NOT NULL REFERENCES usuario(id_usuario),
    tipo_ausencia    VARCHAR(50) NOT NULL,
    fecha_inicio     DATE NOT NULL,
    fecha_fin        DATE NOT NULL,
    estado_workflow  VARCHAR(50) NOT NULL DEFAULT 'Ingresada',
    ruta_pdf         VARCHAR(255),
    fecha_creacion   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    jefe_gtc         VARCHAR(150),  -- nombre visible del jefe (PDF)
    -- Fase 11: Coordinador GTC asignado; filtra su bandeja (Tabla 9).
    id_coordinador   INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    puesto           VARCHAR(150),
    codigo_empleado  VARCHAR(50),
    dias_solicitados INTEGER,
    explicacion      TEXT,
    firma_empleado   TEXT,
    firma_jefe_gtc   TEXT,
    firma_gerencia   TEXT,
    pdf_hash         VARCHAR(64),
    pdf_hash_fecha   TIMESTAMP,
    CONSTRAINT solicitud_estado_workflow_check CHECK (
        estado_workflow IN (
            'Ingresada',
            'Pendiente de Firma Coordinador',
            'Pendiente de Aprobación Gerencia',
            'Finalizada'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_solicitud_coordinador_estado
    ON solicitud (id_coordinador, estado_workflow);

-- ---------------------------------------------------------------------------
-- Historial de estados (trazabilidad / auditoría)
--   ON DELETE CASCADE: al eliminar una solicitud (solo en pruebas) se limpia
--   su historial. En producción las solicitudes no se eliminan (baja lógica).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS solicitud_historial (
    id_historial    SERIAL PRIMARY KEY,
    id_solicitud    INTEGER NOT NULL
                        REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    estado_anterior VARCHAR(50),
    estado_nuevo    VARCHAR(50) NOT NULL,
    id_usuario      INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    fecha           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observacion     TEXT,
    CONSTRAINT solicitud_historial_estado_nuevo_check CHECK (
        estado_nuevo IN (
            'Ingresada',
            'Pendiente de Firma Coordinador',
            'Pendiente de Aprobación Gerencia',
            'Finalizada'
        )
    )
);

-- ---------------------------------------------------------------------------
-- Recordatorios del consultor al Coordinador GTC (R-11)
--   El canal principal es la bandeja del Coordinador; el correo registrado se
--   guarda como copia histórica para el enlace mailto.
--   El mensaje se almacena cifrado con Fernet (RNF-01).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recordatorio (
    id_recordatorio SERIAL PRIMARY KEY,
    id_solicitud    INTEGER NOT NULL
                        REFERENCES solicitud(id_solicitud) ON DELETE CASCADE,
    id_emisor       INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    id_destinatario INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    correo_destino  VARCHAR(150),
    mensaje         TEXT,
    fecha           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atendido        BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_atencion  TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Auditoría de la gestión manual de usuarios (Fase 9)
--   Registra altas, ediciones, bajas, reactivaciones y resets de contraseña.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuario_log (
    id_log      SERIAL PRIMARY KEY,
    fecha       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id_ejecutor INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    id_afectado INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    accion      VARCHAR(20) NOT NULL,
    detalle     TEXT,
    CONSTRAINT usuario_log_accion_check CHECK (
        accion IN ('CREACION', 'EDICION', 'BAJA', 'REACTIVACION', 'RESET_PASSWORD',
                   'ACTUALIZACION_DATOS')
    )
);

-- ---------------------------------------------------------------------------
-- Auditoría del algoritmo de vigencia (RF-05 / CU-06)
--   Guarda cada depuración y cada reactivación, con su ejecutor.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vigencia_log (
    id_log             SERIAL PRIMARY KEY,
    fecha_ejecucion    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id_ejecutor        INTEGER REFERENCES usuario(id_usuario) ON DELETE SET NULL,
    accion             VARCHAR(20) NOT NULL,
    usuarios_afectados INTEGER NOT NULL DEFAULT 0,
    detalle            TEXT,
    CONSTRAINT vigencia_log_accion_check CHECK (
        accion IN ('DEPURACION', 'AUTOMATICA', 'REACTIVACION')
    )
);

-- ---------------------------------------------------------------------------
-- Catálogo de feriados nacionales (RF-01 / D-04)
--   Se excluyen del cálculo de días hábiles de las solicitudes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feriado (
    id_feriado SERIAL PRIMARY KEY,
    fecha      DATE NOT NULL UNIQUE,
    nombre     VARCHAR(120) NOT NULL
);

-- ---------------------------------------------------------------------------
-- Índices de consulta
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_solicitud_estado_fecha
    ON solicitud (estado_workflow, fecha_creacion DESC);

CREATE INDEX IF NOT EXISTS idx_historial_solicitud
    ON solicitud_historial (id_solicitud, fecha);

CREATE INDEX IF NOT EXISTS idx_recordatorio_destino
    ON recordatorio (id_destinatario, atendido, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_recordatorio_solicitud
    ON recordatorio (id_solicitud, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_usuario_log_fecha
    ON usuario_log (fecha DESC);

CREATE INDEX IF NOT EXISTS idx_usuario_log_afectado
    ON usuario_log (id_afectado, fecha DESC);

CREATE INDEX IF NOT EXISTS idx_vigencia_log_fecha
    ON vigencia_log (fecha_ejecucion DESC);

CREATE INDEX IF NOT EXISTS idx_feriado_fecha
    ON feriado (fecha);

-- ---------------------------------------------------------------------------
-- Datos base: roles del sistema
-- ---------------------------------------------------------------------------
INSERT INTO rol (nombre_rol, descripcion_rol) VALUES
    ('Consultor', 'Registra solicitudes de ausencia y consulta su historial.'),
    ('Administrador', 'Gerencia: autoriza solicitudes, consulta métricas y ejecuta la vigencia.'),
    ('Coordinador GTC', 'Jefe inmediato del banco: otorga el visto bueno de las solicitudes.'),
    ('Contabilidad', 'Solo lectura: consulta el repositorio de expedientes y descarga el PDF final (HU-03).'),
    ('IT', 'Gestión de usuarios: altas, ediciones, bajas, reactivaciones y reseteo de contraseñas.')
ON CONFLICT (nombre_rol) DO NOTHING;

-- Feriados nacionales de Guatemala (días completos). Semana Santa: jueves,
-- viernes y sábado santo. Ampliar por año desde el panel de Gerencia.
INSERT INTO feriado (fecha, nombre) VALUES
    ('2025-01-01', 'Año Nuevo'),
    ('2025-04-17', 'Jueves Santo'),
    ('2025-04-18', 'Viernes Santo'),
    ('2025-04-19', 'Sábado Santo'),
    ('2025-05-01', 'Día del Trabajo'),
    ('2025-06-30', 'Día del Ejército'),
    ('2025-09-15', 'Independencia'),
    ('2025-10-20', 'Revolución'),
    ('2025-11-01', 'Todos los Santos'),
    ('2025-12-25', 'Navidad'),
    ('2026-01-01', 'Año Nuevo'),
    ('2026-04-02', 'Jueves Santo'),
    ('2026-04-03', 'Viernes Santo'),
    ('2026-04-04', 'Sábado Santo'),
    ('2026-05-01', 'Día del Trabajo'),
    ('2026-06-30', 'Día del Ejército'),
    ('2026-09-15', 'Independencia'),
    ('2026-10-20', 'Revolución'),
    ('2026-11-01', 'Todos los Santos'),
    ('2026-12-25', 'Navidad'),
    ('2027-01-01', 'Año Nuevo'),
    ('2027-03-25', 'Jueves Santo'),
    ('2027-03-26', 'Viernes Santo'),
    ('2027-03-27', 'Sábado Santo'),
    ('2027-05-01', 'Día del Trabajo'),
    ('2027-06-30', 'Día del Ejército'),
    ('2027-09-15', 'Independencia'),
    ('2027-10-20', 'Revolución'),
    ('2027-11-01', 'Todos los Santos'),
    ('2027-12-25', 'Navidad')
ON CONFLICT (fecha) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- Fase 13: las reglas de integridad y vigencia en el motor de datos están en
-- docs/triggers.sql (se aplican con scripts/migracion_fase13.py).
-- ---------------------------------------------------------------------------
