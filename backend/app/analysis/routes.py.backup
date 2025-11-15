import os
import json
import openpyxl
import docx
import re
import xml.etree.ElementTree as ET
import xml.dom.minidom
import google.generativeai as genai
from openpyxl.comments import Comment
from flask import (
    render_template,
    flash,
    redirect,
    url_for,
    request,
    session,
    jsonify,
    send_file,
    current_app,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from openpyxl.styles import Alignment
from app import db
from app.analysis import bp
from app.analysis.forms import AnalysisForm
from app.models import Usuario, Plantilla, MapaPlantilla, Analisis, AnalisisDato

# --- Funciones de Ayuda: Lectura y Métricas ---


def leer_requerimiento(filepath):
    """
    Lee el contenido de un archivo (.txt, .docx, .xlsx) y lo devuelve como texto.
    ¡ACTUALIZADO! Lee todas las hojas de un archivo Excel.
    """
    _, extension = os.path.splitext(filepath)
    texto_completo = ""

    try:
        if extension == ".txt":
            with open(filepath, "r", encoding="utf-8") as f:
                texto_completo = f.read()

        elif extension == ".docx":
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                texto_completo += para.text + "\n"

        elif extension == ".xlsx":
            workbook = openpyxl.load_workbook(filepath, data_only=True)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                texto_completo += f"\n--- INICIO HOJA: {sheet_name} ---\n"

                for row in sheet.iter_rows():
                    if all(cell.value is None for cell in row):
                        continue

                    fila_texto = [
                        str(cell.value) if cell.value is not None else ""
                        for cell in row
                    ]
                    texto_completo += " | ".join(fila_texto) + "\n"

    except Exception as e:
        flash(f"Error al leer el archivo {filepath}: {e}", "danger")
        return None

    return texto_completo.strip()


def analizar_complejidad_requerimiento(texto):
    """
    Analiza el texto de un requerimiento para determinar métricas clave.
    Devuelve un diccionario con las métricas.
    ¡ACTUALIZADO! Usa la fórmula PERT (Req. #3) en lugar de heurística simple.
    """

    # 1. Conteo de Palabras
    palabras = texto.split()
    conteo_palabras = len(palabras)

    # 2. Conteo de Criterios de Aceptación (CA)
    criterios_funcionales = re.findall(
        r"\b(CA|C\.A\.|\bCriterio de Aceptaci[oó]n)[\s\-]?[—_]?(\d{1,3})\b",
        texto,
        re.IGNORECASE,
    )
    conteo_criterios_funcionales = len(set(criterios_funcionales))

    # 3. Conteo de Criterios No Funcionales (CNF)
    criterios_no_funcionales = re.findall(
        r"\b(CNF|C\.N\.F\.|Requerimiento No Funcional)[\s\-]?[—_]?(\d{1,3})\b",
        texto,
        re.IGNORECASE,
    )
    conteo_criterios_no_funcionales = len(set(criterios_no_funcionales))

    # 4. Cálculo de Complejidad
    nivel = "Baja"
    if conteo_palabras > 800 or conteo_criterios_funcionales > 15:
        nivel = "Alta"
    elif conteo_palabras > 300 or conteo_criterios_funcionales > 7:
        nivel = "Media"

    # 5. Cálculo de Casos (Heurística simple: 3 casos por criterio, 5 por CNF)
    casos_base = conteo_criterios_funcionales * 3
    casos_no_funcionales = conteo_criterios_no_funcionales * 5
    casos_totales_estimados = casos_base + casos_no_funcionales

    if casos_totales_estimados == 0 and conteo_palabras > 50:
        casos_totales_estimados = 5

    # 6. Definir el lookup de PERT (To, Tm, Tp) basado en complejidad
    PERT_LOOKUP = {
        "Baja": {"To": 0.1, "Tm": 0.25, "Tp": 0.5},
        "Media": {"To": 0.25, "Tm": 0.5, "Tp": 1.0},
        "Alta": {"To": 0.5, "Tm": 0.75, "Tp": 1.5},
    }

    # 7. Calcular el Tiempo Estimado (Te) por caso, usando la fórmula PERT
    lookup = PERT_LOOKUP.get(nivel, PERT_LOOKUP["Baja"])
    To = lookup["To"]
    Tm = lookup["Tm"]
    Tp = lookup["Tp"]

    # Te = (To + 4*Tm + Tp) / 6
    tiempo_estimado_por_caso = (To + (4 * Tm) + Tp) / 6

    # 8. Calcular las horas totales
    horas_diseño = tiempo_estimado_por_caso * casos_totales_estimados
    horas_ejecucion = tiempo_estimado_por_caso * casos_totales_estimados

    return {
        "palabras": conteo_palabras,
        "criterios": conteo_criterios_funcionales,
        "criterios_no_funcionales": conteo_criterios_no_funcionales,
        "nivel": nivel,
        "casos_estimados": casos_totales_estimados,
        "horas_diseño_estimadas": horas_diseño,
        "horas_ejecucion_estimadas": horas_ejecucion,
    }


# --- Funciones de Ayuda: Lógica de IA (Gemini) ---


def generar_prompt_dinamico(texto_requerimiento, plantilla_obj):
    """
    Crea el prompt para la IA, pidiendo solo las columnas
    mapeadas por el usuario.
    """
    mapas = plantilla_obj.mapas.all()
    if not mapas:
        return None

    nombres_columnas = [mapa.etiqueta for mapa in mapas]

    col_pasos = next((col for col in nombres_columnas if "paso" in col.lower()), None)
    col_resultados = next(
        (col for col in nombres_columnas if "resultado" in col.lower()), None
    )

    instruccion_extra_pasos = ""
    if col_pasos and col_resultados:
        instruccion_extra_pasos = (
            f"MUY IMPORTANTE: Para las columnas '{col_pasos}' y '{col_resultados}', "
            f"asegúrate de que cada paso esté en una línea separada (usando '\\n') "
            "y que haya exactamente la misma cantidad de líneas en ambas columnas. "
            "Cada línea de paso debe corresponder a una línea de resultado."
        )

    columnas_json_string = ",\n".join(
        [f'        "{col}": "..."' for col in nombres_columnas]
    )

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
    """
    Envía el prompt al API de Google (Gemini) y maneja la respuesta.
    ¡VERSIÓN MEJORADA! Auto-detecta el modelo disponible.
    """
    try:
        # Configuración del modelo
        api_key = current_app.config["GEMINI_API_KEY"]
        print(
            f"🔑 API Key encontrada: {api_key[:10]}..."
            if api_key
            else "❌ API Key NO encontrada"
        )

        if not api_key:
            return None, "Error: API Key no configurada"

        genai.configure(api_key=api_key)

        # Lista los modelos disponibles (para debug)
        print("📋 Listando modelos disponibles:")
        try:
            for m in genai.list_models():
                if "generateContent" in m.supported_generation_methods:
                    print(f"  ✅ {m.name}")
        except Exception as list_err:
            print(f"  ⚠️ No se pudo listar modelos: {list_err}")

        # Intenta con diferentes nombres de modelo
        model_names = [
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
            "gemini-1.5-flash-latest",
            "models/gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "models/gemini-1.5-flash",
            "gemini-pro",
        ]

        model = None
        model_usado = None
        for model_name in model_names:
            try:
                print(f"🔄 Intentando con modelo: {model_name}")
                model = genai.GenerativeModel(model_name)
                model_usado = model_name
                print(f"✅ Modelo cargado exitosamente: {model_name}")
                break
            except Exception as model_err:
                print(f"❌ Falló {model_name}: {model_err}")
                continue

        if not model:
            return (
                None,
                "Error: No se encontró ningún modelo compatible. Actualiza la librería: pip install --upgrade google-generativeai",
            )

        # Configuración de generación
        generation_config = {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 40,
        }

        print(f"📤 Enviando prompt a Gemini ({model_usado})...")
        response = model.generate_content(prompt, generation_config=generation_config)

        print("📥 Respuesta recibida de Gemini")

        # Extrae el texto de la respuesta
        texto_respuesta = response.text.strip()

        # Limpia el formato markdown si existe
        texto_limpio = texto_respuesta.replace("```json", "").replace("```", "").strip()

        # Valida que sea JSON
        try:
            json_data = json.loads(texto_limpio)
            print(f"✅ JSON válido con {len(json_data)} casos de prueba")
            return json_data, texto_limpio
        except json.JSONDecodeError as json_err:
            print(f"❌ Error de JSON: {json_err}")
            print(f"📄 Texto recibido (primeros 500 chars): {texto_limpio[:500]}...")
            return None, f"Error: La IA devolvió un JSON inválido. {json_err}"

    except Exception as e:
        print(f"❌ Error en API de Gemini: {e}")
        import traceback

        traceback.print_exc()
        return None, f"Error: Ocurrió un problema al contactar la API de Gemini. {e}"


# --- Funciones de Ayuda: Generación de Entregables ---


def _traducir_complejidad_a_numero(valor_texto):
    """
    Traduce el texto de complejidad/importancia (Alta, Media, Baja)
    a su equivalente numérico para TestLink (1, 2, 3).
    """
    if isinstance(valor_texto, str):
        valor_lower = valor_texto.strip().lower()
        if valor_lower == "alta":
            return 1
        elif valor_lower == "media":
            return 2
        elif valor_lower == "baja":
            return 3

    return valor_texto


@bp.route("/generate_file/<int:view_id>/<type>", endpoint="generate_file")
@login_required
def generar_excel_entregable(view_id, type):
    """
    Genera y descarga el archivo de entregable (Excel o XML)
    basado en un análisis guardado.
    """

    # 1. Recuperar el análisis y la plantilla
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        flash("No tienes permiso para acceder a este recurso.", "danger")
        return redirect(url_for("analysis.analysis_index"))

    plantilla_obj = analisis.plantilla_usada
    if not plantilla_obj:
        flash("No se encontró la plantilla asociada a este análisis.", "danger")
        return redirect(url_for("analysis.analysis_index", view_id=view_id))

    # 2. Cargar los datos JSON generados por la IA
    try:
        data = json.loads(analisis.ai_result_json)
        if not data or not isinstance(data, list):
            flash("No hay datos generados por la IA para exportar.", "warning")
            return redirect(url_for("analysis.analysis_index", view_id=view_id))
    except (json.JSONDecodeError, TypeError):
        flash(
            "Error al leer los datos de la IA. El formato JSON es inválido.", "danger"
        )
        return redirect(url_for("analysis.analysis_index", view_id=view_id))

    # 3. Obtener el mapeo de columnas
    mapas = plantilla_obj.mapas.all()
    if not mapas:
        flash("La plantilla no tiene columnas mapeadas.", "danger")
        return redirect(url_for("analysis.analysis_index", view_id=view_id))

    # === Lógica de Generación de EXCEL ===
    if type == "excel":
        # 4. Cargar el archivo de plantilla original
        plantilla_path = os.path.join(
            current_app.config["UPLOAD_FOLDER"], plantilla_obj.filename_seguro
        )
        try:
            wb = openpyxl.load_workbook(plantilla_path)
            ws = wb[plantilla_obj.sheet_name]
        except Exception as e:
            flash(f"Error al cargar el archivo de plantilla Excel: {e}", "danger")
            return redirect(url_for("analysis.analysis_index", view_id=view_id))

        # 5. Obtener las cabeceras mapeadas y sus índices de columna
        cabeceras_mapeadas = [mapa.etiqueta for mapa in mapas]
        col_indices = {
            mapa.etiqueta: openpyxl.utils.column_index_from_string(mapa.coordenada)
            for mapa in mapas
        }

        # 6. Lógica de Escritura de Datos
        fila_actual = plantilla_obj.header_row + 1

        etiqueta_pasos = None
        etiqueta_resultados = None

        if plantilla_obj.desglosar_pasos:
            etiqueta_pasos = next(
                (c for c in cabeceras_mapeadas if "paso" in c.lower()), None
            )
            etiqueta_resultados = next(
                (c for c in cabeceras_mapeadas if "resultado" in c.lower()), None
            )

            if not etiqueta_pasos or not etiqueta_resultados:
                flash(
                    'Modo "Desglosar Pasos" activado, pero no se encontraron etiquetas para "Pasos" y "Resultados".',
                    "warning",
                )
                plantilla_obj.desglosar_pasos = False
            else:
                for fila_data in data:
                    pasos = str(fila_data.get(etiqueta_pasos, "")).split("\n")
                    resultados = str(fila_data.get(etiqueta_resultados, "")).split("\n")

                    max_len = max(len(pasos), len(resultados))
                    pasos.extend([""] * (max_len - len(pasos)))
                    resultados.extend([""] * (max_len - len(resultados)))

                    for i in range(max_len):
                        for col_name, col_idx in col_indices.items():
                            celda = ws.cell(row=fila_actual, column=col_idx)

                            if col_name == etiqueta_pasos:
                                valor = pasos[i]
                            elif col_name == etiqueta_resultados:
                                valor = resultados[i]
                            elif i == 0:
                                valor = fila_data.get(col_name, "")

                                if (
                                    "importancia" in col_name.lower()
                                    or "complejidad" in col_name.lower()
                                ):
                                    valor = _traducir_complejidad_a_numero(valor)
                            else:
                                valor = ""

                            celda.value = valor
                            celda.alignment = Alignment(wrap_text=True, vertical="top")

                            # --- 🆕 MEJORA: LÓGICA DE COMENTARIO EN PRIMERA COLUMNA ---
                            import_source = fila_data.get("__import_source")

                            # Colocar comentario SIEMPRE en la primera columna (col_idx == 1)
                            if import_source and col_idx == 1:
                                # Solo agregar una vez por grupo desglosado (i == 0)
                                if i == 0:
                                    celda.comment = Comment(import_source, "Q-Vision")
                            # --- FIN DE LÓGICA DE COMENTARIO ---

                        fila_actual += 1

        if not plantilla_obj.desglosar_pasos:
            for fila in data:
                for cabecera_actual in cabeceras_mapeadas:
                    col_idx = col_indices[cabecera_actual]
                    celda = ws.cell(row=fila_actual, column=col_idx)

                    valor = fila.get(cabecera_actual, "")

                    if (
                        "importancia" in cabecera_actual.lower()
                        or "complejidad" in cabecera_actual.lower()
                    ):
                        valor = _traducir_complejidad_a_numero(valor)

                    if isinstance(valor, list):
                        valor = "\n".join(map(str, valor))

                    celda.value = valor
                    celda.alignment = Alignment(wrap_text=True, vertical="top")

                    # --- 🆕 MEJORA: LÓGICA DE COMENTARIO EN PRIMERA COLUMNA ---
                    import_source = fila.get("__import_source")

                    # Colocar comentario SIEMPRE en la primera columna (col_idx == 1)
                    if import_source and col_idx == 1:
                        celda.comment = Comment(import_source, "Q-Vision")
                    # --- FIN DE LÓGICA DE COMENTARIO ---

                fila_actual += 1

        # 7. Guardar el archivo temporalmente
        temp_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "temp")
        os.makedirs(temp_dir, exist_ok=True)
        excel_path = os.path.join(temp_dir, f"entregable_{analisis.id}.xlsx")
        wb.save(excel_path)

        # 8. Enviar el archivo al usuario
        return send_file(
            excel_path,
            as_attachment=True,
            download_name=f"{analisis.nombre_requerimiento or 'casos'}_generados.xlsx",
        )

    # === Lógica de Generación de XML ===
    elif type == "xml":
        try:
            cabeceras_mapeadas = [mapa.etiqueta for mapa in mapas]
            xml_string = generar_xml_entregable(data, cabeceras_mapeadas)

            temp_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "temp")
            os.makedirs(temp_dir, exist_ok=True)
            xml_path = os.path.join(temp_dir, f"entregable_{analisis.id}.xml")

            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml_string)

            return send_file(
                xml_path,
                as_attachment=True,
                mimetype="text/xml",
                download_name=f"{analisis.nombre_requerimiento or 'casos'}_testlink.xml",
            )

        except Exception as e:
            flash(f"Error al generar el XML: {e}", "danger")
            return redirect(url_for("analysis.analysis_index", view_id=view_id))

    flash("Tipo de archivo no válido para generar.", "danger")
    return redirect(url_for("analysis.analysis_index", view_id=view_id))


