from flask_wtf import FlaskForm
# --- ¡RadioField ya estaba, pero ahora IntegerField se va! ---
from wtforms import StringField, SubmitField, RadioField, SelectMultipleField, widgets
from flask_wtf.file import FileField, FileRequired
# --- DataRequired se usa para el nombre, InputRequired para los radios ---
from wtforms.validators import DataRequired, InputRequired, StopValidation

# --- Validadores Personalizados (Sin cambios) ---
class AtLeastOne:
    """Validador para asegurar que al menos un checkbox esté marcado."""
    def __init__(self, message=None):
        if not message:
            message = 'Debes seleccionar al menos un encabezado para mapear.'
        self.message = message

    def __call__(self, form, field):
        if not field.data:
            raise StopValidation(self.message)

class MultiCheckboxField(SelectMultipleField):
    """
    Widget para renderizar un SelectMultipleField como una lista de checkboxes.
    """
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


# --- Formulario 1: Subida de Plantilla (¡ACTUALIZADO!) ---
class PlantillaUploadForm(FlaskForm):
    """Formulario para subir una nueva plantilla."""
    
    # REQ 2: Mensaje de validación personalizado
    nombre_plantilla = StringField('Nombre de la Plantilla', validators=[
        DataRequired(message="Este campo es obligatorio.")
    ])
    
    # REQ 2: Mensaje de validación personalizado
    archivo_plantilla = FileField('Archivo de Plantilla (.xlsx o .docx)', validators=[
        FileRequired(message="Debes seleccionar un archivo.")
    ])
    
    submit = SubmitField('Subir y Continuar al Asistente')


# --- Formulario 2: Asistente - Seleccionar Hoja (Sin cambios) ---
class SelectSheetForm(FlaskForm):
    """Formulario para seleccionar la hoja de Excel."""
    sheet_name = RadioField(
        'Hoja de Trabajo', 
        validators=[DataRequired(message="Por favor, selecciona una hoja.")],
        coerce=str
    )
    submit = SubmitField('Siguiente')


# --- Formulario 3: Asistente - Seleccionar Fila (Sin cambios) ---
class SelectHeaderRowForm(FlaskForm):
    """Formulario para seleccionar la fila de encabezados (visual)."""
    
    header_row = RadioField(
        'Fila de Encabezados', 
        validators=[InputRequired(message="Por favor, selecciona la fila de encabezados.")],
        coerce=int # Asegura que el valor sea un número
    )
    submit = SubmitField('Siguiente')


# --- Formulario 4: Asistente - Mapear Columnas (Sin cambios) ---
class MapHeadersForm(FlaskForm):
    """Formulario para seleccionar las columnas (encabezados) a mapear."""
    headers = MultiCheckboxField(
        'Encabezados a Mapear', 
        validators=[AtLeastOne()],
        coerce=str # Las 'choices' serán las letras de columna (ej. 'A', 'B')
    )
    submit = SubmitField('Finalizar Mapeo')