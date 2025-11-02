from flask_wtf import FlaskForm
# --- AÑADIDO: Importamos SelectField ---
from wtforms import SubmitField, SelectField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.validators import DataRequired

class RequerimientoUploadForm(FlaskForm):
    """Formulario para subir el archivo de requerimiento."""
    
    # --- ¡NUEVO CAMPO! ---
    # Este es el menú desplegable para seleccionar la plantilla.
    # Lo llenaremos dinámicamente desde la ruta (routes.py).
    plantilla = SelectField('Selecciona la Plantilla a Rellenar', coerce=int, validators=[DataRequired()])
    
    # Permitiremos .txt, .md (markdown) y .docx
    archivo_requerimiento = FileField('Sube el Archivo de Requerimiento (.txt, .md, .docx)', validators=[
        FileRequired(),
        FileAllowed(['txt', 'md', 'docx'], '¡Solo se permiten archivos .txt, .md o .docx!')
    ])
    
    submit = SubmitField('Analizar Requerimiento con IA')