def generar_xml_entregable(data, cabeceras_mapeadas):
    """
    Genera un string XML compatible con TestLink.
    ¡ACTUALIZADO! Maneja pasos/resultados en líneas separadas.
    """

    def find_key(keywords):
        for key in cabeceras_mapeadas:
            if any(kw in key.lower() for kw in keywords):
                return key
        return None

    key_nombre = find_key(["nombre", "título", "titulo", "name"])
    key_resumen = find_key(["resumen", "descripción", "descripcion", "summary"])
    key_precondiciones = find_key(["precondicion", "precondition"])
    key_pasos = find_key(["pasos", "steps", "ejecución", "ejecucion"])
    key_resultados = find_key(["resultado", "results", "esperado"])
    key_importancia = find_key(["importancia", "complejidad", "priority"])

    root = ET.Element("testsuite")

    for i, caso in enumerate(data, 1):
        testcase = ET.SubElement(
            root, "testcase", name=caso.get(key_nombre, f"Caso de Prueba {i}")
        )

        summary = ET.SubElement(testcase, "summary")
        summary.text = caso.get(key_resumen, "N/A")

        preconditions = ET.SubElement(testcase, "preconditions")
        preconditions.text = caso.get(key_precondiciones, "N/A")

        importancia_texto = caso.get(key_importancia, "media").lower()
        if "alta" in importancia_texto:
            importancia_num = "3"
        elif "baja" in importancia_texto:
            importancia_num = "1"
        else:
            importancia_num = "2"
        importance = ET.SubElement(testcase, "importance")
        importance.text = importancia_num

        pasos_str = caso.get(key_pasos, "")
        resultados_str = caso.get(key_resultados, "")

        pasos_lista = str(pasos_str).split("\n") if pasos_str else ["N/A"]
        resultados_lista = (
            str(resultados_str).split("\n") if resultados_str else ["N/A"]
        )

        max_len = max(len(pasos_lista), len(resultados_lista))
        pasos_lista.extend([""] * (max_len - len(pasos_lista)))
        resultados_lista.extend([""] * (max_len - len(resultados_lista)))

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

    xml_str = ET.tostring(root, encoding="utf-8", method="xml")
    dom = xml.dom.minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


