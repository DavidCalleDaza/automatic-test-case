from flask import render_template, flash, redirect, url_for, request, current_app, session, send_file
from flask_login import current_user, login_required
from app import db
from app.analysis import bp
from app.analysis.forms import RequerimientoUploadForm
from app.models import Plantilla, MapaPlantilla
import os
import docx
from docx.shared import Pt 
import google.generativeai as genai
import json
import re
from io import BytesIO
import openpyxl
import traceback

# --- Constantes ---
ALLOWED_EXTENSIONS = {'xlsx', 'docx'}
TAG_REGEX = re.compile(r"(\{\{.*?\}\})") 
TAG_CLEANER = re.compile(r"\{\{(.*?)\}\}") 

# ==============================================================================
# FUNCIONES AUXILIARES
# (Estas funciones: leer_texto_requerimiento, generar_excel_entregable, 
# reemplazar_texto_en_parrafo, y generar_word_entregable 
# NO CAMBIAN. Se asume que están aquí.)
# ...
# ==============================================================================

# ... (Pega aquí tus funciones auxiliares: leer_texto_requerimiento, 
#      generar_excel_entregable, y generar_word_entregable) ...
#
# (Solo voy a re-escribir la parte que cambia: las RUTAS)
#
# ==============================================================================

def leer_texto_requerimiento(archivo):
    """Lee el contenido de un archivo de requerimiento (.docx, .txt, .md)"""
    filename = archivo.filename
    text_content = ""
    try:
        if filename.endswith('.docx'):
            doc = docx.Document(archivo)
            for para in doc.paragraphs:
                text_content += para.text + "\n"
        elif filename.endswith('.txt') or filename.endswith('.md'):
            text_content = archivo.read().decode('utf-8')
        return text_content
    except Exception as e:
        flash(f"Error al leer el archivo: {str(e)}", "danger")
        return None


def generar_excel_entregable(plantilla_obj, datos_ia):
    """
    Genera un archivo Excel rellenando la plantilla con los datos de la IA.
    ¡CORREGIDO! Ahora busca la fila de encabezado para insertar datos.
    """
    try:
        path_plantilla = os.path.join(current_app.config['UPLOAD_FOLDER'], plantilla_obj.filename_seguro)
        workbook = openpyxl.load_workbook(path_plantilla)
        sheet = workbook.active
        
        # Mapa de etiquetas (etiqueta -> coordenada)
        mapa_etiquetas = {mapa.etiqueta: mapa.coordenada for mapa in plantilla_obj.mapas}
        
        # Lógica para tipo tabular (fila_tabla)
        if all(m.tipo_mapa == 'fila_tabla' for m in plantilla_obj.mapas):
            
            # --- ¡INICIO DE LA NUEVA LÓGICA! ---
            header_row_index = -1
            
            # Intentar encontrar la fila de encabezado
            if mapa_etiquetas:
                # Tomar la primera etiqueta y columna para buscar
                primera_etiqueta_limpia = list(mapa_etiquetas.keys())[0]
                etiqueta_buscar = f"{{{{{primera_etiqueta_limpia}}}}}" # ej. "{{Proceso o Funcionalidad}}"
                columna_buscar = mapa_etiquetas[primera_etiqueta_limpia] # ej. "A"

                try:
                    # Iterar por la columna A (o la que sea) para encontrar la etiqueta
                    for cell in sheet[columna_buscar]:
                        if isinstance(cell.value, str) and etiqueta_buscar in cell.value:
                            header_row_index = cell.row # ej. 10
                            break
                except KeyError:
                    # La columna podría no existir si la hoja está muy vacía
                    pass 

            if header_row_index != -1:
                # Encontramos la fila de encabezado (ej. 10), empezamos en la siguiente (ej. 11)
                fila_inicio = header_row_index + 1
            else:
                # Fallback: si no encontramos la etiqueta, usamos la lógica anterior (que tenía el bug)
                fila_inicio = sheet.max_row + 1
            # --- FIN DE LA NUEVA LÓGICA ---

            for caso in datos_ia:
                for etiqueta, valor in caso.items():
                    if etiqueta in mapa_etiquetas:
                        columna = mapa_etiquetas[etiqueta]
                        valor_final = valor
                        if isinstance(valor, list):
                            valor_final = "\n".join(str(v) for v in valor)
                        
                        sheet[f"{columna}{fila_inicio}"] = valor_final
                fila_inicio += 1 # Incrementar la fila para el siguiente caso
        
        else:
            # Lógica para tipo formulario (celda_simple) o mixto
            # (Esta lógica no cambia)
            if datos_ia:
                caso_principal = datos_ia[0] # Usar solo el primer caso
                for etiqueta, valor in caso_principal.items():
                    if etiqueta in mapa_etiquetas:
                        coordenada = mapa_etiquetas[etiqueta] # ej. "B5"
                        valor_final = valor
                        if isinstance(valor, list):
                            valor_final = "\n".join(str(v) for v in valor)
                        sheet[coordenada] = valor_final
        
        buffer_memoria = BytesIO()
        workbook.save(buffer_memoria)
        buffer_memoria.seek(0)
        return buffer_memoria
    except Exception as e:
        print(f"Error generando Excel: {e}")
        traceback.print_exc()
        return None

