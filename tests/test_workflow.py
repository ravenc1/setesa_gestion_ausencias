# Pruebas unitarias del catálogo y las transiciones del workflow.

import pytest

from src.core.workflow import (
    ESTADOS_WORKFLOW,
    ESTADO_FINALIZADA,
    ESTADO_INGRESADA,
    ESTADO_PENDIENTE_APROBACION_GERENCIA,
    ESTADO_PENDIENTE_FIRMA_COORDINADOR,
    estado_valido,
    puede_transicionar,
    siguiente_estado,
)


def test_catalogo_tiene_los_cuatro_estados_de_la_tesis():
    assert ESTADOS_WORKFLOW == [
        ESTADO_INGRESADA,
        ESTADO_PENDIENTE_FIRMA_COORDINADOR,
        ESTADO_PENDIENTE_APROBACION_GERENCIA,
        ESTADO_FINALIZADA,
    ]


def test_estado_legado_no_es_valido():
    assert not estado_valido("En revisión por jefe inmediato GTC")
    assert not estado_valido("Aprobada")


@pytest.mark.parametrize(
    "origen,destino",
    [
        (ESTADO_INGRESADA, ESTADO_PENDIENTE_FIRMA_COORDINADOR),
        (ESTADO_PENDIENTE_FIRMA_COORDINADOR, ESTADO_PENDIENTE_APROBACION_GERENCIA),
        (ESTADO_PENDIENTE_APROBACION_GERENCIA, ESTADO_FINALIZADA),
    ],
)
def test_transiciones_permitidas(origen, destino):
    assert puede_transicionar(origen, destino)


@pytest.mark.parametrize(
    "origen,destino",
    [
        (ESTADO_INGRESADA, ESTADO_FINALIZADA),
        (ESTADO_INGRESADA, ESTADO_PENDIENTE_APROBACION_GERENCIA),
        (ESTADO_PENDIENTE_FIRMA_COORDINADOR, ESTADO_FINALIZADA),
        (ESTADO_PENDIENTE_APROBACION_GERENCIA, ESTADO_PENDIENTE_FIRMA_COORDINADOR),
        (ESTADO_FINALIZADA, ESTADO_INGRESADA),
        ("Estado Invalido", ESTADO_FINALIZADA),
    ],
)
def test_transiciones_rechazadas(origen, destino):
    assert not puede_transicionar(origen, destino)


def test_siguiente_estado():
    assert siguiente_estado(ESTADO_INGRESADA) == ESTADO_PENDIENTE_FIRMA_COORDINADOR
    assert (
        siguiente_estado(ESTADO_PENDIENTE_FIRMA_COORDINADOR)
        == ESTADO_PENDIENTE_APROBACION_GERENCIA
    )
    assert siguiente_estado(ESTADO_PENDIENTE_APROBACION_GERENCIA) == ESTADO_FINALIZADA
    assert siguiente_estado(ESTADO_FINALIZADA) is None
