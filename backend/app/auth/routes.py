from flask import render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.auth import bp  # Importamos el blueprint que crearemos en el siguiente archivo
from app.auth.forms import LoginForm, RegistrationForm
from app.models import Usuario

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Maneja el inicio de sesión del usuario."""
    # Si el usuario ya está logueado, lo redirigimos al inicio
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        # Busca al usuario en la base de datos
        user = Usuario.query.filter_by(email=form.email.data).first()
        
        # Si el usuario no existe o la contraseña es incorrecta, muestra un error
        if user is None or not user.check_password(form.password.data):
            flash('Email o contraseña inválidos', 'danger') # 'danger' es una categoría bootstrap
            return redirect(url_for('auth.login'))
        
        # Si todo está bien, loguea al usuario
        login_user(user, remember=form.remember_me.data)
        flash('¡Inicio de sesión exitoso!', 'success') # 'success' es una categoría bootstrap
        
        # Redirige al usuario a la página que intentaba ver
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')
        return redirect(next_page)
        
    return render_template('auth/login.html', title='Iniciar Sesión', form=form)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Maneja el registro de nuevos usuarios."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RegistrationForm()
    if form.validate_on_submit():
        # Crea un nuevo usuario con los datos del formulario
        user = Usuario(email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('¡Felicidades, te has registrado correctamente!', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/register.html', title='Registro', form=form)

@bp.route('/logout')
@login_required
def logout():
    """Maneja el cierre de sesión del usuario."""
    logout_user()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('main.index'))