def reemplazar_texto_en_parrafo(parrafo, etiqueta, valor):
    """Reemplaza una etiqueta en un párrafo de Word manteniendo el formato"""
    if etiqueta in parrafo.text:
        for run in parrafo.runs:
            if etiqueta in run.text:
                run.text = run.text.replace(etiqueta, str(valor))


def generar_word_entregable(plantilla_obj, datos_ia):
    """
    Genera documento Word con casos de prueba.
    CORREGIDO: Ahora reemplaza correctamente las etiquetas en tablas.
    """
    try:
        # 1. Cargar la plantilla original
        path_plantilla = os.path.join(
            current_app.config['UPLOAD_FOLDER'], 
            plantilla_obj.filename_seguro
        )
        document = docx.Document(path_plantilla)
        
        # 2. Crear los mapas de etiquetas
        mapa_simple = {
            mapa.etiqueta: f"{{{{{mapa.etiqueta}}}}}" 
            for mapa in plantilla_obj.mapas 
            if mapa.tipo_mapa == 'celda_simple'
        }
        mapa_tabla = {
            mapa.etiqueta: int(mapa.coordenada) 
            for mapa in plantilla_obj.mapas 
            if mapa.tipo_mapa == 'fila_tabla'
        }
        etiquetas_tabla_keys = list(mapa_tabla.keys())
        
        # 3. Iterar sobre CADA caso de prueba
        for i, caso_ia in enumerate(datos_ia):
            
            if i == 0:
                # ========================================================
                # CASO 1: RELLENAR LA PLANTILLA EXISTENTE
                # ========================================================
                
                # 4a. Rellenar Etiquetas Simples (Párrafos y Celdas)
                for etiqueta_limpia, etiqueta_sucia in mapa_simple.items():
                    if etiqueta_limpia in caso_ia:
                        valor = caso_ia[etiqueta_limpia]
                        
                        # Reemplazar en párrafos normales
                        for para in document.paragraphs:
                            reemplazar_texto_en_parrafo(para, etiqueta_sucia, valor)
                        
                        # Reemplazar en tablas
                        for table in document.tables:
                            for row in table.rows:
                                for cell in row.cells:
                                    for para in cell.paragraphs:
                                        reemplazar_texto_en_parrafo(para, etiqueta_sucia, valor)

                # 4b. Rellenar Etiquetas de Tabla (Filas Repetibles)
                if etiquetas_tabla_keys:
                    tabla_encontrada = None
                    fila_plantilla_idx = -1
                    
                    # Buscar la tabla que contiene las etiquetas
                    for table in document.tables:
                        if fila_plantilla_idx != -1: 
                            break
                        for r_idx, row in enumerate(table.rows):
                            try:
                                primera_etiqueta = etiquetas_tabla_keys[0]
                                primera_celda_idx = mapa_tabla[primera_etiqueta]
                                
                                if f"{{{{{primera_etiqueta}}}}}" in row.cells[primera_celda_idx].text:
                                    tabla_encontrada = table
                                    fila_plantilla_idx = r_idx
                                    break
                            except (IndexError, KeyError):
                                continue
                    
                    if tabla_encontrada and fila_plantilla_idx != -1:
                        # ------ LOGICA MEJORADA: Detectar si 'PASOS' es un sub-array
                        # o si los datos son planos.
                        
                        # Caso A: 'PASOS' existe como un sub-array (Plantilla antigua)
                        datos_pasos = caso_ia.get("PASOS", [])
                        
                        # Caso B: No hay 'PASOS', los datos vienen planos (Plantilla nueva)
                        if not datos_pasos and all(key in caso_ia for key in etiquetas_tabla_keys):
                             # Creamos un array 'datos_pasos' artificial
                             # con los datos del objeto 'caso_ia' principal
                             datos_pasos = [caso_ia]

                        if datos_pasos and len(datos_pasos) > 0:
                            # CRÍTICO: Guardar la fila plantilla ANTES de modificarla
                            fila_plantilla_original = tabla_encontrada.rows[fila_plantilla_idx]
                            textos_plantilla = {}
                            
                            # Guardar el texto de cada celda con su etiqueta
                            for etiqueta_limpia, col_idx in mapa_tabla.items():
                                try:
                                    textos_plantilla[etiqueta_limpia] = fila_plantilla_original.cells[col_idx].text
                                except IndexError:
                                    textos_plantilla[etiqueta_limpia] = f"{{{{{etiqueta_limpia}}}}}"
                            
                            # Rellenar TODOS los pasos (incluyendo el primero)
                            for paso_idx, paso_ia in enumerate(datos_pasos):
                                if paso_idx == 0:
                                    # Primera fila: usar la fila plantilla existente
                                    fila_actual = fila_plantilla_original
                                else:
                                    # Resto de filas: clonar
                                    fila_actual = tabla_encontrada.add_row()
                                
                                # Rellenar cada celda de la fila
                                for etiqueta_limpia, col_idx in mapa_tabla.items():
                                    try:
                                        if paso_idx > 0:
                                            # Para filas nuevas, copiar el texto plantilla
                                            fila_actual.cells[col_idx].text = textos_plantilla.get(etiqueta_limpia, "")
                                        
                                        # Reemplazar la etiqueta con el valor real
                                        if etiqueta_limpia in paso_ia:
                                            valor_paso = str(paso_ia[etiqueta_limpia])
                                            etiqueta_sucia = f"{{{{{etiqueta_limpia}}}}}"
                                            texto_actual = fila_actual.cells[col_idx].text
                                            fila_actual.cells[col_idx].text = texto_actual.replace(etiqueta_sucia, valor_paso)
                                    except IndexError:
                                        continue
            
            else:
                # ========================================================
                # CASOS 2, 3, 4, 5+: AÑADIR NUEVO CONTENIDO AL FINAL
                # ========================================================
                
                document.add_page_break()
                
                # Intentar obtener un ID y Título
                id_caso_val = caso_ia.get('ID del caso de prueba', caso_ia.get('ID_CASO_PRUEBA', ''))
                titulo_val = caso_ia.get('Descripción del caso de prueba', caso_ia.get('TITULO_CASO_PRUEBA', ''))
                
                titulo_completo = f"Caso de Prueba: {id_caso_val} - {titulo_val}"
                document.add_heading(titulo_completo, level=2)
                
                # Añadir todos los campos simples que existan
                for etiqueta_limpia in mapa_simple.keys():
                    if etiqueta_limpia in caso_ia:
                        document.add_heading(etiqueta_limpia.replace('_', ' ').title(), level=3)
                        document.add_paragraph(str(caso_ia[etiqueta_limpia]))

                # --- Lógica de tabla nueva ---
                datos_pasos = caso_ia.get("PASOS", [])
                if not datos_pasos and all(key in caso_ia for key in etiquetas_tabla_keys):
                     datos_pasos = [caso_ia]

                if datos_pasos and etiquetas_tabla_keys:
                    document.add_heading("Detalle de Ejecución", level=3)
                    tabla_nueva = document.add_table(rows=1, cols=len(etiquetas_tabla_keys))
                    
                    try:
                        tabla_nueva.style = 'Light Grid Accent 1'
                    except KeyError:
                        tabla_nueva.style = 'Table Grid'
                    
                    # Encabezados
                    hdr_cells = tabla_nueva.rows[0].cells
                    for idx, etiqueta in enumerate(etiquetas_tabla_keys):
                        hdr_cells[idx].text = etiqueta
                    
                    # Filas de datos
                    for paso_ia in datos_pasos:
                        row_cells = tabla_nueva.add_row().cells
                        for idx, etiqueta_limpia in enumerate(etiquetas_tabla_keys):
                            if etiqueta_limpia in paso_ia:
                                row_cells[idx].text = str(paso_ia[etiqueta_limpia])
                            else:
                                row_cells[idx].text = ""

        # 5. Guardar el documento
        buffer_memoria = BytesIO()
        document.save(buffer_memoria)
        buffer_memoria.seek(0)
        
        return buffer_memoria

    except Exception as e:
        print(f"Error generando Word: {e}")
        traceback.print_exc()
        return None


