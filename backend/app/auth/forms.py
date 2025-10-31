from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError
from app.models import Usuario

class LoginForm(FlaskForm):
    """Formulario para el inicio de sesión de usuarios."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recuérdame')
    submit = SubmitField('Iniciar Sesión')

class RegistrationForm(FlaskForm):
    """Formulario para el registro de nuevos usuarios."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    password2 = PasswordField(
        'Repetir Contraseña', validators=[DataRequired(), EqualTo('password', message='Las contraseñas no coinciden.')])
    submit = SubmitField('Registrarse')

    def validate_email(self, email):
        """Verifica que el email no esté ya registrado en la base de datos."""
        user = Usuario.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Este email ya está registrado. Por favor, usa uno diferente.')