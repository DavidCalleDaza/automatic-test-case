from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from flask_wtf.file import FileField, FileRequired
from wtforms.validators import DataRequired

class AnalysisForm(FlaskForm):
    plantilla = SelectField(
        'Seleccionar Plantilla', 
        coerce=int, 
        validators=[DataRequired(message="Debes seleccionar una plantilla.")]
    )
    archivo_requerimiento = FileField(
        'Archivo de Requerimiento (.txt, .docx, .xlsx)', 
        validators=[FileRequired(message="Debes subir un archivo.")]
    )
    submit = SubmitField('Analizar')