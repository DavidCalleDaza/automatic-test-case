from flask import render_template, flash, redirect, url_for, request, current_app
from flask_login import current_user, login_required
from app import db
from app.core import bp
from app.core.forms import PlantillaUploadForm
from app.models import Plantilla, MapaPlantilla
import os
from werkzeug.utils import secure_filename
import openpyxl 
import docx
import re

# --- Constantes ---
ALLOWED_EXTENSIONS = {'xlsx', 'docx'}
TAG_REGEX = re.compile(r"(\{\{.*?\}\})") 
TAG_CLEANER = re.compile(r"\{\{(.*?)\}\}") 

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==============================================================================
# (Función de escaneo Tabular (Horizontal) - 'scan_excel_plantilla'
#  La he renombrado a 'scan_tabular_excel' para más claridad)
# ==============================================================================
def scan_tabular_excel(file_path, plantilla_obj):
    mapas_encontrados = []
    try:
        workbook = openpyxl.load_workbook(file_path, read_only=True)
        sheet = workbook.active
        fila_encontrada = False
        
        for row in sheet.iter_rows(min_row=1, max_row=50): # Escaneamos solo las primeras 50 filas
            if fila_encontrada:
                break
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    if TAG_REGEX.search(cell.value):
                        fila_encontrada = True
                        etiqueta_sucia = cell.value.strip()
                        etiqueta_limpia = TAG_CLEANER.search(etiqueta_sucia).group(1)
                        columna = cell.column_letter # Ej: 'A'
                        
                        nuevo_mapa = MapaPlantilla(
                            etiqueta=etiqueta_limpia,
                            coordenada=columna, 
                            tipo_mapa='fila_tabla', # Marcamos como fila repetible
                            plantilla_padre=plantilla_obj
                        )
                        mapas_encontrados.append(nuevo_mapa)
        
        if mapas_encontrados:
            db.session.add_all(mapas_encontrados)
            return True, f"Se encontraron y guardaron {len(mapas_encontrados)} etiquetas (tipo Tabular)."
        else:
            return False, "No se encontraron etiquetas (ej. {{ETIQUETA}}) en las primeras 50 filas."
    except Exception as e:
        return False, f"Error al procesar el archivo Excel: {str(e)}"

# ==============================================================================
# ¡NUEVA FUNCIÓN DE ESCANEO VERTICAL (FORMULARIO)!
# ==============================================================================
def scan_formulario_excel(file_path, plantilla_obj):
    """
    Escanea un archivo Excel (.xlsx) celda por celda, buscando etiquetas
    en cualquier lugar (Formulario) y guarda la coordenada exacta (ej. 'B5').
    """
    mapas_encontrados = []
    try:
        workbook = openpyxl.load_workbook(file_path, read_only=True)
        sheet = workbook.active
        
        # Iteramos por TODAS las celdas usadas
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    # Verificamos si el valor de la celda es una de nuestras etiquetas
                    if TAG_REGEX.search(cell.value):
                        etiqueta_sucia = cell.value.strip()
                        etiqueta_limpia = TAG_CLEANER.search(etiqueta_sucia).group(1)
                        coordenada = cell.coordinate # ¡Obtenemos la celda exacta! Ej: 'B5'
                        
                        nuevo_mapa = MapaPlantilla(
                            etiqueta=etiqueta_limpia,
                            coordenada=coordenada,
                            tipo_mapa='celda_simple', # Marcamos como celda simple
                            plantilla_padre=plantilla_obj
                        )
                        mapas_encontrados.append(nuevo_mapa)
        
        if mapas_encontrados:
            db.session.add_all(mapas_encontrados)
            return True, f"Se encontraron y guardaron {len(mapas_encontrados)} etiquetas (tipo Formulario)."
        else:
            return False, "No se encontraron etiquetas (ej. {{ETIQUETA}}) en el archivo."
    except Exception as e:
        return False, f"Error al procesar el archivo Excel: {str(e)}"

# ==============================================================================
# (Función de escaneo de Word - Actualizada para escanear Vertical/Formulario)
# ==============================================================================
def scan_word_plantilla(file_path, plantilla_obj):
    """
    Escanea un archivo Word (.docx), busca etiquetas "simples" (párrafos) y
    "filas plantilla repetibles" (tablas).
    """
    mapas_encontrados = []
    try:
        document = docx.Document(file_path)
        
        # 1. Escanear Párrafos (Para etiquetas simples - tipo 'celda_simple')
        for para in document.paragraphs:
            if TAG_REGEX.search(para.text):
                for match in TAG_REGEX.finditer(para.text):
                    etiqueta_sucia = match.group(1)
                    etiqueta_limpia = TAG_CLEANER.search(etiqueta_sucia).group(1)
                    nuevo_mapa = MapaPlantilla(etiqueta=etiqueta_limpia, coordenada='parrafo', tipo_mapa='celda_simple', plantilla_padre=plantilla_obj)
                    mapas_encontrados.append(nuevo_mapa)

        # 2. Escanear Tablas (Para filas plantilla repetibles - tipo 'fila_tabla')
        for table in document.tables:
            for i, row in enumerate(table.rows):
                es_fila_plantilla = True
                etiquetas_en_fila = []
                for j, cell in enumerate(row.cells):
                    if not TAG_REGEX.search(cell.text):
                        es_fila_plantilla = False
                        break
                    etiqueta_sucia = TAG_REGEX.search(cell.text.strip()).group(1)
                    etiqueta_limpia = TAG_CLEANER.search(etiqueta_sucia).group(1)
                    etiquetas_en_fila.append((etiqueta_limpia, str(j))) # j es el índice de columna (0, 1, 2...)
                
                if es_fila_plantilla and etiquetas_en_fila:
                    for etiqueta, col_index in etiquetas_en_fila:
                        nuevo_mapa = MapaPlantilla(etiqueta=etiqueta_limpia, coordenada=col_index, tipo_mapa='fila_tabla', plantilla_padre=plantilla_obj)
                        mapas_encontrados.append(nuevo_mapa)
                    
        if mapas_encontrados:
            db.session.add_all(mapas_encontrados)
            return True, f"Se encontraron y guardaron {len(mapas_encontrados)} etiquetas (simples y de tabla)."
        else:
            return False, "No se encontraron etiquetas (ej. {{ETIQUETA}}) en el archivo."
    except Exception as e:
        return False, f"Error al procesar el archivo Word: {str(e)}"

