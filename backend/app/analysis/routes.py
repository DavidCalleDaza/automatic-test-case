import os
import io
import openpyxl
import xml.etree.ElementTree as ET
from xml.dom import minidom
from flask import (
    render_template, flash, redirect, url_for, request,
    current_app, session, jsonify, send_file
)
from flask_login import current_user, login_required
from app import db
from app.analysis import bp
from app.analysis.forms import AnalysisForm
from app.models import Plantilla, Analisis
from werkzeug.utils import secure_filename
import docx
import json
import google.generativeai as genai
import re

# --- CONFIGURACIÓN DE IA ---
try:
    genai.configure(api_key=os.environ.get('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except Exception as e:
    print(f"Error configurando Gemini: {e}")
    model = None

# --- FUNCIONES HELPERS ---
ALLOWED_EXTENSIONS = {'txt', 'docx', 'md', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def leer_requerimiento(filepath):
    """
    Lee el contenido de un archivo .txt, .docx, o .xlsx.
    Para Excel, extrae texto de todas las hojas y celdas.
    """
    extension = filepath.rsplit('.', 1)[1].lower()
    full_text = []

    try:
        if extension == 'docx':
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                full_text.append(para.text)

        elif extension == 'xlsx':
            workbook = openpyxl.load_workbook(filepath, data_only=True)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                full_text.append(f"\n--- INICIO HOJA: {sheet_name} ---\n")
                for row in sheet.iter_rows():
                    row_text = []
                    for cell in row:
                        if cell.value is not None:
                            row_text.append(str(cell.value))
                    if row_text:
                        full_text.append(" | ".join(row_text))
            workbook.close()

        else: # 'txt', 'md', o default
            with open(filepath, 'r', encoding='utf-8') as f:
                full_text.append(f.read())
                
    except Exception as e:
        print(f"Error al leer el archivo {filepath}: {str(e)}")
        return f"Error al procesar el archivo: {str(e)}"

    return '\n'.join(full_text)


def limpiar_json_string(s):
    """Limpia el string de respuesta de la IA."""
    try:
        start = s.index('[')
        end = s.rindex(']') + 1
        json_str = s[start:end]
        json_str = json_str.replace('\n', '')
        json_str = json_str.replace('\\n', '\\n')
        return json_str
    except ValueError:
        print("Error: No se encontró '[' o ']' en la respuesta de la IA.")
        return s

def analizar_complejidad_requerimiento(texto):
    """
    Analiza el texto y devuelve métricas.
    Añadido contador para Criterios No Funcionales (CNF).
    """
    palabras = texto.split()
    num_palabras = len(palabras)
    texto_lower = texto.lower()
    
    # --- Conteo de Criterios Funcionales (CA) ---
    criterios_keywords = texto_lower.count('criterio de aceptac')
    criterios_keywords += texto_lower.count('regla de negocio')
    criterios_keywords += texto_lower.count('posibles errores')
    criterios_keywords += texto_lower.count('escenario:')
    
    gherkin_count = 0
    gherkin_keywords = ['dado', 'cuando', 'entonces']
    for p in palabras:
        if p.lower().strip().rstrip(':') in gherkin_keywords:
            gherkin_count += 1
    
    criterios_patron = re.findall(r'ca[\s_-]?\d+', texto_lower, re.IGNORECASE)
    patron_count_ca = len(criterios_patron)
    criterios_funcionales = max(patron_count_ca, (criterios_keywords + gherkin_count))

    # --- Conteo de Criterios No Funcionales (CNF) ---
    cnf_patron = re.findall(r'cnf[\s_-]?\d+', texto_lower, re.IGNORECASE)
    patron_count_cnf = len(cnf_patron)
    cnf_keywords = texto_lower.count('criterio no funcional')
    criterios_no_funcionales = max(patron_count_cnf, cnf_keywords)
    
    # --- Conteo General ---
    criterios_totales = criterios_funcionales + criterios_no_funcionales
    num_hojas = texto_lower.count('--- inicio hoja:')
    
    num_casos = 5
    complejidad = "Baja"
    horas_diseño = 2
    horas_ejecucion = 2

    if num_palabras > 800 or criterios_totales > 15 or num_hojas > 3:
        complejidad = "Alta"
        num_casos = 25
        horas_diseño = 8
        horas_ejecucion = 8
    elif num_palabras > 300 or criterios_totales > 7 or num_hojas > 1:
        complejidad = "Media"
        num_casos = 12
        horas_diseño = 4
        horas_ejecucion = 4
    
    if criterios_funcionales == 0 and num_palabras > 50:
         criterios_funcionales = 1 # Asumir al menos 1

    return {
        "nivel": complejidad,
        "casos_sugeridos": num_casos,
        "criterios": criterios_funcionales,
        "criterios_no_funcionales": criterios_no_funcionales,
        "palabras": num_palabras,
        "horas_diseño_estimadas": horas_diseño,
        "horas_ejecucion_estimadas": horas_ejecucion
    }

# --- FUNCIÓN (PROMPT 1:1) ---
def generar_prompt_dinamico(texto_req, plantilla_obj, metricas):
    """Construye el prompt para la IA basado en la plantilla."""
    
    mapas = plantilla_obj.mapas.all()
    etiquetas = [m.etiqueta for m in mapas]
    
    if not etiquetas:
        return None

    etiquetas_str = ", ".join([f'"{e}"' for e in etiquetas])

    pasos_field = None
    resultado_field = None
    
    for e in etiquetas:
        if 'paso' in e.lower():
            pasos_field = e
        if 'resultado' in e.lower():
            resultado_field = e
            
    prompt_base = f"""
    Eres un experto QA Senior especializado en diseño de casos de prueba.
    Analiza el siguiente requerimiento y genera EXACTAMENTE {metricas['casos_sugeridos']} casos de prueba.
    Enfócate en los Criterios de Aceptación Funcionales (CA).

    REQUERIMIENTO:
    ---
    {texto_req}
    ---

    RESPONDE ÚNICAMENTE con un array JSON. Cada objeto debe tener las siguientes llaves: {etiquetas_str}.
    """
    
    if pasos_field and resultado_field:
        prompt_especifico = f"""
        MUY IMPORTANTE: Para los campos "{pasos_field}" y "{resultado_field}":
        1.  Genera múltiples pasos y resultados.
        2.  Ambos campos deben ser un solo string.
        3.  Usa el caracter de salto de línea (\\n) para separar cada paso y cada resultado.
        4.  DEBE haber exactamente la misma cantidad de saltos de línea en "{pasos_field}" que en "{resultado_field}".
        5.  Cada línea en "{pasos_field}" debe corresponder 1:1 con su línea en "{resultado_field}".

        Ejemplo de formato para esos campos:
        "{pasos_field}": "1. Hacer clic en Login\\n2. Ingresar 'user'\\n3. Ingresar 'pass'\\n4. Hacer clic en 'Entrar'",
        "{resultado_field}": "1. El sistema muestra la modal de login\\n2. El campo 'usuario' se rellena\\n3. El campo 'password' se rellena\\n4. El sistema redirige al dashboard"
        """
        prompt = prompt_base + prompt_especifico
    else:
        prompt = prompt_base + "\nGenera los casos de prueba."

    return prompt

# --- FUNCIÓN (Excel sin Merge) ---
def generar_excel_entregable(analisis_obj):
    """
    Genera el archivo Excel basado en el análisis y su plantilla.
    ¡ACTUALIZADO para manejar el desglose de TestLink (sin merge)!
    """
    plantilla_obj = analisis_obj.plantilla_usada
    mapas = plantilla_obj.mapas.all()
    
    try:
        casos_ia = json.loads(analisis_obj.ai_result_json)
        if not isinstance(casos_ia, list):
            raise ValueError("El JSON no es una lista")
    except Exception as e:
        print(f"Error al parsear JSON para Excel: {e}")
        return None

    try:
        path_plantilla = os.path.join(
            current_app.config['UPLOAD_FOLDER'], 
            plantilla_obj.filename_seguro
        )
        workbook = openpyxl.load_workbook(path_plantilla)
        sheet = workbook[plantilla_obj.sheet_name]
    except Exception as e:
        print(f"Error al cargar la plantilla Excel: {e}")
        return None

    fila_actual = plantilla_obj.header_row + 1

    pasos_field = None
    resultado_field = None
    mapa_coordenadas = {}
    
    for m in mapas:
        mapa_coordenadas[m.etiqueta] = m.coordenada
        if 'paso' in m.etiqueta.lower():
            pasos_field = m.etiqueta
        if 'resultado' in m.etiqueta.lower():
            resultado_field = m.etiqueta

    desglosar_para_testlink = plantilla_obj.desglosar_pasos and pasos_field and resultado_field

    for caso in casos_ia:
        
        if desglosar_para_testlink:
            try:
                pasos_list = caso.get(pasos_field, "").split('\n')
                resultados_list = caso.get(resultado_field, "").split('\n')
                
                num_pasos = max(len(pasos_list), len(resultados_list))
                
                pasos_list.extend([''] * (num_pasos - len(pasos_list)))
                resultados_list.extend([''] * (num_pasos - len(resultados_list)))

                for i in range(num_pasos):
                    paso_actual = pasos_list[i]
                    resultado_actual = resultados_list[i]

                    for etiqueta, col in mapa_coordenadas.items():
                        celda = f"{col}{fila_actual}"
                        
                        if etiqueta == pasos_field:
                            sheet[celda] = paso_actual
                        elif etiqueta == resultado_field:
                            sheet[celda] = resultado_actual
                        else:
                            sheet[celda] = caso.get(etiqueta, "")
                    
                    fila_actual += 1
                    
            except Exception as e:
                print(f"Error al desglosar pasos: {e}")
                for etiqueta, col in mapa_coordenadas.items():
                    sheet[f"{col}{fila_actual}"] = caso.get(etiqueta, "")
                fila_actual += 1
        
        else:
            for etiqueta, col in mapa_coordenadas.items():
                sheet[f"{col}{fila_actual}"] = caso.get(etiqueta, "")
            fila_actual += 1
            
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    workbook.close()
    
    return output

# --- FUNCIÓN (Requerimiento XML) ---
def generar_xml_entregable(analisis_obj):
    """
    Genera un archivo XML con los casos de prueba (formato TestLink).
    """
    try:
        casos_ia = json.loads(analisis_obj.ai_result_json)
        if not isinstance(casos_ia, list) or not casos_ia:
            raise ValueError("El JSON no es una lista válida o está vacío")
    except Exception as e:
        print(f"Error al parsear JSON para XML: {e}")
        return None

    id_field = next((k for k in casos_ia[0] if 'id' in k.lower()), 'ID_CASO')
    titulo_field = next((k for k in casos_ia[0] if 'titulo' in k.lower() or 'nombre' in k.lower()), 'TITULO_CASO')
    pasos_field = next((k for k in casos_ia[0] if 'paso' in k.lower()), 'PASOS_EJECUCION')
    resultado_field = next((k for k in casos_ia[0] if 'resultado' in k.lower()), 'RESULTADOS_ESPERADOS')
    precond_field = next((k for k in casos_ia[0] if 'precond' in k.lower()), 'PRECONDICIONES')
    resumen_field = next((k for k in casos_ia[0] if 'resumen' in k.lower() or 'descrip' in k.lower()), 'RESUMEN')

    root = ET.Element("testsuite")
    
    for caso in casos_ia:
        testcase = ET.SubElement(root, "testcase", name=caso.get(titulo_field, "Caso sin título"))
        
        name_node = ET.SubElement(testcase, "name")
        name_node.text = caso.get(titulo_field, "Caso sin título")
        
        summary = ET.SubElement(testcase, "summary")
        summary.text = f"<![CDATA[{caso.get(resumen_field, '')}]]>"
        
        preconditions = ET.SubElement(testcase, "preconditions")
        preconditions.text = f"<![CDATA[{caso.get(precond_field, '')}]]>"
        
        externalid = ET.SubElement(testcase, "externalid")
        externalid.text = caso.get(id_field, "")

        steps = ET.SubElement(testcase, "steps")
        
        pasos_list = caso.get(pasos_field, "").split('\n')
        resultados_list = caso.get(resultado_field, "").split('\n')
        num_pasos = max(len(pasos_list), len(resultados_list))
        pasos_list.extend([''] * (num_pasos - len(pasos_list)))
        resultados_list.extend([''] * (num_pasos - len(resultados_list)))

        for i in range(num_pasos):
            if not pasos_list[i]: continue
            
            step = ET.SubElement(steps, "step")
            
            step_number = ET.SubElement(step, "step_number")
            step_number.text = str(i + 1)
            
            actions = ET.SubElement(step, "actions")
            actions.text = f"<![CDATA[{pasos_list[i]}]]>"
            
            expectedresults = ET.SubElement(step, "expectedresults")
            expectedresults.text = f"<![CDATA[{resultados_list[i]}]]>"
            
            execution_type = ET.SubElement(step, "execution_type")
            execution_type.text = "1"
    
    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    output = io.BytesIO(pretty_xml)
    output.seek(0)
    
    return output

# --- RUTAS ---

@bp.route('/', methods=['GET', 'POST'])
@login_required
def analysis_index():
    form = AnalysisForm()
    form.plantilla.choices = [
        (p.id, p.nombre_plantilla) for p in Plantilla.query.filter_by(
            autor=current_user
        ).order_by(Plantilla.nombre_plantilla).all()
    ]

    analisis_obj = None
    ai_result_data = None
    ai_result_raw = None
    texto_requerimiento = None
    analisis_info = None
    ai_result_xml_string = None 

    # --- Lógica POST (Nuevo Análisis) ---
    if form.validate_on_submit():
        archivo = form.archivo_requerimiento.data
        plantilla_id = form.plantilla.data
        plantilla_obj = Plantilla.query.get_or_404(plantilla_id)

        if archivo and allowed_file(archivo.filename):
            filename = secure_filename(archivo.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            archivo.save(upload_path)
            
            texto_req = leer_requerimiento(upload_path)
            metricas = analizar_complejidad_requerimiento(texto_req)
            prompt = generar_prompt_dinamico(texto_req, plantilla_obj, metricas)
            
            if not model or not prompt:
                flash("Error: No se pudo inicializar el modelo de IA o la plantilla no está mapeada.", "danger")
                return redirect(url_for('analysis.analysis_index'))

            try:
                respuesta = model.generate_content(prompt)
                respuesta_ia_raw = respuesta.text
                respuesta_ia_json = limpiar_json_string(respuesta_ia_raw)
                
                # --- ¡INICIO DE LA ACTUALIZACIÓN (Guardar Estimaciones)! ---
                nuevo_analisis = Analisis(
                    autor=current_user,
                    plantilla_usada=plantilla_obj,
                    nombre_requerimiento=filename,
                    texto_requerimiento_raw=texto_req,
                    nivel_complejidad=metricas["nivel"],
                    casos_generados=metricas["casos_sugeridos"],
                    criterios_detectados=metricas["criterios"],
                    criterios_no_funcionales=metricas["criterios_no_funcionales"],
                    palabras_analizadas=metricas["palabras"],
                    horas_diseño_estimadas=metricas["horas_diseño_estimadas"], # ¡NUEVO!
                    horas_ejecucion_estimadas=metricas["horas_ejecucion_estimadas"], # ¡NUEVO!
                    ai_result_json=respuesta_ia_json
                )
                # --- FIN DE LA ACTUALIZACIÓN ---
                
                db.session.add(nuevo_analisis)
                db.session.commit()
                
                flash("¡Análisis completado exitosamente!", "success")
                return redirect(url_for('analysis.analysis_index', view_id=nuevo_analisis.id))
                
            except Exception as e:
                flash(f"Error al generar contenido de IA: {str(e)}", "danger")
                print(f"RESPUESTA IA (RAW): {respuesta.text if 'respuesta' in locals() else 'N/A'}")

        else:
            flash("Tipo de archivo no permitido.", "warning")

    # --- Lógica GET (Ver Historial) ---
    view_id = request.args.get('view_id', type=int)
    if view_id:
        analisis_obj = Analisis.query.get_or_404(view_id)
        
        if analisis_obj.autor != current_user:
            flash("Acceso no autorizado.", "danger")
            return redirect(url_for('analysis.analysis_index'))
            
        texto_requerimiento = analisis_obj.texto_requerimiento_raw
        ai_result_raw = analisis_obj.ai_result_json
        
        # --- ¡INICIO DE LA ACTUALIZACIÓN (Mostrar Estimaciones)! ---
        analisis_info = {
            "nivel": analisis_obj.nivel_complejidad,
            "casos": analisis_obj.casos_generados,
            "criterios": analisis_obj.criterios_detectados,
            "criterios_no_funcionales": analisis_obj.criterios_no_funcionales,
            "palabras": analisis_obj.palabras_analizadas,
            "horas_diseño": analisis_obj.horas_diseño_estimadas, # ¡NUEVO!
            "horas_ejecucion": analisis_obj.horas_ejecucion_estimadas # ¡NUEVO!
        }
        # --- FIN DE LA ACTUALIZACIÓN ---
        
        try:
            ai_result_data = json.loads(ai_result_raw)
            
            xml_output_io = generar_xml_entregable(analisis_obj)
            if xml_output_io:
                ai_result_xml_string = xml_output_io.getvalue().decode('utf-8')
                
        except json.JSONDecodeError:
            ai_result_data = None
            flash("Error al decodificar el JSON de la IA. Mostrando datos crudos.", "warning")

    historial_analisis = Analisis.query.filter_by(
        autor=current_user
    ).order_by(Analisis.timestamp.desc()).limit(20).all()

    return render_template(
        'analysis/analysis.html',
        title='Análisis de Requerimientos',
        form=form,
        historial_analisis=historial_analisis,
        analisis_obj=analisis_obj,
        ai_result_data=ai_result_data,
        ai_result_raw=ai_result_raw,
        ai_result_xml_string=ai_result_xml_string,
        texto_requerimiento=texto_requerimiento,
        analisis_info=analisis_info
    )

# --- Ruta de Re-Análisis ---
@bp.route('/re-analyze/<int:view_id>', methods=['POST'])
@login_required
def re_analyze(view_id):
    analisis_obj = Analisis.query.get_or_404(view_id)
    if analisis_obj.autor != current_user:
        flash("Acceso no autorizado.", "danger")
        return redirect(url_for('analysis.analysis_index'))
    
    texto_req = request.form.get('texto_requerimiento')
    if not texto_req:
        flash("No se proporcionó texto para re-analizar.", "warning")
        return redirect(url_for('analysis.analysis_index', view_id=view_id))
        
    plantilla_obj = analisis_obj.plantilla_usada
    
    metricas = analizar_complejidad_requerimiento(texto_req)
    prompt = generar_prompt_dinamico(texto_req, plantilla_obj, metricas)
    
    if not model or not prompt:
        flash("Error: No se pudo inicializar el modelo de IA o la plantilla no está mapeada.", "danger")
        return redirect(url_for('analysis.analysis_index', view_id=view_id))

    try:
        respuesta = model.generate_content(prompt)
        respuesta_ia_raw = respuesta.text
        respuesta_ia_json = limpiar_json_string(respuesta_ia_raw)
        
        # --- ¡INICIO DE LA ACTUALIZACIÓN (Guardar Estimaciones)! ---
        analisis_obj.texto_requerimiento_raw = texto_req
        analisis_obj.nivel_complejidad = metricas["nivel"]
        analisis_obj.casos_generados = metricas["casos_sugeridos"]
        analisis_obj.criterios_detectados = metricas["criterios"]
        analisis_obj.criterios_no_funcionales = metricas["criterios_no_funcionales"]
        analisis_obj.palabras_analizadas = metricas["palabras"]
        analisis_obj.horas_diseño_estimadas = metricas["horas_diseño_estimadas"] # ¡NUEVO!
        analisis_obj.horas_ejecucion_estimadas = metricas["horas_ejecucion_estimadas"] # ¡NUEVO!
        analisis_obj.ai_result_json = respuesta_ia_json
        # --- FIN DE LA ACTUALIZACIÓN ---
        
        db.session.commit()
        
        flash("¡Re-análisis completado exitosamente!", "success")
        
    except Exception as e:
        flash(f"Error al generar contenido de IA: {str(e)}", "danger")
        print(f"RESPUESTA IA (RAW): {respuesta.text if 'respuesta' in locals() else 'N/A'}")

    return redirect(url_for('analysis.analysis_index', view_id=view_id))

# --- Rutas de Borrado ---
@bp.route('/delete-analysis/<int:view_id>', methods=['POST'])
@login_required
def delete_analysis(view_id):
    analisis_obj = Analisis.query.filter_by(id=view_id, autor=current_user).first_or_404()
    try:
        db.session.delete(analisis_obj)
        db.session.commit()
        flash("Análisis eliminado.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar: {str(e)}", "danger")
    return redirect(url_for('analysis.analysis_index'))

@bp.route('/clear-analysis', methods=['POST'])
@login_required
def clear_analysis():
    return redirect(url_for('analysis.analysis_index'))

# --- RUTA DE DESCARGA ---
@bp.route('/generate-file/<int:view_id>')
@login_required
def generate_file(view_id):
    analisis_obj = Analisis.query.filter_by(id=view_id, autor=current_user).first_or_404()
    
    file_type = request.args.get('type', 'excel')
    
    if file_type == 'excel':
        output = generar_excel_entregable(analisis_obj)
        if output is None:
            flash("Error al generar el archivo Excel.", "danger")
            return redirect(url_for('analysis.analysis_index', view_id=view_id))
        
        filename = f"Analisis_{view_id}_{analisis_obj.plantilla_usada.nombre_plantilla}.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    elif file_type == 'xml':
        output = generar_xml_entregable(analisis_obj)
        if output is None:
            flash("Error al generar el archivo XML.", "danger")
            return redirect(url_for('analysis.analysis_index', view_id=view_id))
            
        filename = f"Analisis_{view_id}_TestLink.xml"
        mimetype = "application/xml"
        
    else:
        flash("Tipo de archivo no válido.", "danger")
        return redirect(url_for('analysis.analysis_index', view_id=view_id))

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )