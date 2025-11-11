from flask_wtf import FlaskForm
from wtforms import SubmitField, SelectField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.validators import DataRequired

class RequerimientoUploadForm(FlaskForm):
    """Formulario para subir el archivo de requerimiento.
    El sistema analizará automáticamente la complejidad."""
    
    # Campo de selección de plantilla
    plantilla = SelectField(
        'Selecciona la Plantilla a Rellenar', 
        coerce=int, 
        validators=[DataRequired(message='Debes seleccionar una plantilla')]
    )
    
    # Archivo de requerimiento (.txt, .md, .docx)
    archivo_requerimiento = FileField(
        'Sube el Archivo de Requerimiento (.txt, .md, .docx)', 
        validators=[
            FileRequired(message='Debes subir un archivo'),
            FileAllowed(['txt', 'md', 'docx'], '¡Solo se permiten archivos .txt, .md o .docx!')
        ]
    )
    
    submit = SubmitField('Analizar con IA')