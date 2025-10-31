from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# La clase 'UserMixin' incluye las funciones que Flask-Login
# necesita para manejar a los usuarios (como is_authenticated, etc.)
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    
    # Relaciones (qué otros datos "posee" este usuario)
    # plantillas = db.relationship('Plantilla', backref='autor', lazy='dynamic')

    def set_password(self, password):
        # Esta función crea un "hash" seguro. Nunca guardamos la contraseña real.
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # Esta función compara el hash guardado con la contraseña que el usuario ingresa.
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.email}>'

# Esta función es requerida por Flask-Login para saber cómo
# cargar un usuario desde la base de datos en cada sesión.
@login.user_loader
def load_user(id):
    return Usuario.query.get(int(id))

# --- POR AHORA, DEJAREMOS LOS OTROS MODELOS PENDIENTES ---
# Más adelante añadiremos aquí las clases para Plantilla y MapaPlantilla
# class Plantilla(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     nombre_plantilla = db.Column(db.String(140))
#     id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'))
#     ...