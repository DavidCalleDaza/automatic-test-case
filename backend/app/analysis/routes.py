from flask import render_template, flash, redirect, url_for, request, current_app, session, send_file
from flask_login import current_user, login_required
from app import db
from app.analysis import bp
from app.analysis.forms import RequerimientoUploadForm
from app.models import Plantilla, MapaPlantilla
import os
import docx 
import google.generativeai as genai
import json
import re
from io import BytesIO
import openpyxl

# (La función 'leer_texto_requerimiento' es la misma de antes)
def leer_texto_requerimiento(archivo):
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

# ==============================================================================
# ¡FUNCIÓN DE GENERACIÓN DE EXCEL (CORREGIDA)!
# ==============================================================================
def generar_excel_entregable(plantilla_obj, datos_ia):
    """
    Toma la plantilla original, su mapa de etiquetas y los datos de la IA,
    y genera un nuevo archivo Excel rellenado.
    """
    try:
        # 1. Cargar la plantilla original desde la carpeta 'uploads'
        path_plantilla = os.path.join(
            current_app.config['UPLOAD_FOLDER'], 
            plantilla_obj.filename_seguro
        )
        workbook = openpyxl.load_workbook(path_plantilla)
        sheet = workbook.active
        
        # 2. Crear el mapa de etiquetas (ej: {'TITULO_CASO': 'B', 'ID_CASO': 'A'})
        mapa_etiquetas = {mapa.etiqueta: mapa.coordenada for mapa in plantilla_obj.mapas}
        
        # 3. Encontrar la primera fila vacía después de los encabezados
        fila_inicio = sheet.max_row + 1
        
        # 4. Iterar sobre los datos de la IA (lista de diccionarios)
        for caso in datos_ia:
            # 5. Rellenar la fila
            for etiqueta, valor in caso.items():
                if etiqueta in mapa_etiquetas:
                    columna = mapa_etiquetas[etiqueta] # Ej: 'B'
                    
                    # --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
                    valor_final = valor
                    # Si el valor que nos dio la IA es una LISTA...
                    if isinstance(valor, list):
                        # ...la unimos en un solo string con saltos de línea.
                        valor_final = "\n".join(valor)
                    # --- FIN DE LA CORRECCIÓN ---

                    # Escribimos el valor final (string) en la celda
                    sheet[f"{columna}{fila_inicio}"] = valor_final
            
            fila_inicio += 1 # Pasamos a la siguiente fila
            
        # 6. Guardar el archivo en un buffer de memoria
        buffer_memoria = BytesIO()
        workbook.save(buffer_memoria)
        buffer_memoria.seek(0) # Rebobinamos el buffer al inicio
        
        return buffer_memoria

    except Exception as e:
        # Imprimimos el error en la consola de Flask para depurarlo
        print(f"Error generando Excel: {e}")
        return None

# ==============================================================================
# (El resto de las rutas son las mismas)
# ==============================================================================