# ==============================================================================
# (Rutas)
# ==============================================================================

@bp.route('/dashboard')
@login_required
def dashboard():
    form = PlantillaUploadForm()
    plantillas_usuario = Plantilla.query.filter_by(autor=current_user).all()
    return render_template('core/dashboard.html', 
                           title='Dashboard', 
                           form=form, 
                           plantillas=plantillas_usuario)

# --- ¡RUTA DE SUBIDA TOTALMENTE ACTUALIZADA! ---
@bp.route('/upload_plantilla', methods=['POST'])
@login_required
def upload_plantilla():
    form = PlantillaUploadForm()
    
    # Manejamos el caso en que el formulario no es válido
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error en el campo "{getattr(form, field).label.text}": {error}', 'danger')
        return redirect(url_for('core.dashboard'))

    # Si el formulario es válido, continuamos
    archivo = form.archivo_plantilla.data
    nombre_seguro = secure_filename(archivo.filename)
    tipo_escaneo_seleccionado = form.tipo_escaneo.data # 'tabular' o 'formulario'
    
    if not allowed_file(nombre_seguro):
        flash('Error: Tipo de archivo no permitido. Sube solo .xlsx o .docx', 'danger')
        return redirect(url_for('core.dashboard'))

    tipo_archivo = 'Excel' if nombre_seguro.endswith('.xlsx') else 'Word'
    
    # 1. Creamos la entrada en la base de datos
    nueva_plantilla = Plantilla(
        nombre_plantilla=form.nombre_plantilla.data,
        tipo_archivo=tipo_archivo,
        autor=current_user,
        filename_seguro=nombre_seguro
    )
    db.session.add(nueva_plantilla)
    
    # 2. Guardamos el archivo físicamente
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, nombre_seguro)
    archivo.save(file_path)
    
    exito = False
    mensaje = ""
    
    # --- ¡NUEVA LÓGICA DE SELECCIÓN DE ESCÁNER! ---
    try:
        if tipo_archivo == 'Excel':
            if tipo_escaneo_seleccionado == 'tabular':
                exito, mensaje = scan_tabular_excel(file_path, nueva_plantilla)
            elif tipo_escaneo_seleccionado == 'formulario':
                exito, mensaje = scan_formulario_excel(file_path, nueva_plantilla)
        
        elif tipo_archivo == 'Word':
            # (Word es siempre tipo 'formulario' o 'tabular' en tablas)
            exito, mensaje = scan_word_plantilla(file_path, nueva_plantilla)

        db.session.commit()
        
        if exito:
            flash(f'¡Plantilla "{nombre_seguro}" subida! {mensaje}', 'success')
        else:
            flash(f'Plantilla subida, pero hubo un problema al escanearla: {mensaje}', 'warning')
    
    except Exception as e:
        db.session.rollback() # Deshacemos todo si falla el escaneo
        flash(f"Error crítico al procesar el archivo: {str(e)}", "danger")
    
    return redirect(url_for('core.dashboard'))

# --- ¡NUEVA RUTA DE ELIMINAR! ---
@bp.route('/plantilla/delete/<int:plantilla_id>', methods=['POST'])
@login_required
def delete_plantilla(plantilla_id):
    """
    Elimina una plantilla y sus archivos asociados.
    """
    # 1. Encontrar la plantilla, asegurándonos que le pertenece al usuario
    plantilla = Plantilla.query.filter_by(id=plantilla_id, autor=current_user).first_or_404()
    
    try:
        # 2. Eliminar el archivo físico de la carpeta 'uploads'
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], plantilla.filename_seguro)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # 3. Eliminar de la base de datos
        # (Gracias al 'cascade delete' que pusimos en models.py,
        #  esto también borrará todos los 'MapaPlantilla' asociados)
        db.session.delete(plantilla)
        db.session.commit()
        
        flash(f"Plantilla '{plantilla.nombre_plantilla}' eliminada exitosamente.", 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar la plantilla: {str(e)}", 'danger')

    return redirect(url_for('core.dashboard'))


# --- (Ruta 'ver_plantilla' - sin cambios) ---
@bp.route('/plantilla/<int:plantilla_id>')
@login_required
def ver_plantilla(plantilla_id):
    plantilla = Plantilla.query.filter_by(id=plantilla_id, autor=current_user).first_or_404()
    mapas = plantilla.mapas.order_by(MapaPlantilla.tipo_mapa).all()
    
    return render_template('core/ver_plantilla.html', 
                           title=f"Detalle: {plantilla.nombre_plantilla}", 
                           plantilla=plantilla, 
                           mapas=mapas)