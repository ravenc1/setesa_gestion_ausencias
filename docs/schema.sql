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
    ultima_actividad     TIMESTAMP NOT NULL
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
    jefe_gtc         VARCHAR(150),
    puesto           VARCHAR(150),
    codigo_empleado  VARCHAR(50),
    dias_solicitados INTEGER,
    explicacion      TEXT,
    firma_empleado   TEXT,
    firma_jefe_gtc   TEXT,
    firma_gerencia   TEXT,
    CONSTRAINT solicitud_estado_workflow_check CHECK (
        estado_workflow IN (
            'Ingresada',
            'Pendiente de Firma Coordinador',
            'Pendiente de Aprobación Gerencia',
            'Finalizada'
        )
    )
);

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
-- Índices de consulta
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_solicitud_estado_fecha
    ON solicitud (estado_workflow, fecha_creacion DESC);

CREATE INDEX IF NOT EXISTS idx_historial_solicitud
    ON solicitud_historial (id_solicitud, fecha);

CREATE INDEX IF NOT EXISTS idx_vigencia_log_fecha
    ON vigencia_log (fecha_ejecucion DESC);

-- ---------------------------------------------------------------------------
-- Datos base: roles del sistema
-- ---------------------------------------------------------------------------
INSERT INTO rol (nombre_rol, descripcion_rol) VALUES
    ('Consultor', 'Registra solicitudes de ausencia y consulta su historial.'),
    ('Administrador', 'Gerencia: autoriza solicitudes, consulta métricas y ejecuta la vigencia.'),
    ('Coordinador GTC', 'Jefe inmediato del banco: otorga el visto bueno de las solicitudes.')
ON CONFLICT (nombre_rol) DO NOTHING;

COMMIT;
