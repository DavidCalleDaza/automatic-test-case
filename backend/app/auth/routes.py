from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from app import db
from app.auth import bp
# Asegúrate de importar TODOS los formularios y modelos necesarios
from app.auth.forms import LoginForm, RegistrationForm, EditProfileForm
from app.models import Usuario, Analisis, HistorialCambios

# --- RUTA DE LOGIN (Existente) ---
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = Usuario.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Email o contraseña inválidos', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=form.remember_me.data)
        
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'):
            next_page = url_for('main.index')
        
        return redirect(next_page)
        
    return render_template('auth/login.html', title='Iniciar Sesión', form=form)

# --- RUTA DE LOGOUT (La que faltaba) ---
@bp.route('/logout')
def logout():
    # Limpiamos datos de sesión (el fix que implementamos)
    session.pop('ai_result_raw', None)
    session.pop('plantilla_seleccionada_id', None)
    
    logout_user()
    return redirect(url_for('main.index'))

# --- RUTA DE REGISTRO (Existente) ---
@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = Usuario(email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('¡Felicidades, ahora eres un usuario registrado!', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/register.html', title='Registrarse', form=form)

# --- NUEVA RUTA PARA VER PERFIL ---
@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """
    Muestra la página de perfil del usuario y maneja la edición.
    """
    # Pasamos el email original al formulario para la validación
    form = EditProfileForm(current_user.email)
    
    if form.validate_on_submit():
        # Actualizar email
        current_user.email = form.email.data
        
        # Actualizar contraseña (solo si el campo 'password' no está vacío)
        if form.password.data:
            current_user.set_password(form.password.data)
            
        db.session.commit()
        flash('Tu perfil ha sido actualizado exitosamente.', 'success')
        return redirect(url_for('auth.profile'))
    
    elif request.method == 'GET':
        # Poblar el formulario con los datos actuales del usuario
        form.email.data = current_user.email

    # --- Obtener Estadísticas del Usuario ---
    stats = {
        'total_analisis': Analisis.query.filter_by(id_usuario=current_user.id).count(),
        'analisis_activos': Analisis.query.filter_by(id_usuario=current_user.id, is_active=True).count(),
        'total_ediciones': HistorialCambios.query.filter_by(id_usuario=current_user.id).count()
    }
    
    return render_template('auth/profile.html', title='Mi Perfil', form=form, stats=stats)