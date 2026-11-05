# Guion de prueba manual (5 a 10 minutos)

La prueba automática `tests/test_flujo_completo.py` recorre todo el sistema con
los cinco roles, pero hay tres cosas que solo se comprueban en un navegador
real: **dibujar la firma**, **adjuntar y descargar archivos** y **ver las
pantallas**. Este guion cubre eso.

Abra la aplicación (`streamlit run app.py`) con dos ventanas del navegador, una
normal y otra de incógnito, para tener dos roles a la vez. Si no tiene cuentas
de prueba, IT las crea en **Crear usuario**.

## 1. Consultor (ventana 1)

1. Inicie sesión como **Consultor** → «🪪 Mis datos» → complete puesto, código y
   teléfono → **Confirmar**. Debe mostrar la nueva fecha límite.
2. «Principal» → elija un **Jefe Inmediato GTC**, un motivo **VACACION** y
   fechas de lunes a miércoles. Revise que los **días hábiles** sean 3.
3. Escriba una explicación → **Firmar Electrónicamente** → **dibuje su firma**
   en el recuadro → **Enviar**.
4. **Descargue el comprobante** y ábralo: debe verse como la hoja oficial de
   SETESA (logo, casillas, fechas dd/mm/aaaa, su firma sobre «EMPLEADO QUE SE
   LE APLICA»).
5. Registre otra con motivo **SUSPENSIÓN IGSS**: el sistema debe **exigir** una
   constancia; adjunte un PDF o una foto.

## 2. Coordinador GTC (ventana 2)

6. Inicie sesión como el **Coordinador GTC** elegido: la solicitud debe
   aparecer en la bandeja (y no en la de otro coordinador).
7. Elija **Otorgar visto bueno**, dibuje su firma y envíe.
8. En otra solicitud elija **Denegar**: debe exigir un **motivo** y la firma.

## 3. Gerencia

9. Inicie sesión como **Gerencia** → Dashboard → seleccione el expediente →
   **Aprobar** (o **Denegar**), dibuje la firma y finalice.
10. Descargue el **PDF final** y compruebe: tres firmas, «RESOLUCION: APROBADA»
    y el mensaje «Integridad verificada (SHA-256)».
11. Pestaña **Motivos de ausencia**: agregue uno nuevo y verifique que aparece
    en el formulario del consultor.

## 4. Contabilidad y RR.HH. y consultor

12. Inicie sesión como **Contabilidad y RR.HH.**: en «🔔 Avisos» debe verse la
    resolución del expediente, con el enlace para escribir al consultor.
13. Abra las **evidencias** del expediente IGSS y descárguelas.
14. Como **consultor**, revise «🔔 Avisos» y su historial: debe ver la
    resolución (y el motivo si fue denegada).

## 5. Seguridad

15. En una ventana de incógnito, escriba 5 veces una contraseña incorrecta: al
    quinto intento el acceso se bloquea 15 minutos. IT puede desbloquearlo en
    su pestaña **Auditoría**.

Anote cualquier cosa que se vea rara o se sienta lenta: es justo lo que la
prueba automática no puede juzgar.