# ==============================================================================
# RUTAS (ESTA ES LA SECCIÓN CRÍTICA QUE CAMBIA)
# ==============================================================================

@bp.route('/analysis', methods=['GET', 'POST'])
@login_required
def analysis_index():
    """Ruta principal para análisis de requerimientos con IA"""
    form = RequerimientoUploadForm()
    
    # Obtener plantillas del usuario actual
    plantillas_usuario = Plantilla.query.filter_by(
        autor=current_user
    ).with_entities(Plantilla.id, Plantilla.nombre_plantilla).all()
    form.plantilla.choices = [(p.id, p.nombre_plantilla) for p in plantillas_usuario]
    
    # Recuperar datos de la sesión
    ai_result_raw = session.get('ai_result_raw', None)
    ai_result_data = None
    plantilla_id_sesion = session.get('plantilla_seleccionada_id', None)
    
    # Parsear el resultado de la IA si existe
    if ai_result_raw:
        try:
            match = re.search(r'\[.*\]', ai_result_raw, re.DOTALL)
            json_text = match.group(0) if match else ai_result_raw
            ai_result_data = json.loads(json_text)
        except Exception as e:
            print(f"Error parseando resultado de IA: {e}")
            ai_result_data = None
            
    # Procesar el formulario
    if form.validate_on_submit():
        archivo = form.archivo_requerimiento.data
        plantilla_seleccionada_id = form.plantilla.data
        plantilla_obj = Plantilla.query.get(plantilla_seleccionada_id)
        
        # Verificar que la plantilla tenga etiquetas
        mapas = plantilla_obj.mapas.all()
        if not mapas:
            flash(f"La plantilla '{plantilla_obj.nombre_plantilla}' no tiene etiquetas escaneadas.", "danger")
            return redirect(url_for('analysis.analysis_index'))
            
        # Separar etiquetas por tipo
        etiquetas_simples = [m.etiqueta for m in mapas if m.tipo_mapa == 'celda_simple']
        etiquetas_tabla = [m.etiqueta for m in mapas if m.tipo_mapa == 'fila_tabla']
        
        # Leer el contenido del archivo de requerimiento
        texto_requerimiento = leer_texto_requerimiento(archivo)
        
        if texto_requerimiento:
            try:
                # Configurar API de Gemini
                api_key = os.environ.get('GOOGLE_API_KEY') 
                if not api_key:
                    flash("Error: GOOGLE_API_KEY no está configurada.", "danger")
                    return redirect(url_for('analysis.analysis_index'))
                
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-2.0-flash-exp') 
                
                # ==========================================================
                # ¡AQUÍ ESTÁ LA NUEVA LÓGICA DE PROMPT!
                # ==========================================================
                
                prompt = f"""
                Eres un Ingeniero de QA Senior, experto en análisis de requerimientos y diseño de Casos de Prueba.
                Basado en el siguiente requerimiento, genera un set de 5 casos de prueba exhaustivos (positivos y negativos).
                
                REQUERIMIENTO:
                ---
                {texto_requerimiento}
                ---
                
                INSTRUCCIONES CRÍTICAS:
                1. La respuesta debe ser ÚNICAMENTE un array de objetos JSON, sin texto adicional.
                """
                
                # CASO 1: Plantilla Mixta (Formulario + Tabla de Pasos)
                # (Ej. "TITULO" es simple, "PASOS" es tabla)
                if etiquetas_simples and etiquetas_tabla:
                    prompt += f"""
                    2. Debes generar EXACTAMENTE estos campos para cada caso de prueba:
                       {json.dumps(etiquetas_simples, ensure_ascii=False)}
                    
                    3. ADICIONALMENTE, genera un campo "PASOS" como array de objetos con estos campos:
                       {json.dumps(etiquetas_tabla, ensure_ascii=False)}
                       
                       Cada paso debe tener TODOS estos campos llenos con información relevante.
                    
                    4. TODOS los campos de la lista principal (punto 2) deben ser strings de texto.
                    """

                # CASO 2: Plantilla Tabular Plana (¡TU NUEVO CASO!)
                # (Ej. Todos los campos son 'fila_tabla')
                elif not etiquetas_simples and etiquetas_tabla:
                    prompt += f"""
                    2. Debes generar EXACTAMENTE estos campos para cada caso de prueba.
                       {json.dumps(etiquetas_tabla, ensure_ascii=False)}

                    3. TODOS los campos deben ser strings de texto.
                    4. Si un campo se llama 'Pasos' o similar, debe ser un solo string con saltos de línea.
                       (Ej: "1. Abrir app\\n2. Ingresar credenciales\\n3. Clic en Login")
                    """
                
                # CASO 3: Plantilla de Formulario Simple (Solo 'celda_simple')
                elif etiquetas_simples and not etiquetas_tabla:
                    prompt += f"""
                    2. Debes generar EXACTAMENTE estos campos para cada caso de prueba.
                       {json.dumps(etiquetas_simples, ensure_ascii=False)}

                    3. TODOS los campos deben ser strings de texto.
                    4. Si un campo se llama 'Pasos' o similar, debe ser un solo string con saltos de línea.
                       (Ej: "1. Abrir app\\n2. Ingresar credenciales\\n3. Clic en Login")
                    """

                prompt += """
                
                IMPORTANTE: 
                - Genera TODOS los campos de la lista exactamente como están escritos.
                - NO inventes campos adicionales.
                - NO omitas ningún campo.
                - Asegúrate de que el JSON sea válido y parseable.
                """
                # ==========================================================
                # FIN DE LA LÓGICA DE PROMPT
                # ==========================================================
                
                # Llamar a la API de Gemini
                response = model.generate_content(prompt)
                
                # Guardar el resultado en la sesión
                session['ai_result_raw'] = response.text
                session['plantilla_seleccionada_id'] = plantilla_seleccionada_id
                
                flash("¡Requerimiento analizado por la IA exitosamente!", "success")
                
            except Exception as e:
                flash(f"Error al contactar la API de Gemini: {str(e)}", "danger")
                traceback.print_exc()
        
        return redirect(url_for('analysis.analysis_index'))

    return render_template('analysis/analysis.html', 
                           title='Análisis de Requerimiento', 
                           form=form,
                           ai_result_data=ai_result_data,
                           ai_result_raw=ai_result_raw,
                           plantilla_id=plantilla_id_sesion)


