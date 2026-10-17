# -*- coding: utf-8 -*-
"""
Genera las "capturas de código" (imágenes PNG con resaltado de sintaxis) por
módulo, usadas como evidencia técnica en la sección 10 (Evidencias y
documentación técnica) del documento Plantillas_UMG_Completadas.docx.

Tecnología: Pygments (resaltado de sintaxis) + Pillow (render) + fuente Consolas.

Salida:
  proyecto_doc/plantillas_llenadas/capturas/codigo_<modulo>.png
  proyecto_doc/plantillas_llenadas/capturas/manifest.json
"""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.styles import get_style_by_name

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE = Path(r"C:\Users\conde\OneDrive\Documentos\UMG 2026\Segundo Semestre\PG2\proyecto_setesa")
OUT_DIR = BASE / "proyecto_doc" / "plantillas_llenadas" / "capturas"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FONTS_DIR = Path(r"C:\Windows\Fonts")

# Se renderiza a 2x para que, al insertarse en Word, se reduzca (se vea nítido).
SCALE = 2
FS = 14 * SCALE
LINE_H = int(FS * 1.55)
PAD = 16 * SCALE
TITLE_H = int(FS * 2.3)
GUTTER = 5 * SCALE

STYLE = get_style_by_name("default")
COLOR_TEXTO = "#1F2328"
COLOR_BG = "#FBFBFB"
COLOR_TITLE_BG = "#1F3B57"
COLOR_TITLE_FG = "#FFFFFF"
COLOR_GUTTER = "#9AA7B4"
COLOR_BORDE = "#C9D1D9"

# ---------------------------------------------------------------------------
# Fragmentos de código por módulo (extractos reales del repositorio)
# ---------------------------------------------------------------------------
CAPTURAS = [
    {
        "imagen": "codigo_01_rbac_auth.png",
        "archivo": "src/core/auth.py",
        "modulo": "Control de Acceso Basado en Roles (RBAC)",
        "codigo": '''def login_user(email, password):
    cursor = conn.cursor()
    query = """
        SELECT u.id_usuario, u.nombre_completo, u.estado_vigencia,
               r.nombre_rol, u.password_hash
        FROM usuario u
        JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.correo_institucional = %s
    """
    cursor.execute(query, (email,))
    id_usuario, nombre, estado_vigencia, rol, phash = cursor.fetchone()
    valido, nuevo_hash = verify_or_upgrade(password, phash)

    if not estado_vigencia:
        st.error("Acceso denegado: Usuario inactivo (Baja Logica).")
    else:
        st.session_state['rol'] = rol
        st.rerun()''',
    },
    {
        "imagen": "codigo_02_registro_solicitud.png",
        "archivo": "src/features/registro.py",
        "modulo": "Registro de solicitudes de ausencia",
        "codigo": '''def registrar_solicitud_firmada(id_us, tipo, f_ini, f_fin, jefe, puesto,
                                codigo, dias, exp, firma_b64):
    """Inserta la solicitud en PostgreSQL con su firma digitalizada."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        INSERT INTO solicitud (id_usuario, tipo_ausencia, fecha_inicio, fecha_fin,
            estado_workflow, jefe_gtc, puesto, dias_solicitados, firma_empleado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (id_us, tipo, f_ini, f_fin, ESTADO_INGRESADA, jefe,
                           puesto, dias, firma_b64))
    conn.commit()
    return True''',
    },
    {
        "imagen": "codigo_03_motor_pdf.png",
        "archivo": "src/services/motor_pdf.py",
        "modulo": "Generación automática del PDF (FPDF)",
        "codigo": '''def generar_pdf_accion_personal(nombre_empleado, jefe_gtc, puesto,
                                tipo_ausencia, dias, ...):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 8, "SETESA", ln=True, align="C")
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 6, "ACCION DE PERSONAL", ln=True, align="C")

    for fila in filas_opciones:            # casilla [ X ] de la naturaleza
        check1 = "[ X ]" if fila[0] == tipo_ausencia else "[   ]"
        check2 = "[ X ]" if fila[1] == tipo_ausencia else "[   ]"
        pdf.cell(65, 6, f"{check1} {fila[0]}", border=0)
        pdf.cell(65, 6, f"{check2} {fila[1]}", border=0, ln=True)''',
    },
    {
        "imagen": "codigo_04_vigencia_baja_logica.png",
        "archivo": "src/features/vigencia.py",
        "modulo": "Vigencia de usuarios (baja lógica semestral)",
        "codigo": '''def ejecutar_depuracion_semestral():
    """Baja lógica a usuarios sin actividad en los últimos 6 meses."""
    conn = get_connection()
    cursor = conn.cursor()

    query_update = """
        UPDATE usuario
        SET estado_vigencia = FALSE
        WHERE estado_vigencia = TRUE
        AND ultima_actividad < CURRENT_DATE - INTERVAL '6 months'
    """
    cursor.execute(query_update)
    filas_afectadas = cursor.rowcount
    conn.commit()
    return True, filas_afectadas''',
    },
    {
        "imagen": "codigo_05_workflow_dias_habiles.png",
        "archivo": "src/core/workflow.py  +  src/core/utils.py",
        "modulo": "Estados del workflow y cálculo de días hábiles",
        "codigo": '''# src/core/workflow.py
ESTADO_INGRESADA = "Ingresada"
ESTADO_PENDIENTE_FIRMA_COORDINADOR = "Pendiente de Firma Coordinador"
ESTADO_PENDIENTE_APROBACION_GERENCIA = "Pendiente de Aprobación Gerencia"
ESTADO_FINALIZADA = "Finalizada"

# src/core/utils.py
def calcular_dias_habiles(fecha_inicio, fecha_fin):
    """Cuenta los días hábiles (lunes a viernes) entre dos fechas."""
    dias = 0
    actual = fecha_inicio
    while actual <= fecha_fin:
        if actual.weekday() < 5:
            dias += 1
        actual += datetime.timedelta(days=1)
    return dias''',
    },
    {
        "imagen": "codigo_06_firmas_base64.png",
        "archivo": "src/services/utils_firma.py",
        "modulo": "Captura de firmas digitalizadas (Canvas / Base64)",
        "codigo": '''def canvas_to_base64(canvas_image_data):
    """Convierte el trazo del Canvas a Base64 para incrustarlo en el PDF."""
    img = Image.fromarray(canvas_image_data.astype('uint8'), 'RGBA')
    alpha = img.split()[-1]
    bbox = alpha.getbbox()

    if not bbox:
        return None                       # lienzo vacío -> sin firma

    img_cropped = img.crop(bbox)
    fondo_blanco = Image.new("RGB", new_size, (255, 255, 255))
    buffered = io.BytesIO()
    fondo_blanco.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")''',
    },
]


