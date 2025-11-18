# ============================================================================
# ARCHIVO: backend/app/analysis/routes.py (CORRECCIÓN DE IMPORTACIONES)
# ============================================================================
import os
import json
import openpyxl
import docx
import re
import xml.etree.ElementTree as ET
import xml.dom.minidom
import google.generativeai as genai
from openpyxl.comments import Comment
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from flask import (
    render_template, flash, redirect, url_for, request, 
    session, jsonify, send_file, current_app
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app import db
from app.analysis import bp
from app.analysis.forms import AnalysisForm
from app.models import ( # <- BLOQUE DE IMPORTACIÓN CORREGIDO
    Usuario, Plantilla, MapaPlantilla, Analisis, AnalisisDato, HistorialCambios
)

# --- Sinónimos ---
OBSERVACIONES_SYNONYMS = [
    'observa', 'comenta', 'nota', 'aclara', 'anota', 'apunte', 
    'considera', 'indica', 'adverten'
]
ID_CASO_SYNONYMS = ['id', 'caso', 'cp', 'identificador']

# ==============================================================================
# FUNCIONES DE AYUDA: LECTURA Y ANÁLISIS
# ==============================================================================

def leer_requerimiento(filepath):
    """Lee archivos .txt, .docx, .xlsx y retorna el texto completo."""
    _, extension = os.path.splitext(filepath)
    texto_completo = ""
    try:
        if extension == '.txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                texto_completo = f.read()
        elif extension == '.docx':
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                texto_completo += para.text + '\n'
        elif extension == '.xlsx':
            workbook = openpyxl.load_workbook(filepath, data_only=True)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                texto_completo += f"\n--- INICIO HOJA: {sheet_name} ---\n"
                for row in sheet.iter_rows():
                    if all(cell.value is None for cell in row):
                        continue
                    fila_texto = [str(cell.value) if cell.value is not None else '' for cell in row]
                    texto_completo += ' | '.join(fila_texto) + '\n'
    except Exception as e:
        flash(f"Error al leer el archivo {filepath}: {e}", "danger")
        return None
    return texto_completo.strip()


def analizar_complejidad_requerimiento(texto):
    """Analiza complejidad usando PERT y detecta criterios CA/CNF."""
    palabras = texto.split()
    conteo_palabras = len(palabras)
    
    criterios_funcionales = re.findall(
        r'\b(CA|C\.A\.|\bCriterio de Aceptaci[oó]n)[\s\-]?[–_]?(\d{1,3})\b', 
        texto, re.IGNORECASE
    )
    conteo_criterios_funcionales = len(set(criterios_funcionales))
    
    criterios_no_funcionales = re.findall(
        r'\b(CNF|C\.N\.F\.|Requerimiento No Funcional)[\s\-]?[–_]?(\d{1,3})\b',
        texto, re.IGNORECASE
    )
    conteo_criterios_no_funcionales = len(set(criterios_no_funcionales))

    nivel = "Baja"
    if conteo_palabras > 800 or conteo_criterios_funcionales > 15:
        nivel = "Alta"
    elif conteo_palabras > 300 or conteo_criterios_funcionales > 7:
        nivel = "Media"

    casos_base = conteo_criterios_funcionales * 3
    casos_no_funcionales = conteo_criterios_no_funcionales * 5
    casos_totales_estimados = casos_base + casos_no_funcionales
    if casos_totales_estimados == 0 and conteo_palabras > 50:
        casos_totales_estimados = 5 
    
    PERT_LOOKUP = {
        'Baja':  {'To': 0.1, 'Tm': 0.25, 'Tp': 0.5},
        'Media': {'To': 0.25, 'Tm': 0.5, 'Tp': 1.0},
        'Alta':  {'To': 0.5, 'Tm': 0.75, 'Tp': 1.5}
    }
    lookup = PERT_LOOKUP.get(nivel, PERT_LOOKUP['Baja'])
    To, Tm, Tp = lookup['To'], lookup['Tm'], lookup['Tp']
    tiempo_estimado_por_caso = (To + (4 * Tm) + Tp) / 6
    horas_diseño = tiempo_estimado_por_caso * casos_totales_estimados
    horas_ejecucion = tiempo_estimado_por_caso * casos_totales_estimados

    criterios_ca_lista = [f"{match[0]}-{match[1]}" for match in set(criterios_funcionales)]
    criterios_cnf_lista = [f"{match[0]}-{match[1]}" for match in set(criterios_no_funcionales)]
    
    return {
        "palabras": conteo_palabras, 
        "criterios": conteo_criterios_funcionales,
        "criterios_no_funcionales": conteo_criterios_no_funcionales, 
        "nivel": nivel,
        "casos_estimados": casos_totales_estimados,
        "horas_diseño_estimadas": horas_diseño,
        "horas_ejecucion_estimadas": horas_ejecucion,
        "criterios_ca_lista": criterios_ca_lista,
        "criterios_cnf_lista": criterios_cnf_lista,
        "pert_to": To,
        "pert_tm": Tm,
        "pert_tp": Tp,
        "tiempo_estimado_por_caso": tiempo_estimado_por_caso,
        "casos_base": casos_base,
        "casos_no_funcionales": casos_no_funcionales
    }


# ==============================================================================
# FUNCIONES DE IA (GEMINI)
# ==============================================================================

def generar_prompt_dinamico(texto_requerimiento, plantilla_obj):
    """Genera prompt dinámico basado en las columnas mapeadas."""
    mapas = plantilla_obj.mapas.all()
    if not mapas: return None 
    nombres_columnas = [mapa.etiqueta for mapa in mapas]
    col_pasos = next((col for col in nombres_columnas if 'paso' in col.lower()), None)
    col_resultados = next((col for col in nombres_columnas if 'resultado' in col.lower()), None)
    instruccion_extra_pasos = ""
    if col_pasos and col_resultados:
        instruccion_extra_pasos = (
            f"MUY IMPORTANTE: Para las columnas '{col_pasos}' y '{col_resultados}', "
            f"asegúrate de que cada paso esté en una línea separada (usando '\\n') "
            "y que haya exactamente la misma cantidad de líneas en ambas columnas. "
            "Cada línea de paso debe corresponder a una línea de resultado."
        )
    columnas_json_string = ",\n".join([f'        "{col}": "..."' for col in nombres_columnas])
    prompt = f"""
    Eres un experto en QA y pruebas de software.
    Tarea: Analiza el siguiente requerimiento de software y genera un conjunto completo de casos de prueba.
    Requerimiento:
    ---
    {texto_requerimiento}
    ---
    Instrucciones de Salida:
    1.  Tu respuesta debe ser únicamente un objeto JSON válido.
    2.  El JSON debe ser una lista de objetos, donde cada objeto es un caso de prueba.
    3.  Cada objeto (caso de prueba) debe tener EXACTAMENTE las siguientes claves (respeta mayúsculas y espacios):
    [
      {{
    {columnas_json_string}
      }}
    ]
    4.  {instruccion_extra_pasos}
    5.  Asegúrate de cubrir escenarios positivos, negativos y de borde.
    6.  No incluyas nada antes o después del JSON. Tu respuesta debe empezar con `[` y terminar con `]`.
    """
    return prompt


def llamar_api_gemini(prompt):
    """Llama a Gemini 2.0 Flash Exp para generar casos de prueba."""
    try:
        genai.configure(api_key=current_app.config['GEMINI_API_KEY'])
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        generation_config = genai.GenerationConfig(
            temperature=0.2, top_p=0.9, top_k=40,
            response_mime_type="application/json"
        )
        response = model.generate_content([prompt], generation_config=generation_config)
        texto_limpio = response.text.strip().replace("```json", "").replace("```", "")
        try:
            json_data = json.loads(texto_limpio)
            return json_data, texto_limpio
        except json.JSONDecodeError as json_err:
            print(f"Error de JSON: {json_err}")
            print(f"Texto recibido de Gemini: {texto_limpio}")
            return None, f"Error: La IA devolvió un JSON inválido. {json_err}"
    except Exception as e:
        print(f"Error en API de Gemini: {e}")
        return None, f"Error: Ocurrió un problema al contactar la API de Gemini. {e}"


# ==============================================================================
# FUNCIONES DE GENERACIÓN DE ENTREGABLES
# ==============================================================================

def _traducir_complejidad_a_numero(valor_texto):
    """Traduce texto de complejidad a número para TestLink."""
    if isinstance(valor_texto, str):
        valor_lower = valor_texto.strip().lower()
        if valor_lower == 'alta': return 1
        elif valor_lower == 'media': return 2
        elif valor_lower == 'baja': return 3
    return valor_texto


@bp.route('/generate_file/<int:view_id>/<type>')
@login_required
def generar_excel_entregable(view_id, type):
    """Genera archivos Excel o XML para descarga."""
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        flash('No tienes permiso para acceder a este recurso.', 'danger')
        return redirect(url_for('analysis.analysis_index'))
    
    plantilla_obj = analisis.plantilla_usada
    if not plantilla_obj:
        flash('No se encontró la plantilla asociada a este análisis.', 'danger')
        return redirect(url_for('analysis.analysis_index', view_id=view_id))
    
    try:
        data = json.loads(analisis.ai_result_json)
        if not data or not isinstance(data, list):
            flash('No hay datos generados por la IA para exportar.', 'warning')
            return redirect(url_for('analysis.analysis_index', view_id=view_id))
    except (json.JSONDecodeError, TypeError):
        flash('Error al leer los datos de la IA. El formato JSON es inválido.', 'danger')
        return redirect(url_for('analysis.analysis_index', view_id=view_id))
    
    mapas = plantilla_obj.mapas.all()
    if not mapas:
        flash('La plantilla no tiene columnas mapeadas.', 'danger')
        return redirect(url_for('analysis.analysis_index', view_id=view_id))

    # === GENERACIÓN DE EXCEL ===
    if type == 'excel':
        # REQ #7: CHEQUEO DE ARCHIVO FÍSICO
        plantilla_path = os.path.join(current_app.config['UPLOAD_FOLDER'], plantilla_obj.filename_seguro)
        
        if not os.path.exists(plantilla_path):
            flash(
                f'Error: El archivo de plantilla "{plantilla_obj.nombre_plantilla}" no se encuentra en el servidor. '
                'Es posible que haya sido eliminado.',
                'danger'
            )
            return redirect(url_for('analysis.analysis_index', view_id=view_id))
        
        try:
            wb = openpyxl.load_workbook(plantilla_path)
            ws = wb[plantilla_obj.sheet_name]
        except FileNotFoundError:
            flash('Error: No se pudo abrir el archivo de plantilla.', 'danger')
            return redirect(url_for('analysis.analysis_index', view_id=view_id))
        except Exception as e:
            flash(f'Error al cargar el archivo de plantilla Excel: {e}', 'danger')
            return redirect(url_for('analysis.analysis_index', view_id=view_id))

        cabeceras_mapeadas = [mapa.etiqueta for mapa in mapas]
        col_indices = {mapa.etiqueta: openpyxl.utils.column_index_from_string(mapa.coordenada) for mapa in mapas}
        fila_actual = plantilla_obj.header_row + 1
        
        # --- Lógica de Desglose de Pasos (sin cambios) ---
        if plantilla_obj.desglosar_pasos:
            etiqueta_pasos = next((c for c in cabeceras_mapeadas if 'paso' in c.lower()), None)
            etiqueta_resultados = next((c for c in cabeceras_mapeadas if 'resultado' in c.lower()), None)
            if not etiqueta_pasos or not etiqueta_resultados:
                flash('Modo "Desglosar Pasos" activado, pero no se encontraron etiquetas para "Pasos" y "Resultados".', 'warning')
            else:
                for fila_data in data: 
                    pasos = str(fila_data.get(etiqueta_pasos, '')).split('\n')
                    resultados = str(fila_data.get(etiqueta_resultados, '')).split('\n')
                    max_len = max(len(pasos), len(resultados))
                    pasos.extend([''] * (max_len - len(pasos)))
                    resultados.extend([''] * (max_len - len(resultados)))
                    
                    for i in range(max_len):
                        for col_idx_num, cabecera_actual in enumerate(cabeceras_mapeadas, 1):
                            col_letter = get_column_letter(col_idx_num) 
                            col_idx = col_indices[cabecera_actual]
                            celda = ws.cell(row=fila_actual, column=col_idx)
                            
                            if cabecera_actual == etiqueta_pasos: valor = pasos[i]
                            elif cabecera_actual == etiqueta_resultados: valor = resultados[i]
                            elif i == 0: 
                                valor = fila_data.get(cabecera_actual, '')
                                if 'importancia' in cabecera_actual.lower() or 'complejidad' in cabecera_actual.lower():
                                    valor = _traducir_complejidad_a_numero(valor)
                            else: valor = '' 
                            
                            celda.value = valor
                            celda.alignment = Alignment(wrap_text=True, vertical='top')
                            
                            import_source = fila_data.get('__import_source')
                            if import_source and col_idx == 1 and i == 0:
                                celda.comment = Comment(import_source, "Q-Vision")
                        fila_actual += 1
            
        if not plantilla_obj.desglosar_pasos or (plantilla_obj.desglosar_pasos and (not etiqueta_pasos or not etiqueta_resultados)):
            for fila in data: 
                for col_idx_num, cabecera_actual in enumerate(cabeceras_mapeadas, 1):
                    col_letter = get_column_letter(col_idx_num)
                    col_idx = col_indices[cabecera_actual]
                    celda = ws.cell(row=fila_actual, column=col_idx)
                    valor = fila.get(cabecera_actual, '')
                    
                    if 'importancia' in cabecera_actual.lower() or 'complejidad' in cabecera_actual.lower():
                        valor = _traducir_complejidad_a_numero(valor)
                    if isinstance(valor, list):
                        valor = '\n'.join(map(str, valor))

                    celda.value = valor
                    celda.alignment = Alignment(wrap_text=True, vertical='top')
                    import_source = fila.get('__import_source')
                    if import_source and col_idx == 1:
                        celda.comment = Comment(import_source, "Q-Vision")
                fila_actual += 1
        
        temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        excel_path = os.path.join(temp_dir, f'entregable_{analisis.id}.xlsx')
        wb.save(excel_path)
        
        return send_file(
            excel_path, as_attachment=True,
            download_name=f"{analisis.nombre_requerimiento or 'casos'}_generados.xlsx"
        )
    
    # === GENERACIÓN DE XML ===
    elif type == 'xml':
        cabeceras_mapeadas = [mapa.etiqueta for mapa in mapas]
        try:
            xml_string = generar_xml_entregable(data, cabeceras_mapeadas)
            temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            xml_path = os.path.join(temp_dir, f'entregable_{analisis.id}.xml')
            with open(xml_path, 'w', encoding='utf-8') as f:
                f.write(xml_string)
            return send_file(
                xml_path, as_attachment=True,
                mimetype='text/xml',
                download_name=f"{analisis.nombre_requerimiento or 'casos'}_testlink.xml"
            )
        except Exception as e:
            flash(f'Error al generar el XML: {e}', 'danger')
            return redirect(url_for('analysis.analysis_index', view_id=view_id))

    flash('Tipo de archivo no válido para generar.', 'danger')
    return redirect(url_for('analysis.analysis_index', view_id=view_id))


def generar_xml_entregable(data, cabeceras_mapeadas):
    """Genera XML compatible con TestLink."""
    def find_key(keywords):
        for key in cabeceras_mapeadas:
            if any(kw in key.lower() for kw in keywords): return key
        return None
    
    key_nombre = find_key(['nombre', 'título', 'titulo', 'name'])
    key_resumen = find_key(['resumen', 'descripción', 'descripcion', 'summary'])
    key_precondiciones = find_key(['precondicion', 'precondition'])
    key_pasos = find_key(['pasos', 'steps', 'ejecución', 'ejecucion'])
    key_resultados = find_key(['resultado', 'results', 'esperado'])
    key_importancia = find_key(['importancia', 'complejidad', 'priority'])
    
    root = ET.Element("testsuite")
    for i, caso in enumerate(data, 1):
        testcase = ET.SubElement(root, "testcase", name=caso.get(key_nombre, f"Caso de Prueba {i}"))
        summary = ET.SubElement(testcase, "summary")
        summary.text = caso.get(key_resumen, "N/A")
        preconditions = ET.SubElement(testcase, "preconditions")
        preconditions.text = caso.get(key_precondiciones, "N/A")
        
        importancia_texto = caso.get(key_importancia, "media").lower()
        if 'alta' in importancia_texto: importancia_num = "3"
        elif 'baja' in importancia_texto: importancia_num = "1"
        else: importancia_num = "2"
        importance = ET.SubElement(testcase, "importance")
        importance.text = importancia_num
        
        pasos_str = caso.get(key_pasos, "")
        resultados_str = caso.get(key_resultados, "")
        pasos_lista = str(pasos_str).split('\n') if pasos_str else ["N/A"]
        resultados_lista = str(resultados_str).split('\n') if resultados_str else ["N/A"]
        max_len = max(len(pasos_lista), len(resultados_lista))
        pasos_lista.extend([''] * (max_len - len(pasos_lista)))
        resultados_lista.extend([''] * (max_len - len(resultados_lista)))
        
        steps = ET.SubElement(testcase, "steps")
        for idx, (paso, resultado) in enumerate(zip(pasos_lista, resultados_lista), 1):
            step = ET.SubElement(steps, "step")
            step_number = ET.SubElement(step, "step_number")
            step_number.text = str(idx)
            actions = ET.SubElement(step, "actions")
            actions.text = paso if paso else " "
            expectedresults = ET.SubElement(step, "expectedresults")
            expectedresults.text = resultado if resultado else " "
            execution_type = ET.SubElement(step, "execution_type")
            execution_type.text = "1"
    
    xml_str = ET.tostring(root, encoding='utf-8', method='xml')
    dom = xml.dom.minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')


# ==============================================================================
# RUTAS PRINCIPALES
# ==============================================================================

@bp.route('/', methods=['GET', 'POST'])
@login_required
def analysis_index():
    """Ruta principal del módulo de análisis."""
    form = AnalysisForm()
    form.plantilla.choices = [
        (p.id, p.nombre_plantilla) for p in current_user.plantillas.all()
    ]
    analisis_info = None
    ai_result_data = None
    ai_result_xml_string = None
    texto_requerimiento = None
    analisis_obj = None
    
    if request.method == 'GET':
        view_id = request.args.get('view_id')
        if view_id:
            # REQ #6: Asegurar que solo se carguen análisis activos.
            analisis_obj = Analisis.query.filter_by(id=view_id, is_active=True).first()
            if analisis_obj and analisis_obj.autor == current_user:
                try:
                    ai_result_data = json.loads(analisis_obj.ai_result_json)
                    cabeceras_mapeadas = [m.etiqueta for m in analisis_obj.plantilla_usada.mapas]
                    ai_result_xml_string = generar_xml_entregable(ai_result_data, cabeceras_mapeadas)
                except (json.JSONDecodeError, TypeError):
                    ai_result_data = None
                    flash('El JSON guardado está corrupto.', 'danger')
                except Exception as e:
                    ai_result_xml_string = f"Error al generar XML: {e}"

                datos_completos = analizar_complejidad_requerimiento(analisis_obj.texto_requerimiento_raw)
                
                analisis_info = {
                    'nivel': analisis_obj.nivel_complejidad, 
                    'casos': analisis_obj.casos_generados,
                    'criterios': analisis_obj.criterios_detectados,
                    'criterios_no_funcionales': analisis_obj.criterios_no_funcionales,
                    'palabras': analisis_obj.palabras_analizadas,
                    'horas_diseno': analisis_obj.horas_diseño_estimadas,
                    'horas_ejecucion': analisis_obj.horas_ejecucion_estimadas,
                    'criterios_ca_lista': datos_completos.get('criterios_ca_lista', []),
                    'criterios_cnf_lista': datos_completos.get('criterios_cnf_lista', []),
                    'pert_to': datos_completos.get('pert_to', 0),
                    'pert_tm': datos_completos.get('pert_tm', 0),
                    'pert_tp': datos_completos.get('pert_tp', 0),
                    'tiempo_estimado_por_caso': datos_completos.get('tiempo_estimado_por_caso', 0),
                    'casos_base': datos_completos.get('casos_base', 0),
                    'casos_no_funcionales': datos_completos.get('casos_no_funcionales', 0)
                }
                texto_requerimiento = analisis_obj.texto_requerimiento_raw
            elif not analisis_obj:
                flash('Este análisis ya no existe o fue eliminado.', 'warning')
                return redirect(url_for('analysis.analysis_index'))
            else:
                flash('No tienes permiso para ver este análisis.', 'danger')
                return redirect(url_for('analysis.analysis_index'))
    
    if form.validate_on_submit():
        archivo = form.archivo_requerimiento.data
        plantilla_id = form.plantilla.data
        plantilla_obj = Plantilla.query.get(plantilla_id)
        if not plantilla_obj:
            flash('Plantilla no válida.', 'danger')
            return redirect(url_for('analysis.analysis_index'))

        filename = secure_filename(archivo.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        archivo.save(filepath)
        texto_requerimiento = leer_requerimiento(filepath)
        
        if texto_requerimiento is None:
            os.remove(filepath) 
            return redirect(url_for('analysis.analysis_index'))
        
        # REQ #4: Validación de Duplicados
        existing = Analisis.query.filter_by(
            id_usuario=current_user.id,
            texto_requerimiento_raw=texto_requerimiento,
            id_plantilla=plantilla_id, 
            is_active=True
        ).first()
        if existing:
            flash('Ya existe un análisis con este mismo requerimiento y plantilla. Cargando el análisis existente.', 'info')
            os.remove(filepath) 
            return redirect(url_for('analysis.analysis_index', view_id=existing.id))
        
        os.remove(filepath) 
        
        analisis_info = analizar_complejidad_requerimiento(texto_requerimiento)
        prompt = generar_prompt_dinamico(texto_requerimiento, plantilla_obj)
        if prompt is None:
            flash('La plantilla seleccionada no tiene columnas mapeadas.', 'danger')
            return redirect(url_for('analysis.analysis_index'))
        
        ai_result_data, ai_result_raw = llamar_api_gemini(prompt)
        
        if ai_result_data is None:
            flash(f"Error de la IA: {ai_result_raw}", 'danger')
            return redirect(url_for('analysis.analysis_index'))
        
        try:
            casos_generados = len(ai_result_data)
            nuevo_analisis = Analisis(
                id_usuario=current_user.id, id_plantilla=plantilla_obj.id,
                nombre_requerimiento=archivo.filename,
                texto_requerimiento_raw=texto_requerimiento,
                nivel_complejidad=analisis_info['nivel'],
                casos_generados=casos_generados,
                criterios_detectados=analisis_info['criterios'],
                criterios_no_funcionales=analisis_info['criterios_no_funcionales'],
                palabras_analizadas=analisis_info['palabras'],
                horas_diseño_estimadas=analisis_info['horas_diseño_estimadas'],
                horas_ejecucion_estimadas=analisis_info['horas_ejecucion_estimadas'],
                ai_result_json=ai_result_raw, is_active=True
            )
            db.session.add(nuevo_analisis)
            db.session.commit()
            flash(f'¡Análisis completado! Se generaron {casos_generados} casos.', 'success')
            return redirect(url_for('analysis.analysis_index', view_id=nuevo_analisis.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar en la base de datos: {e}', 'danger')

    historial_analisis = current_user.analisis_historial.filter_by(is_active=True).order_by(Analisis.timestamp.desc()).all()

    return render_template('analysis/analysis.html', 
                           title='Análisis de Requerimientos',
                           form=form,
                           analisis_info=analisis_info,
                           ai_result_data=ai_result_data,
                           ai_result_xml_string=ai_result_xml_string,
                           texto_requerimiento=texto_requerimiento,
                           analisis_obj=analisis_obj,
                           historial_analisis=historial_analisis)


@bp.route('/re_analyze/<int:view_id>', methods=['POST'])
@login_required
def re_analyze(view_id):
    """Re-analiza un requerimiento modificado."""
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        flash('No tienes permiso.', 'danger')
        return redirect(url_for('analysis.analysis_index'))
    
    texto_requerimiento_modificado = request.form.get('texto_requerimiento')
    if not texto_requerimiento_modificado:
        flash('El texto del requerimiento no puede estar vacío.', 'warning')
        return redirect(url_for('analysis.analysis_index', view_id=view_id))
    
    try:
        historial = HistorialCambios(
            id_analisis=analisis.id, id_usuario=current_user.id,
            tipo_cambio="REQUERIMIENTO_MODIFICADO",
            datos_json_antiguos=analisis.ai_result_json
        )
        db.session.add(historial)
    except Exception as e:
        flash(f'Error al guardar en el historial: {e}', 'warning')
    
    plantilla_obj = analisis.plantilla_usada
    analisis_info = analizar_complejidad_requerimiento(texto_requerimiento_modificado)
    prompt = generar_prompt_dinamico(texto_requerimiento_modificado, plantilla_obj)
    ai_result_data, ai_result_raw = llamar_api_gemini(prompt)
    
    if ai_result_data is None:
        flash(f"Error de la IA al re-analizar: {ai_result_raw}", 'danger')
        return redirect(url_for('analysis.analysis_index', view_id=view_id))
    
    try:
        casos_generados = len(ai_result_data)
        analisis.texto_requerimiento_raw = texto_requerimiento_modificado
        analisis.nivel_complejidad = analisis_info['nivel']
        analisis.casos_generados = casos_generados
        analisis.criterios_detectados = analisis_info['criterios']
        analisis.criterios_no_funcionales = analisis_info['criterios_no_funcionales']
        analisis.palabras_analizadas = analisis_info['palabras']
        analisis.horas_diseño_estimadas = analisis_info['horas_diseño_estimadas']
        analisis.horas_ejecucion_estimadas = analisis_info['horas_ejecucion_estimadas']
        analisis.ai_result_json = ai_result_raw
        analisis.timestamp = db.func.now() 
        db.session.commit()
        flash(f'¡Re-análisis completado! Se generaron {casos_generados} nuevos casos.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el análisis: {e}', 'danger')

    return redirect(url_for('analysis.analysis_index', view_id=view_id))


@bp.route('/delete_analysis/<int:view_id>', methods=['POST'])
@login_required
def delete_analysis(view_id):
    """Elimina un análisis (soft delete)."""
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        flash('No tienes permiso para eliminar este análisis.', 'danger')
        return redirect(url_for('analysis.analysis_index'))
    try:
        analisis.is_active = False
        db.session.commit()
        flash('Análisis movido al historial (oculto).', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el análisis: {e}', 'danger')
    
    # REQ #6: Forzar redirect para actualizar UI
    return redirect(url_for('analysis.analysis_index'))


@bp.route('/clear_analysis', methods=['POST'])
@login_required
def clear_analysis():
    """Limpia el análisis actual."""
    return redirect(url_for('analysis.analysis_index'))


@bp.route('/update_results/<int:view_id>', methods=['POST'])
@login_required
def update_results(view_id):
    """Actualiza los resultados de un análisis vía AJAX."""
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        return jsonify({'status': 'error', 'message': 'Permiso denegado'}), 403
    
    new_data = request.get_json()
    if not isinstance(new_data, list):
        return jsonify({'status': 'error', 'message': 'Datos inválidos. Se esperaba una lista.'}), 400
    
    try:
        historial = HistorialCambios(
            id_analisis=analisis.id, id_usuario=current_user.id,
            tipo_cambio="CASOS_MODIFICADOS",
            datos_json_antiguos=analisis.ai_result_json
        )
        db.session.add(historial)
        analisis.ai_result_json = json.dumps(new_data, indent=4)
        analisis.casos_generados = len(new_data)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': f'¡Casos guardados! Se actualizaron {len(new_data)} casos.',
            'casos': len(new_data)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Error al guardar en la BD: {e}'}), 500


# ==============================================================================
# REQ #3: API PARA OBTENER INFORMACIÓN DE PLANTILLA
# ==============================================================================
@bp.route('/api/plantilla/<int:plantilla_id>/info', methods=['GET'])
@login_required
def get_plantilla_info(plantilla_id):
    """Endpoint AJAX para obtener información detallada de una plantilla."""
    from app.models import Plantilla, MapaPlantilla
    
    plantilla = Plantilla.query.get_or_404(plantilla_id)
    
    if plantilla.autor != current_user:
        return jsonify({
            'success': False,
            'error': 'No tienes permiso para ver esta plantilla'
        }), 403
    
    mapas = plantilla.mapas.all()
    
    plantilla_data = {
        'id': plantilla.id,
        'nombre': plantilla.nombre_plantilla,
        'tipo_archivo': plantilla.tipo_archivo.upper() if plantilla.tipo_archivo else 'N/A',
        'sheet_name': plantilla.sheet_name or 'N/A',
        'header_row': plantilla.header_row or 1,
        'desglosar_pasos': plantilla.desglosar_pasos,
        'timestamp': plantilla.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'total_mapas': len(mapas)
    }
    
    mapas_data = [
        {
            'etiqueta': mapa.etiqueta,
            'coordenada': mapa.coordenada,
            'tipo_mapa': mapa.tipo_mapa
        }
        for mapa in mapas
    ]
    
    return jsonify({
        'success': True,
        'plantilla': plantilla_data,
        'mapas': mapas_data
    })


# ==============================================================================
# REQ #5: API PARA OBTENER HISTORIAL DE CAMBIOS
# ==============================================================================
@bp.route('/api/historial/<int:analisis_id>', methods=['GET'])
@login_required
def get_historial_cambios(analisis_id):
    """Endpoint AJAX para obtener el historial de cambios de un análisis."""
    try:
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
        tipo_filtro = request.args.get('tipo', None)
        
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        if offset < 0:
            offset = 0
    except ValueError:
        return jsonify({'success': False, 'error': 'Parámetros inválidos'}), 400
    
    analisis = Analisis.query.get_or_404(analisis_id)
    
    if analisis.autor != current_user:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    from app.models import Usuario
    query = HistorialCambios.query.join(Usuario).filter(
        HistorialCambios.id_analisis == analisis_id
    )
    
    if tipo_filtro:
        query = query.filter(HistorialCambios.tipo_cambio == tipo_filtro)
    
    total_cambios = query.count()
    
    historial = query.order_by(
        HistorialCambios.timestamp.desc()
    ).limit(limit).offset(offset).all()
    
    cambios_data = []
    for h in historial:
        preview_json = None
        if h.datos_json_antiguos:
            preview_json = h.datos_json_antiguos[:200]
            if len(h.datos_json_antiguos) > 200:
                preview_json += '...'
        
        tipo_badge = {
            'REQUERIMIENTO_MODIFICADO': 'warning',
            'CASOS_MODIFICADOS': 'info',
            'PLANTILLA_CAMBIADA': 'secondary',
            'RE_ANALISIS': 'primary'
        }.get(h.tipo_cambio, 'secondary')
        
        cambios_data.append({
            'id': h.id,
            'fecha': h.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_relativa': calcular_tiempo_relativo(h.timestamp),
            'usuario': h.autor.email,
            'tipo_cambio': h.tipo_cambio,
            'tipo_badge': tipo_badge,
            'tiene_json_backup': h.datos_json_antiguos is not None,
            'preview_json': preview_json,
            'tamano_json': len(h.datos_json_antiguos) if h.datos_json_antiguos else 0
        })
    
    analisis_data = {
        'id': analisis.id,
        'nombre': analisis.nombre_requerimiento,
        'timestamp': analisis.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'casos_generados': analisis.casos_generados,
        'nivel_complejidad': analisis.nivel_complejidad
    }
    
    return jsonify({
        'success': True,
        'analisis': analisis_data,
        'total_cambios': total_cambios,
        'cambios': cambios_data,
        'paginacion': {
            'limit': limit,
            'offset': offset,
            'tiene_mas': (offset + limit) < total_cambios,
            'pagina_actual': (offset // limit) + 1,
            'total_paginas': (total_cambios + limit - 1) // limit
        }
    })


@bp.route('/api/historial/<int:historial_id>/json', methods=['GET'])
@login_required
def get_historial_json_completo(historial_id):
    """Endpoint para obtener el JSON completo de un cambio específico."""
    historial = HistorialCambios.query.get_or_404(historial_id)
    
    if historial.analisis.autor != current_user:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    try:
        if historial.datos_json_antiguos:
            json_data = json.loads(historial.datos_json_antiguos)
        else:
            json_data = None
    except json.JSONDecodeError:
        json_data = historial.datos_json_antiguos
    
    return jsonify({
        'success': True,
        'historial_id': historial.id,
        'tipo_cambio': historial.tipo_cambio,
        'fecha': historial.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'json_backup': json_data
    })


def calcular_tiempo_relativo(timestamp):
    """Convierte timestamp en representación legible de tiempo relativo."""
    from datetime import datetime, timezone
    
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    
    ahora = datetime.now(timezone.utc)
    diferencia = ahora - timestamp
    segundos = diferencia.total_seconds()
    
    if segundos < 60:
        return "hace un momento"
    elif segundos < 3600:
        minutos = int(segundos / 60)
        return f"hace {minutos} {'minuto' if minutos == 1 else 'minutos'}"
    elif segundos < 86400:
        horas = int(segundos / 3600)
        return f"hace {horas} {'hora' if horas == 1 else 'horas'}"
    elif segundos < 604800:
        dias = int(segundos / 86400)
        return f"hace {dias} {'día' if dias == 1 else 'días'}"
    elif segundos < 2592000:
        semanas = int(segundos / 604800)
        return f"hace {semanas} {'semana' if semanas == 1 else 'semanas'}"
    else:
        return timestamp.strftime('%d/%m/%Y')