# --- Rutas Principales del Blueprint ---


@bp.route("/", methods=["GET", "POST"])
@login_required
def analysis_index():
    """
    Página principal del módulo de análisis.
    Maneja la subida del requerimiento y muestra los resultados.
    """
    form = AnalysisForm()
    form.plantilla.choices = [
        (p.id, p.nombre_plantilla) for p in current_user.plantillas.all()
    ]

    analisis_info = None
    ai_result_data = None
    ai_result_xml_string = None
    texto_requerimiento = None
    analisis_obj = None

    if request.method == "GET":
        view_id = request.args.get("view_id")
        if view_id:
            analisis_obj = Analisis.query.get(view_id)
            if analisis_obj and analisis_obj.autor == current_user:
                try:
                    ai_result_data = json.loads(analisis_obj.ai_result_json)
                    cabeceras_mapeadas = [
                        m.etiqueta for m in analisis_obj.plantilla_usada.mapas
                    ]
                    ai_result_xml_string = generar_xml_entregable(
                        ai_result_data, cabeceras_mapeadas
                    )
                except (json.JSONDecodeError, TypeError):
                    ai_result_data = None
                    flash("El JSON guardado está corrupto.", "danger")

                analisis_info = {
                    "nivel": analisis_obj.nivel_complejidad,
                    "casos": analisis_obj.casos_generados,
                    "criterios": analisis_obj.criterios_detectados,
                    "criterios_no_funcionales": analisis_obj.criterios_no_funcionales,
                    "palabras": analisis_obj.palabras_analizadas,
                    "horas_diseño": analisis_obj.horas_diseño_estimadas,
                    "horas_ejecucion": analisis_obj.horas_ejecucion_estimadas,
                }
                texto_requerimiento = analisis_obj.texto_requerimiento_raw
            else:
                flash("No se encontró el análisis o no tienes permiso.", "danger")
                return redirect(url_for("analysis.analysis_index"))

    if form.validate_on_submit():
        archivo = form.archivo_requerimiento.data
        plantilla_id = form.plantilla.data

        plantilla_obj = Plantilla.query.get(plantilla_id)
        if not plantilla_obj:
            flash("Plantilla no válida.", "danger")
            return redirect(url_for("analysis.analysis_index"))

        filename = secure_filename(archivo.filename)
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        archivo.save(filepath)

        texto_requerimiento = leer_requerimiento(filepath)
        os.remove(filepath)

        if texto_requerimiento is None:
            return redirect(url_for("analysis.analysis_index"))

        analisis_info = analizar_complejidad_requerimiento(texto_requerimiento)

        prompt = generar_prompt_dinamico(texto_requerimiento, plantilla_obj)
        if prompt is None:
            flash("La plantilla seleccionada no tiene columnas mapeadas.", "danger")
            return redirect(url_for("analysis.analysis_index"))

        ai_result_data, ai_result_raw = llamar_api_gemini(prompt)

        if ai_result_data is None:
            flash(f"Error de la IA: {ai_result_raw}", "danger")
            return redirect(url_for("analysis.analysis_index"))

        try:
            casos_generados = len(ai_result_data)

            nuevo_analisis = Analisis(
                id_usuario=current_user.id,
                id_plantilla=plantilla_obj.id,
                nombre_requerimiento=archivo.filename,
                texto_requerimiento_raw=texto_requerimiento,
                nivel_complejidad=analisis_info["nivel"],
                casos_generados=casos_generados,
                criterios_detectados=analisis_info["criterios"],
                criterios_no_funcionales=analisis_info["criterios_no_funcionales"],
                palabras_analizadas=analisis_info["palabras"],
                horas_diseño_estimadas=analisis_info["horas_diseño_estimadas"],
                horas_ejecucion_estimadas=analisis_info["horas_ejecucion_estimadas"],
                ai_result_json=ai_result_raw,
            )
            db.session.add(nuevo_analisis)
            db.session.commit()

            flash(
                f"¡Análisis completado! Se generaron {casos_generados} casos.",
                "success",
            )
            return redirect(
                url_for("analysis.analysis_index", view_id=nuevo_analisis.id)
            )

        except Exception as e:
            db.session.rollback()
            flash(f"Error al guardar en la base de datos: {e}", "danger")

    historial_analisis = current_user.analisis_historial.order_by(
        Analisis.timestamp.desc()
    ).all()

    return render_template(
        "analysis/analysis.html",
        title="Análisis de Requerimientos",
        form=form,
        analisis_info=analisis_info,
        ai_result_data=ai_result_data,
        ai_result_xml_string=ai_result_xml_string,
        texto_requerimiento=texto_requerimiento,
        analisis_obj=analisis_obj,
        historial_analisis=historial_analisis,
    )


