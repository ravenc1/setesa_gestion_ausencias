-- =============================================================================
-- SETESA Workflow - Triggers de PostgreSQL (Fase 13)
--
-- Tesis, sección 3.6: los triggers validan automáticamente la vigencia de los
-- usuarios, "independientemente de si el administrador olvida realizar la
-- revisión manual". Resultados QA: "los Triggers en PostgreSQL evitan
-- registros huérfanos, garantizando la integridad de los datos".
--
-- Estas reglas repiten en el motor de datos las que ya aplica la aplicación,
-- de modo que se cumplen aunque alguien escriba directamente en la base.
--
-- Se aplica con: python scripts/migracion_fase13.py   (idempotente)
--
-- Borrados: los expedientes y su historial no se eliminan (baja lógica). Para
-- limpiar datos de prueba, dentro de la transacción ejecute antes:
--     SET LOCAL setesa.permitir_borrado = 'on';
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Funciones de apoyo
-- -----------------------------------------------------------------------------

-- ¿La transacción actual habilitó explícitamente el borrado de pruebas?
CREATE OR REPLACE FUNCTION setesa_borrado_permitido()
RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(current_setting('setesa.permitir_borrado', TRUE), '') = 'on'
$$;

-- Rol del usuario, o NULL si no existe.
CREATE OR REPLACE FUNCTION setesa_rol_usuario(p_id_usuario INTEGER)
RETURNS VARCHAR
LANGUAGE sql STABLE AS $$
    SELECT r.nombre_rol
      FROM usuario u
      JOIN rol r ON u.id_rol = r.id_rol
     WHERE u.id_usuario = p_id_usuario
$$;

-- RF-05: vigente = activo y con actividad en los últimos 6 meses. Los roles
-- protegidos (Administrador, IT) nunca vencen por inactividad.
CREATE OR REPLACE FUNCTION setesa_usuario_vigente(p_id_usuario INTEGER)
RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
    SELECT COALESCE((
        SELECT u.estado_vigencia
               AND (r.nombre_rol IN ('Administrador', 'IT')
                    OR u.ultima_actividad >= CURRENT_DATE - INTERVAL '6 months')
          FROM usuario u
          JOIN rol r ON u.id_rol = r.id_rol
         WHERE u.id_usuario = p_id_usuario
    ), FALSE)
$$;


-- -----------------------------------------------------------------------------
-- 1. Vigencia automática (sección 3.6)
--    Si un usuario activo lleva más de 6 meses sin actividad y el sistema
--    intenta registrarle actividad nueva (login, firma, registro), el trigger
--    aplica la baja lógica en lugar de "revivirlo" y lo deja auditado.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION setesa_trg_usuario_vigencia()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado_vigencia
       AND NEW.estado_vigencia
       AND NEW.ultima_actividad > OLD.ultima_actividad
       AND OLD.ultima_actividad < CURRENT_DATE - INTERVAL '6 months'
       AND setesa_rol_usuario(OLD.id_usuario) NOT IN ('Administrador', 'IT')
    THEN
        NEW.estado_vigencia := FALSE;
        NEW.ultima_actividad := OLD.ultima_actividad;
        INSERT INTO vigencia_log (id_ejecutor, accion, usuarios_afectados, detalle)
        VALUES (NULL, 'AUTOMATICA', 1,
                'trigger: id=' || OLD.id_usuario || ' (más de 6 meses sin actividad)');
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_usuario_vigencia ON usuario;
CREATE TRIGGER trg_usuario_vigencia
    BEFORE UPDATE OF ultima_actividad ON usuario
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_usuario_vigencia();


-- Depuración completa, la misma que hace scripts/vigencia_semestral.py.
-- La programa pg_cron a diario (ver migración); solo audita si hubo bajas.
CREATE OR REPLACE FUNCTION setesa_depurar_vigencia()
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    v_ids INTEGER[];
BEGIN
    WITH bajas AS (
        UPDATE usuario u
           SET estado_vigencia = FALSE
          FROM rol r
         WHERE u.id_rol = r.id_rol
           AND u.estado_vigencia = TRUE
           AND u.ultima_actividad < CURRENT_DATE - INTERVAL '6 months'
           AND r.nombre_rol NOT IN ('Administrador', 'IT')
        RETURNING u.id_usuario
    )
    SELECT array_agg(id_usuario ORDER BY id_usuario) INTO v_ids FROM bajas;

    IF v_ids IS NOT NULL THEN
        INSERT INTO vigencia_log (id_ejecutor, accion, usuarios_afectados, detalle)
        VALUES (NULL, 'AUTOMATICA', cardinality(v_ids),
                'pg_cron: ids=' || array_to_string(v_ids, ','));
        RETURN cardinality(v_ids);
    END IF;
    RETURN 0;
END;
$$;