# ---------------------------------------------------------------------------
# Utilidades de render
# ---------------------------------------------------------------------------
def _font(bold=False, italic=False):
    if bold and italic:
        name = "consolaz.ttf"
    elif bold:
        name = "consolab.ttf"
    elif italic:
        name = "consolai.ttf"
    else:
        name = "consola.ttf"
    return ImageFont.truetype(str(FONTS_DIR / name), FS)


def _color_token(ttype):
    info = STYLE.style_for_token(ttype)
    c = info.get("color") or ""
    if not c:
        return COLOR_TEXTO, False, False
    c = c if c.startswith("#") else "#" + c
    return c, bool(info.get("bold")), bool(info.get("italic"))


def _tokenizar_lineas(codigo):
    lineas = [[]]
    for ttype, value in lex(codigo, PythonLexer()):
        partes = value.replace("\t", "    ").split("\n")
        for i, parte in enumerate(partes):
            if i > 0:
                lineas.append([])
            if parte:
                lineas[-1].append((ttype, parte))
    return lineas


def render(item) -> Path:
    lineas = _tokenizar_lineas(item["codigo"])
    fuente = _font()
    char_w = fuente.getlength("M")

    max_cols = max((sum(len(t) for _, t in ln) for ln in lineas), default=1)
    num_digitos = len(str(len(lineas)))
    gutter_w = int(num_digitos * char_w) + GUTTER

    ancho_codigo = int(max_cols * char_w)
    ancho = PAD * 2 + gutter_w + ancho_codigo
    alto_codigo = len(lineas) * LINE_H
    alto = TITLE_H + PAD + alto_codigo + PAD

    img = Image.new("RGB", (ancho, alto), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # Barra de título
    draw.rectangle([0, 0, ancho, TITLE_H], fill=COLOR_TITLE_BG)
    for i, col in enumerate(("#FF5F56", "#FFBD2E", "#27C93F")):
        cx = PAD - 4 + i * (int(FS * 0.75))
        cy = TITLE_H // 2
        r = int(FS * 0.22)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    tx = PAD - 4 + 3 * int(FS * 0.75) + int(FS * 0.6)
    draw.text((tx, TITLE_H // 2), item["archivo"], font=_font(bold=True),
              fill=COLOR_TITLE_FG, anchor="lm")

    # Líneas de código
    y0 = TITLE_H + PAD
    for idx, linea in enumerate(lineas, start=1):
        y = y0 + (idx - 1) * LINE_H
        # Número de línea
        draw.text((PAD + gutter_w - GUTTER, y), f"{idx:>{num_digitos}}",
                  font=fuente, fill=COLOR_GUTTER, anchor="lt")
        # Tokens
        x = PAD + gutter_w
        for ttype, texto in linea:
            color, bold, italic = _color_token(ttype)
            draw.text((x, y), texto, font=_font(bold=bold, italic=italic), fill=color)
            x += len(texto) * char_w

    # Borde
    draw.rectangle([0, 0, ancho - 1, alto - 1], outline=COLOR_BORDE, width=SCALE)

    salida = OUT_DIR / item["imagen"]
    img.save(salida)
    return salida


def main() -> None:
    manifest = []
    for item in CAPTURAS:
        ruta = render(item)
        manifest.append({
            "imagen": item["imagen"],
            "archivo": item["archivo"],
            "modulo": item["modulo"],
        })
        print("Captura generada:", ruta, Image.open(ruta).size)

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Manifiesto:", OUT_DIR / "manifest.json")


if __name__ == "__main__":
    main()
