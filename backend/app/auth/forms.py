from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
# Se añade 'Optional' para el formulario de perfil
from wtforms.validators import DataRequired, Email, EqualTo, StopValidation, Optional
from app.models import Usuario

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message="El campo Email es obligatorio."), Email(message="Email no válido.")])
    password = PasswordField('Contraseña', validators=[DataRequired(message="El campo Contraseña es obligatorio.")])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message="El campo Email es obligatorio."), Email(message="Email no válido.")])
    password = PasswordField('Contraseña', validators=[DataRequired(message="El campo Contraseña es obligatorio.")])
    password2 = PasswordField(
        'Repetir Contraseña', validators=[DataRequired(message="Este campo es obligatorio."), EqualTo('password', message='Las contraseñas no coinciden.')])
    submit = SubmitField('Registrarse')

    def validate_email(self, email):
        user = Usuario.query.filter_by(email=email.data).first()
        if user is not None:
            raise StopValidation('Este email ya está registrado.')

# --- NUEVO FORMULARIO PARA EL PERFIL ---
class EditProfileForm(FlaskForm):
    """
    Formulario para que un usuario edite su propia información.
    """
    email = StringField('Email', validators=[DataRequired(message="El email es obligatorio."), Email()])
    
    # Validadores 'Optional()' para que no sean obligatorios
    password = PasswordField('Nueva Contraseña (opcional)', validators=[Optional()])
    password2 = PasswordField(
        'Confirmar Nueva Contraseña', 
        validators=[Optional(), EqualTo('password', message='Las contraseñas no coinciden.')]
    )
    submit = SubmitField('Guardar Cambios')

    def __init__(self, original_email, *args, **kwargs):
        """
        Constructor personalizado para guardar el email original del usuario.
        """
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_email = original_email

    def validate_email(self, email):
        """
        Valida que el nuevo email no esté ya en uso por OTRO usuario.
        """
        if email.data != self.original_email:
            user = Usuario.query.filter_by(email=email.data).first()
            if user:
                raise StopValidation('Este email ya está en uso. Por favor, elige otro.')