-- -----------------------------------------------------------------------------
-- 2. Registro de solicitudes
--    Nace en 'Ingresada', sin firmas de banco ni gerencia, de un usuario
--    vigente y dirigida a un Coordinador GTC vigente.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION setesa_trg_solicitud_insert()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.estado_workflow IS DISTINCT FROM 'Ingresada' THEN
        RAISE EXCEPTION 'SETESA: toda solicitud debe registrarse en estado Ingresada.';
    END IF;
    IF NEW.firma_jefe_gtc IS NOT NULL OR NEW.firma_gerencia IS NOT NULL THEN
        RAISE EXCEPTION 'SETESA: una solicitud nueva no puede traer firmas del banco ni de Gerencia.';
    END IF;
    IF NOT setesa_usuario_vigente(NEW.id_usuario) THEN
        RAISE EXCEPTION 'SETESA: el usuario % no está vigente y no puede registrar solicitudes.',
            NEW.id_usuario;
    END IF;
    IF NEW.id_coordinador IS NULL
       OR setesa_rol_usuario(NEW.id_coordinador) IS DISTINCT FROM 'Coordinador GTC'
       OR NOT setesa_usuario_vigente(NEW.id_coordinador)
    THEN
        RAISE EXCEPTION 'SETESA: la solicitud debe dirigirse a un Coordinador GTC vigente.';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitud_insert ON solicitud;
CREATE TRIGGER trg_solicitud_insert
    BEFORE INSERT ON solicitud
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_solicitud_insert();


-- -----------------------------------------------------------------------------
-- 3. Cambios sobre una solicitud
--    a) Finalizada es inalterable (solo se admite el sello del PDF).
--    b) Solo las transiciones del workflow, cada una con su firma.
--    c) La reasignación solo va a un Coordinador GTC vigente.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION setesa_trg_solicitud_update()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_sello CONSTANT TEXT[] := ARRAY['ruta_pdf', 'pdf_hash', 'pdf_hash_fecha'];
BEGIN
    IF setesa_borrado_permitido() THEN
        RETURN NEW;  -- limpieza de pruebas (p. ej. ON DELETE SET NULL)
    END IF;

    -- a) Expediente cerrado.
    IF OLD.estado_workflow = 'Finalizada' THEN
        IF (to_jsonb(NEW) - v_sello) IS DISTINCT FROM (to_jsonb(OLD) - v_sello) THEN
            RAISE EXCEPTION 'SETESA: el expediente % está Finalizado y no puede modificarse.',
                OLD.id_solicitud;
        END IF;
        RETURN NEW;
    END IF;

    -- b) Transiciones permitidas.
    IF NEW.estado_workflow IS DISTINCT FROM OLD.estado_workflow THEN
        IF NOT (
               (OLD.estado_workflow = 'Ingresada'
                AND NEW.estado_workflow = 'Pendiente de Firma Coordinador')
            OR (OLD.estado_workflow = 'Pendiente de Firma Coordinador'
                AND NEW.estado_workflow = 'Pendiente de Aprobación Gerencia')
            OR (OLD.estado_workflow = 'Pendiente de Aprobación Gerencia'
                AND NEW.estado_workflow = 'Finalizada')
        ) THEN
            RAISE EXCEPTION 'SETESA: transición no permitida: % -> %.',
                OLD.estado_workflow, NEW.estado_workflow;
        END IF;

        IF NEW.estado_workflow = 'Pendiente de Aprobación Gerencia'
           AND NEW.firma_jefe_gtc IS NULL THEN
            RAISE EXCEPTION 'SETESA: el visto bueno del banco requiere la firma del Coordinador GTC.';
        END IF;
        IF NEW.estado_workflow = 'Finalizada' AND NEW.firma_gerencia IS NULL THEN
            RAISE EXCEPTION 'SETESA: la aprobación final requiere la firma de Gerencia.';
        END IF;
    END IF;

    -- Las firmas ya estampadas no se reemplazan ni se borran.
    IF OLD.firma_empleado IS NOT NULL
       AND NEW.firma_empleado IS DISTINCT FROM OLD.firma_empleado THEN
        RAISE EXCEPTION 'SETESA: la firma del consultor no puede modificarse.';
    END IF;
    IF OLD.firma_jefe_gtc IS NOT NULL
       AND NEW.firma_jefe_gtc IS DISTINCT FROM OLD.firma_jefe_gtc THEN
        RAISE EXCEPTION 'SETESA: la firma del Coordinador GTC no puede modificarse.';
    END IF;

    -- c) Reasignación de coordinador (Fase 12).
    IF NEW.id_coordinador IS DISTINCT FROM OLD.id_coordinador THEN
        IF OLD.estado_workflow <> 'Pendiente de Firma Coordinador' THEN
            RAISE EXCEPTION 'SETESA: solo se reasignan expedientes pendientes del visto bueno del banco.';
        END IF;
        IF NEW.id_coordinador IS NULL
           OR setesa_rol_usuario(NEW.id_coordinador) IS DISTINCT FROM 'Coordinador GTC'
           OR NOT setesa_usuario_vigente(NEW.id_coordinador)
        THEN
            RAISE EXCEPTION 'SETESA: el expediente solo puede asignarse a un Coordinador GTC vigente.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitud_update ON solicitud;
