# Versionamiento del proyecto SETESA Workflow

Repositorio: https://github.com/ravenc1/setesa_gestion_ausencias (público).

## Ramas

- `main` es la rama estable: siempre compila y pasa la suite de pruebas.
- Cada fase se desarrolla en su propia rama: `fase-<número>-<descripción>`,
  por ejemplo `fase-11-coordinador-equipo`.
- No se trabaja directamente sobre `main`.

## Commits

Formato convencional, en español y en imperativo:

| Prefijo | Uso |
|---|---|
| `feat:` | Funcionalidad nueva |
| `fix:` | Corrección de un defecto |
| `docs:` | Solo documentación |
| `test:` | Solo pruebas |
| `refactor:` | Cambio interno sin alterar el comportamiento |
| `chore:` | Mantenimiento (dependencias, configuración, archivos ignorados) |

Cada commit debe ser pequeño y dejar el proyecto en un estado que compile.

## Flujo de una fase

1. Crear la rama de la fase desde `main` actualizado.
2. Hacer commits pequeños mientras se avanza.
3. Subir la rama y abrir un pull request hacia `main`.
4. Esperar el CI en verde (`.github/workflows/ci.yml`).
5. Integrar el pull request y borrar la rama.
6. Crear la etiqueta de versión de la fase sobre `main`.

## Versiones (etiquetas)

Se usa versionado semántico `vMAYOR.MENOR.PARCHE`:

- `v0.9.0`: estado al cierre de la Fase 9 (rol IT y gestión de usuarios).
- Cada fase nueva sube el número menor: Fase 10 → `v0.10.0`, Fase 11 →
  `v0.11.0`, etc.
- Las correcciones sobre una fase ya etiquetada suben el parche
  (`v0.11.1`).
- `v1.0.0` se reserva para la versión que se presenta en la defensa y se
  despliega en producción (Render + Supabase).

## Qué no se versiona

- Secretos: `.env`, `.streamlit/secrets.toml` y la `FERNET_KEY`.
- Archivos generados: `storage/pdf/*`, `storage/firmas/*`, respaldos y logs.
- La plantilla Excel oficial de SETESA
  (`proyecto_doc/Excel_PlantillaOficial_SETESA/`), por ser un documento
  interno y el repositorio público. Solo se versiona el logo en
  `assets/logo_setesa.png`, necesario para generar el PDF oficial.