@bp.route("/re_analyze/<int:view_id>", methods=["POST"])
@login_required
def re_analyze(view_id):
    """
    Toma el texto de requerimiento modificado del modal,
    lo re-analiza y actualiza el registro en la BD.
    """
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        flash("No tienes permiso.", "danger")
        return redirect(url_for("analysis.analysis_index"))

    texto_requerimiento_modificado = request.form.get("texto_requerimiento")

    if not texto_requerimiento_modificado:
        flash("El texto del requerimiento no puede estar vacío.", "warning")
        return redirect(url_for("analysis.analysis_index", view_id=view_id))

    plantilla_obj = analisis.plantilla_usada

    # 1. Re-analizar métricas
    analisis_info = analizar_complejidad_requerimiento(texto_requerimiento_modificado)

    # 2. Re-generar prompt
    prompt = generar_prompt_dinamico(texto_requerimiento_modificado, plantilla_obj)

    # 3. Re-llamar a la IA
    ai_result_data, ai_result_raw = llamar_api_gemini(prompt)

    if ai_result_data is None:
        flash(f"Error de la IA al re-analizar: {ai_result_raw}", "danger")
        return redirect(url_for("analysis.analysis_index", view_id=view_id))

    # 4. Actualizar el registro en la BD
    try:
        casos_generados = len(ai_result_data)

        analisis.texto_requerimiento_raw = texto_requerimiento_modificado
        analisis.nivel_complejidad = analisis_info["nivel"]
        analisis.casos_generados = casos_generados
        analisis.criterios_detectados = analisis_info["criterios"]
        analisis.criterios_no_funcionales = analisis_info["criterios_no_funcionales"]
        analisis.palabras_analizadas = analisis_info["palabras"]
        analisis.horas_diseño_estimadas = analisis_info["horas_diseño_estimadas"]
        analisis.horas_ejecucion_estimadas = analisis_info["horas_ejecucion_estimadas"]
        analisis.ai_result_json = ai_result_raw
        # ¡IMPORTANTE! Actualizamos el timestamp
        analisis.timestamp = db.func.now()

        db.session.commit()

        flash(
            f"¡Re-análisis completado! Se generaron {casos_generados} nuevos casos.",
            "success",
        )

    except Exception as e:
        db.session.rollback()
        flash(f"Error al actualizar el análisis: {e}", "danger")

    return redirect(url_for("analysis.analysis_index", view_id=view_id))