@bp.route('/analysis/clear', methods=['POST'])
@login_required
def clear_analysis():
    """Limpia los resultados del análisis de la sesión"""
    session.pop('ai_result_raw', None)
    session.pop('plantilla_seleccionada_id', None)
    flash("Análisis limpiado correctamente.", "info")
    return redirect(url_for('analysis.analysis_index'))


@bp.route('/generate_file')
@login_required
def generate_file():
    """Genera y descarga el archivo entregable (Excel o Word)"""
    
    # Recuperar datos de la sesión
    json_text = session.get('ai_result_raw')
    plantilla_id = session.get('plantilla_seleccionada_id')
    
    if not json_text or not plantilla_id:
        flash("Error: No se encontraron datos de la IA o plantilla en la sesión. Por favor, vuelve a analizar el requerimiento.", "danger")
        return redirect(url_for('analysis.analysis_index'))
        
    plantilla_obj = Plantilla.query.get_or_404(plantilla_id)
    
    # Parsear los datos de la IA
    try:
        match = re.search(r'\[.*\]', json_text, re.DOTALL)
        datos_ia = json.loads(match.group(0))
    except Exception as e:
        flash("Error: Los datos de la IA estaban corruptos. Por favor, vuelve a analizar.", "danger")
        traceback.print_exc()
        return redirect(url_for('analysis.analysis_index'))
        
    buffer_memoria = None
    mimetype = ""
    download_name = ""
    
    # Generar el archivo según el tipo de plantilla
    if plantilla_obj.tipo_archivo == 'Excel':
        buffer_memoria = generar_excel_entregable(plantilla_obj, datos_ia)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        download_name = f"entregable_{os.path.splitext(plantilla_obj.filename_seguro)[0]}.xlsx"
        
    elif plantilla_obj.tipo_archivo == 'Word':
        buffer_memoria = generar_word_entregable(plantilla_obj, datos_ia)
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        download_name = f"entregable_{os.path.splitext(plantilla_obj.filename_seguro)[0]}.docx"
    
    if buffer_memoria:
        # Limpiar la sesión después de generar el archivo
        session.pop('ai_result_raw', None)
        session.pop('plantilla_seleccionada_id', None)
        
        return send_file(
            buffer_memoria,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
    else:
        flash(f"Error al generar el archivo {plantilla_obj.tipo_archivo}. Revisa los logs del servidor para más detalles.", "danger")
        return redirect(url_for('analysis.analysis_index'))