from flask_wtf import FlaskForm
# --- AÑADIDO: Importamos RadioField ---
from wtforms import StringField, SubmitField, RadioField
from flask_wtf.file import FileField, FileRequired
from wtforms.validators import DataRequired

class PlantillaUploadForm(FlaskForm):
    """Formulario para subir una nueva plantilla etiquetada."""
    nombre_plantilla = StringField('Nombre de la Plantilla', validators=[DataRequired()])
    
    # --- ¡NUEVO CAMPO! ---
    # Opciones para que el usuario elija el tipo de escaneo.
    tipo_escaneo = RadioField(
        'Tipo de Plantilla',
        choices=[
            ('tabular', 'Tabular (Encabezados en una fila, datos abajo)'),
            ('formulario', 'Formulario (Etiquetas en celdas específicas, ej. B5)')
        ],
        validators=[DataRequired(message="Por favor, selecciona un tipo de plantilla.")],
        default='tabular' # Dejamos 'tabular' como la opción por defecto
    )
    
    archivo_plantilla = FileField('Archivo de Plantilla (.xlsx o .docx)', validators=[
        FileRequired()
    ])
    
    submit = SubmitField('Subir y Analizar Plantilla')