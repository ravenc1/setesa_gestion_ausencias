# Correo de recordatorio (Fase 15)

Los Consultores y Contabilidad y RR.HH. deben actualizar «Mis datos» cada
6 meses. Además del aviso dentro del sistema, una tarea diaria les escribe
desde la cuenta de SETESA **30, 15, 7 y 1 día(s)** antes del vencimiento.

- Tarea: `.github/workflows/recordatorios.yml` (08:00 de Guatemala).
- Script: `scripts/enviar_recordatorios.py` (`--simular` para probar).
- Registro: tabla `aviso_actualizacion`; IT lo ve en «Por vencer».

## 1. Contraseña de aplicación de la cuenta de SETESA

La tarea nunca usa la contraseña normal de la cuenta.

**Gmail o Google Workspace**

1. Active la verificación en dos pasos de la cuenta.
2. Entre a <https://myaccount.google.com/apppasswords>, cree una contraseña
   de aplicación llamada «SETESA Ausencias» y cópiela (16 caracteres).
3. Datos: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`.

**Outlook o Microsoft 365**

1. El administrador de Microsoft 365 debe habilitar *SMTP AUTH* para el buzón.
2. Con verificación en dos pasos, cree una contraseña de aplicación en
   <https://account.microsoft.com/security>.
3. Datos: `SMTP_HOST=smtp.office365.com`, `SMTP_PORT=587`.

## 2. Conexión a Supabase para GitHub Actions

GitHub Actions no tiene IPv6 y la conexión directa de Supabase
(`db.<proyecto>.supabase.co`) solo funciona por IPv6. Use la del pooler:

1. Supabase → su proyecto → botón **Connect**.
2. Copie la cadena **Session pooler** (host `aws-...pooler.supabase.com`,
   usuario `postgres.<proyecto>`) y reemplace `[YOUR-PASSWORD]`.

## 3. Secretos en GitHub

En el repositorio: **Settings → Secrets and variables → Actions → New
repository secret**. Los secretos se guardan cifrados y no son visibles en el
repositorio público.

| Secreto | Valor |
|---|---|
| `DATABASE_URL` | Cadena del *Session pooler* |
| `SMTP_HOST` | `smtp.gmail.com` o `smtp.office365.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USUARIO` | Cuenta de SETESA que envía |
| `SMTP_PASSWORD` | Contraseña de aplicación |
| `SMTP_REMITENTE` | Opcional, si difiere de `SMTP_USUARIO` |

En la pestaña **Variables**, `APP_URL` (opcional) con el enlace de la app.

También puede cargarlos desde la terminal con `gh secret set NOMBRE`
(pide el valor sin mostrarlo).

## 4. Prueba

1. GitHub → **Actions → Recordatorios de actualización de datos → Run
   flujo** con «simular» marcado: lista a quién escribiría, sin enviar.
2. Repita sin «simular» para enviar de verdad.

Si faltan los secretos, la tarea termina sin hacer nada. GitHub desactiva las
tareas programadas de un repositorio público tras 60 días sin actividad; si
ocurre, reactívela en la pestaña **Actions**.