@bp.route('/analysis', methods=['GET', 'POST'])
@login_required
def analysis_index():
    form = RequerimientoUploadForm()
    
    plantillas_usuario = Plantilla.query.filter_by(
        autor=current_user
    ).with_entities(Plantilla.id, Plantilla.nombre_plantilla).all()
    form.plantilla.choices = [(p.id, p.nombre_plantilla) for p in plantillas_usuario]
    
    ai_result_raw = session.get('ai_result_raw', None)
    ai_result_data = None
    plantilla_id_sesion = session.get('plantilla_seleccionada_id', None)
    
    if ai_result_raw:
        try:
            match = re.search(r'\[.*\]', ai_result_raw, re.DOTALL)
            json_text = match.group(0) if match else ai_result_raw
            ai_result_data = json.loads(json_text)
        except Exception:
            ai_result_data = None
    
    # (¡CORREGIDO! No borramos la sesión aquí)
    
    if form.validate_on_submit():
        archivo = form.archivo_requerimiento.data
        plantilla_seleccionada_id = form.plantilla.data
        plantilla_obj = Plantilla.query.get(plantilla_seleccionada_id)
        
        mapas = plantilla_obj.mapas.all()
        if not mapas:
            flash(f"La plantilla '{plantilla_obj.nombre_plantilla}' no tiene etiquetas escaneadas.", "danger")
            return redirect(url_for('analysis.analysis_index'))
            
        lista_de_etiquetas = [mapa.etiqueta for mapa in mapas]
        
        texto_requerimiento = leer_texto_requerimiento(archivo)
        
        if texto_requerimiento:
            try:
                api_key = os.environ.get('GOOGLE_API_KEY') 
                if not api_key:
                    flash("Error: GOOGLE_API_KEY no está configurada.", "danger")
                    return redirect(url_for('analysis.analysis_index'))
                
                genai.configure(api_key=api_key)
                
                model = genai.GenerativeModel('gemini-2.0-flash-exp') 
                
                prompt = f"""
                Eres un Analista de QA experto. 
                Basado en el siguiente requerimiento, genera una lista de 5 casos de prueba (positivos y negativos).
                REQUERIMIENTO:
                ---
                {texto_requerimiento}
                ---
                Quiero que la respuesta sea ÚNICAMENTE un array de objetos JSON.
                Para CADA caso de prueba, necesito que generes los siguientes campos:
                {json.dumps(lista_de_etiquetas)}
                Asegúrate de que la respuesta sea solo el JSON.
                """
                
                response = model.generate_content(prompt)
                
                session['ai_result_raw'] = response.text
                session['plantilla_seleccionada_id'] = plantilla_seleccionada_id
                
                flash("¡Requerimiento analizado por la IA exitosamente!", "success")
                
            except Exception as e:
                flash(f"Error al contactar la API de Gemini: {str(e)}", "danger")
        
        return redirect(url_for('analysis.analysis_index'))

    return render_template('analysis/analysis.html', 
                           title='Análisis de Requerimiento', 
                           form=form,
                           ai_result_data=ai_result_data,
                           ai_result_raw=ai_result_raw,
                           plantilla_id=plantilla_id_sesion)

@bp.route('/generate_file')
@login_required
def generate_file():
    
    json_text = session.get('ai_result_raw')
    plantilla_id = session.get('plantilla_seleccionada_id')
    
    if not json_text or not plantilla_id:
        flash("Error: No se encontraron datos de la IA o plantilla en la sesión. Por favor, vuelve a analizar el requerimiento.", "danger")
        return redirect(url_for('analysis.analysis_index'))
        
    plantilla_obj = Plantilla.query.get_or_404(plantilla_id)
    
    try:
        match = re.search(r'\[.*\]', json_text, re.DOTALL)
        datos_ia = json.loads(match.group(0))
    except Exception:
        flash("Error: Los datos de la IA estaban corruptos. Por favor, vuelve a analizar.", "danger")
        return redirect(url_for('analysis.analysis_index'))
        
    buffer_memoria = None
    
    if plantilla_obj.tipo_archivo == 'Excel':
        buffer_memoria = generar_excel_entregable(plantilla_obj, datos_ia)
    elif plantilla_obj.tipo_archivo == 'Word':
        flash("La generación de archivos Word aún está en desarrollo.", "info")
        return redirect(url_for('analysis.analysis_index'))
    
    if buffer_memoria:
        # ¡CORREGIDO! Limpiamos la sesión DESPUÉS de usar los datos.
        session.pop('ai_result_raw', None)
        session.pop('plantilla_seleccionada_id', None)
        
        return send_file(
            buffer_memoria,
            as_attachment=True,
            download_name=f"entregable_{plantilla_obj.filename_seguro}",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        # ¡CAMBIO! Este es el error que viste.
        flash("Error desconocido al generar el archivo Excel.", "danger")
        return redirect(url_for('analysis.analysis_index'))