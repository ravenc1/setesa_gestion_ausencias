# Modulo de firmas digitales por rol.


import base64
from PIL import Image
import io
from src.core.config import FIRMAS_DIR, ensure_dirs

def canvas_to_base64(canvas_image_data):
    """
    Convierte el canvas a Base64.
    Recorta el espacio en blanco y lo centra en un lienzo de proporción 3:1
    con fondo blanco puro para garantizar contraste y alineación perfecta en el PDF.
    """
    if canvas_image_data is not None:
        # Convertir a imagen RGBA
        img = Image.fromarray(canvas_image_data.astype('uint8'), 'RGBA')
        
        # Extraer el canal alfa (transparencia) para detectar dónde hay trazos reales
        alpha = img.split()[-1]
        bbox = alpha.getbbox()
        
        # Si el lienzo está completamente vacío, retorna None
        if not bbox:
            return None
            
        # 1. Recortar la firma a sus límites exactos (eliminando áreas vacías)
        img_cropped = img.crop(bbox)
        
        # 2. Calcular proporciones para forzar un ratio 3:1 (ancho:alto)
        target_w = img_cropped.width
        target_h = int(target_w / 3)
        
        if img_cropped.height > target_h:
            target_h = img_cropped.height
            target_w = int(target_h * 3)
            
        # 3. Crear un lienzo nuevo BLANCO PURO con un margen (padding) de 40px
        new_size = (target_w + 40, target_h + 40)
        fondo_blanco = Image.new("RGB", new_size, (255, 255, 255))
        
        # 4. Centrar matemáticamente el trazo recortado en el nuevo lienzo
        offset_x = (new_size[0] - img_cropped.width) // 2
        offset_y = (new_size[1] - img_cropped.height) // 2
        fondo_blanco.paste(img_cropped, (offset_x, offset_y), img_cropped)
        
        # Guardar como PNG y codificar a Base64
        buffered = io.BytesIO()
        fondo_blanco.save(buffered, format="PNG")
        
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
        
    return None

def base64_to_image(base64_str, output_filename="temp_firma.png"):
    """Toma un string Base64 y crea un archivo temporal para FPDF."""
    if base64_str and isinstance(base64_str, str) and base64_str.strip():
        try:
            ensure_dirs()
            ruta = FIRMAS_DIR / output_filename
            img_data = base64.b64decode(base64_str)
            with open(ruta, "wb") as f:
                f.write(img_data)
            return str(ruta)
        except Exception as e:
            print(f"Error decodificando la firma: {e}")
            return None
    return None