@bp.route("/delete_analysis/<int:view_id>", methods=["POST"])
@login_required
def delete_analysis(view_id):
    """Elimina un registro de análisis del historial."""
    analisis = Analisis.query.get_or_404(view_id)
    if analisis.autor != current_user:
        flash("No tienes permiso para eliminar este análisis.", "danger")
        return redirect(url_for("analysis.analysis_index"))

    try:
        db.session.delete(analisis)
        db.session.commit()
        flash("Análisis eliminado del historial.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar el análisis: {e}", "danger")

    return redirect(url_for("analysis.analysis_index"))


@bp.route("/clear_analysis", methods=["POST"])
@login_required
def clear_analysis():
    """Limpia la vista (simplemente redirige a la ruta base)."""
    return redirect(url_for("analysis.analysis_index"))


# --- 🔴 RUTA CORREGIDA: reuse_analysis (SOLUCIÓN AL ERROR CRÍTICO) ---


@bp.route("/reuse_analysis/<int:source_id>/<int:target_id>", methods=["POST"])
@login_required
def reuse_analysis(source_id, target_id):
    """
    Importa (reutiliza) casos de un análisis 'fuente' (source_id)
    y los AÑADE al 'destino' (target_id).

    🔴 CORRECCIÓN CRÍTICA: Ahora valida que ambos análisis usen LA MISMA PLANTILLA
    antes de fusionar. Esto evita la corrupción de datos en la tabla/exports.

    📊 MEJORA: Fusiona el texto del requerimiento y recalcula TODAS las métricas
    para mantener coherencia en la interfaz de usuario.
    """

    # 0. Validación básica
    if source_id == target_id:
        flash("No puedes importar un análisis sobre sí mismo.", "warning")
        return redirect(url_for("analysis.analysis_index", view_id=target_id))

    source_analysis = Analisis.query.get_or_404(source_id)
    target_analysis = Analisis.query.get_or_404(target_id)

    # 🔴 CORRECCIÓN #1: VALIDACIÓN DE PLANTILLA (Evita el bug crítico)
    if source_analysis.id_plantilla != target_analysis.id_plantilla:
        flash(
            "⚠️ Error: No se pueden combinar análisis de plantillas diferentes. "
            "Los campos no coinciden y se corrompería la tabla de resultados.",
            "danger"
        )
        return redirect(url_for("analysis.analysis_index", view_id=target_id))

    # 1. Validación de Permisos
    if source_analysis.autor != current_user or target_analysis.autor != current_user:
        flash("No tienes permiso para realizar esta acción.", "danger")
        return redirect(url_for("analysis.analysis_index"))

    # 2. Validar JSON
    if not source_analysis.ai_result_json or not target_analysis.ai_result_json:
        flash("Uno de los análisis no contiene datos válidos para combinar.", "danger")
        return redirect(url_for("analysis.analysis_index", view_id=target_id))

    try:
        # 3. Cargar datos
        source_data = json.loads(source_analysis.ai_result_json)
        target_data = json.loads(target_analysis.ai_result_json)

        # 4. Etiquetar los casos importados (para rastreabilidad en Excel)
        import_tag = f"Importado de: {source_analysis.nombre_requerimiento}"
        for caso in source_data:
            caso["__import_source"] = import_tag

        # 5. Fusionar datos (Casos + Texto)
        combined_data = target_data + source_data

        combined_text = (
            f"{target_analysis.texto_requerimiento_raw}\n\n"
            f"--- CASOS IMPORTADOS DE: {source_analysis.nombre_requerimiento} ---\n\n"
            f"{source_analysis.texto_requerimiento_raw}"
        )

        # 🔴 CORRECCIÓN #2: Recalcular métricas basándose en la FUSIÓN REAL
        # (Antes solo sumaba casos, lo que causaba incoherencia en la UI)
        new_metrics = analizar_complejidad_requerimiento(combined_text)

        # 6. Actualizar el análisis destino (Target)
        target_analysis.texto_requerimiento_raw = combined_text
        target_analysis.ai_result_json = json.dumps(combined_data, indent=4)

        # Actualizar TODAS las métricas para coherencia en la UI
        target_analysis.casos_generados = len(combined_data)  # Conteo real
        target_analysis.nivel_complejidad = new_metrics["nivel"]
        target_analysis.criterios_detectados = new_metrics["criterios"]
        target_analysis.criterios_no_funcionales = new_metrics[
            "criterios_no_funcionales"
        ]
        target_analysis.palabras_analizadas = new_metrics["palabras"]
        target_analysis.horas_diseño_estimadas = new_metrics["horas_diseño_estimadas"]
        target_analysis.horas_ejecucion_estimadas = new_metrics[
            "horas_ejecucion_estimadas"
        ]

        # 7. Guardar en la BD
        db.session.commit()

        flash(
            f"✅ ¡Éxito! Se importaron {len(source_data)} casos. "
            f"El requerimiento y las métricas han sido recalculados.",
            "success",
        )

    except json.JSONDecodeError:
        flash("Error al procesar los datos JSON de los casos de prueba.", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Ocurrió un error inesperado al reutilizar: {e}", "danger")

    return redirect(url_for("analysis.analysis_index", view_id=target_id))


@bp.route("/update_results/<int:view_id>", methods=["POST"])
@login_required
def update_results(view_id):
    """
    Recibe los datos JSON editados de la tabla de resultados
    y actualiza el registro en la base de datos.
    """
    analisis = Analisis.query.get_or_404(view_id)

    # 1. Verificar permisos
    if analisis.autor != current_user:
        return jsonify({"status": "error", "message": "Permiso denegado"}), 403

    # 2. Obtener los nuevos datos desde el request
    new_data = request.get_json()
    if not isinstance(new_data, list):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Datos inválidos. Se esperaba una lista.",
                }
            ),
            400,
        )

    try:
        # 3. Actualizar el análisis en la BD
        analisis.ai_result_json = json.dumps(new_data, indent=4)
        analisis.casos_generados = len(new_data)  # Actualizamos el conteo

        db.session.commit()

        return jsonify(
            {
                "status": "success",
                "message": f"¡Casos guardados! Se actualizaron {len(new_data)} casos.",
                "casos": len(new_data),
            }
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify({"status": "error", "message": f"Error al guardar en la BD: {e}"}),
            500,
        )