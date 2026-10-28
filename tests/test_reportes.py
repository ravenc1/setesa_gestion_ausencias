# Pruebas unitarias de los filtros, KPIs y exportación del dashboard (RF-04).

import datetime

import pandas as pd
import pytest

from src.core.reportes import (
    calcular_kpis,
    exportar_csv,
    filtrar_solicitudes,
    nombre_archivo_csv,
    resumen_por_tipo,
)
from src.core.workflow import (
    ESTADO_FINALIZADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
)


@pytest.fixture
def solicitudes():
    return pd.DataFrame(
        [
            {
                "id_solicitud": 1,
                "nombre_completo": "Ana López",
                "tipo_ausencia": "VACACION",
                "fecha_inicio": datetime.date(2026, 10, 1),
                "fecha_fin": datetime.date(2026, 10, 5),
                "dias_solicitados": 5,
                "estado_workflow": ESTADO_FINALIZADA,
                "fecha_creacion": datetime.datetime(2026, 9, 25, 10, 0),
                "ruta_pdf": "/tmp/1.pdf",
            },
            {
                "id_solicitud": 2,
                "nombre_completo": "Bruno Díaz",
                "tipo_ausencia": "DUELO",
                "fecha_inicio": datetime.date(2026, 10, 10),
                "fecha_fin": datetime.date(2026, 10, 12),
                "dias_solicitados": 3,
                "estado_workflow": ESTADO_PENDIENTE_FIRMA_COORDINADOR,
                "fecha_creacion": datetime.datetime(2026, 10, 1, 9, 0),
                "ruta_pdf": None,
            },
            {
                "id_solicitud": 3,
                "nombre_completo": "Carla Ruiz",
                "tipo_ausencia": "VACACION",
                "fecha_inicio": datetime.date(2026, 11, 2),
                "fecha_fin": datetime.date(2026, 11, 6),
                "dias_solicitados": 5,
                "estado_workflow": ESTADO_PENDIENTE_APROBACION_GERENCIA,
                "fecha_creacion": datetime.datetime(2026, 10, 20, 11, 0),
                "ruta_pdf": None,
            },
            {
                "id_solicitud": 4,
                "nombre_completo": "Ana López",
                "tipo_ausencia": "PERMISO SIN GOCE DE SUELDO",
                "fecha_inicio": datetime.date(2026, 9, 15),
                "fecha_fin": datetime.date(2026, 9, 16),
                "dias_solicitados": 2,
                "estado_workflow": ESTADO_FINALIZADA,
                "fecha_creacion": datetime.datetime(2026, 9, 10, 8, 0),
                "ruta_pdf": "/tmp/4.pdf",
            },
        ]
    )


def _ids(df):
    return set(df["id_solicitud"].tolist())


def test_filtro_por_nombre_ignora_mayusculas_y_espacios(solicitudes):
    assert _ids(filtrar_solicitudes(solicitudes, nombre="  ana  ")) == {1, 4}


def test_filtro_por_estado(solicitudes):
    assert _ids(
        filtrar_solicitudes(solicitudes, estado=ESTADO_FINALIZADA)
    ) == {1, 4}
    assert len(filtrar_solicitudes(solicitudes, estado="Todos")) == 4


def test_filtro_por_tipo(solicitudes):
    assert _ids(filtrar_solicitudes(solicitudes, tipo="VACACION")) == {1, 3}


def test_filtro_por_rango_de_fechas_solapadas(solicitudes):
    filtrado = filtrar_solicitudes(
        solicitudes,
        fecha_desde=datetime.date(2026, 10, 4),
        fecha_hasta=datetime.date(2026, 10, 11),
    )
    assert _ids(filtrado) == {1, 2}


def test_filtro_solo_desde(solicitudes):
    filtrado = filtrar_solicitudes(
        solicitudes, fecha_desde=datetime.date(2026, 10, 20)
    )
    assert _ids(filtrado) == {3}


def test_filtro_solo_hasta(solicitudes):
    filtrado = filtrar_solicitudes(
        solicitudes, fecha_hasta=datetime.date(2026, 9, 30)
    )
    assert _ids(filtrado) == {4}


def test_filtros_combinados(solicitudes):
    filtrado = filtrar_solicitudes(
        solicitudes,
        nombre="Ana",
        estado=ESTADO_FINALIZADA,
        tipo="VACACION",
        fecha_desde=datetime.date(2026, 10, 1),
        fecha_hasta=datetime.date(2026, 10, 31),
    )
    assert _ids(filtrado) == {1}


def test_rango_invalido_lanza_error(solicitudes):
    with pytest.raises(ValueError):
        filtrar_solicitudes(
            solicitudes,
            fecha_desde=datetime.date(2026, 10, 31),
            fecha_hasta=datetime.date(2026, 10, 1),
        )


def test_dataframe_vacio():
    vacio = filtrar_solicitudes(pd.DataFrame())
    assert vacio.empty
    assert calcular_kpis(None) == {
        "total": 0,
        "ingresadas": 0,
        "pendientes_coordinador": 0,
        "pendientes_gerencia": 0,
        "finalizadas": 0,
    }
    assert list(resumen_por_tipo(None).columns) == ["tipo_ausencia", "cantidad"]


def test_calcular_kpis(solicitudes):
    assert calcular_kpis(solicitudes) == {
        "total": 4,
        "ingresadas": 0,
        "pendientes_coordinador": 1,
        "pendientes_gerencia": 1,
        "finalizadas": 2,
    }


def test_resumen_por_tipo(solicitudes):
    resumen = resumen_por_tipo(solicitudes)
    conteo = dict(zip(resumen["tipo_ausencia"], resumen["cantidad"]))
    assert conteo == {
        "VACACION": 2,
        "PERMISO SIN GOCE DE SUELDO": 1,
        "DUELO": 1,
    }


def test_exportar_csv_respeta_columnas_y_es_compatible_con_excel(solicitudes):
    contenido = exportar_csv(solicitudes)
    assert contenido.startswith(b"\xef\xbb\xbf")

    texto = contenido.decode("utf-8-sig")
    lineas = texto.strip().splitlines()
    assert lineas[0].startswith("id_solicitud,nombre_completo,tipo_ausencia")
    assert "Ana López" in texto
    assert "ruta_pdf" not in lineas[0]
    assert len(lineas) == 5


def test_nombre_archivo_csv():
    assert (
        nombre_archivo_csv(datetime.date(2026, 10, 27))
        == "setesa_solicitudes_2026-10-27.csv"
    )