CREATE TRIGGER trg_solicitud_update
    BEFORE UPDATE ON solicitud
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_solicitud_update();


-- Los expedientes no se eliminan (baja lógica).
CREATE OR REPLACE FUNCTION setesa_trg_solicitud_delete()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT setesa_borrado_permitido() THEN
        RAISE EXCEPTION 'SETESA: los expedientes no se eliminan (expediente %).',
            OLD.id_solicitud;
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitud_delete ON solicitud;
CREATE TRIGGER trg_solicitud_delete
    BEFORE DELETE ON solicitud
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_solicitud_delete();


-- Sin registros huérfanos: al confirmar la transacción, toda solicitud nueva
-- debe tener al menos un movimiento en su historial.
CREATE OR REPLACE FUNCTION setesa_trg_solicitud_con_historial()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM solicitud WHERE id_solicitud = NEW.id_solicitud)
       AND NOT EXISTS (
           SELECT 1 FROM solicitud_historial WHERE id_solicitud = NEW.id_solicitud
       )
    THEN
        RAISE EXCEPTION 'SETESA: la solicitud % no tiene historial; se revierte el registro.',
            NEW.id_solicitud;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitud_con_historial ON solicitud;
CREATE CONSTRAINT TRIGGER trg_solicitud_con_historial
    AFTER INSERT ON solicitud
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_solicitud_con_historial();


-- -----------------------------------------------------------------------------
-- 4. Historial (trazabilidad)
--    Solo se agrega; cada movimiento refleja el estado real del expediente y
--    lo registra el actor que corresponde a esa etapa, siempre vigente.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION setesa_trg_historial_insert()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_estado      VARCHAR;
    v_dueno       INTEGER;
    v_coordinador INTEGER;
    v_rol         VARCHAR;
BEGIN
    SELECT estado_workflow, id_usuario, id_coordinador
      INTO v_estado, v_dueno, v_coordinador
      FROM solicitud
     WHERE id_solicitud = NEW.id_solicitud;

    IF NEW.estado_nuevo IS DISTINCT FROM v_estado THEN
        RAISE EXCEPTION 'SETESA: el historial (%) no coincide con el estado del expediente (%).',
            NEW.estado_nuevo, v_estado;
    END IF;

    IF NEW.id_usuario IS NULL OR NOT setesa_usuario_vigente(NEW.id_usuario) THEN
        RAISE EXCEPTION 'SETESA: el usuario % no está vigente y no puede operar expedientes.',
            NEW.id_usuario;
    END IF;

    v_rol := setesa_rol_usuario(NEW.id_usuario);

    IF NEW.estado_nuevo IN ('Ingresada', 'Pendiente de Firma Coordinador')
       AND NEW.estado_anterior IS DISTINCT FROM 'Pendiente de Firma Coordinador' THEN
        IF NEW.id_usuario <> v_dueno THEN
            RAISE EXCEPTION 'SETESA: solo el consultor dueño registra su solicitud.';
        END IF;
    ELSIF NEW.estado_anterior = 'Pendiente de Firma Coordinador'
          AND NEW.estado_nuevo = 'Pendiente de Firma Coordinador' THEN
        IF v_rol <> 'Administrador' THEN
            RAISE EXCEPTION 'SETESA: solo Gerencia reasigna expedientes.';
        END IF;
    ELSIF NEW.estado_nuevo = 'Pendiente de Aprobación Gerencia' THEN
        IF NEW.id_usuario IS DISTINCT FROM v_coordinador THEN
            RAISE EXCEPTION 'SETESA: solo el Coordinador GTC asignado da el visto bueno.';
        END IF;
    ELSIF NEW.estado_nuevo = 'Finalizada' THEN
        IF v_rol <> 'Administrador' THEN
            RAISE EXCEPTION 'SETESA: solo Gerencia aprueba y finaliza expedientes.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_historial_insert ON solicitud_historial;
CREATE TRIGGER trg_historial_insert
    BEFORE INSERT ON solicitud_historial
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_historial_insert();


CREATE OR REPLACE FUNCTION setesa_trg_historial_inmutable()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT setesa_borrado_permitido() THEN
        RAISE EXCEPTION 'SETESA: el historial de expedientes no se modifica ni se elimina.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_historial_inmutable ON solicitud_historial;
CREATE TRIGGER trg_historial_inmutable
    BEFORE UPDATE OR DELETE ON solicitud_historial
    FOR EACH ROW EXECUTE FUNCTION setesa_trg_historial_inmutable();
