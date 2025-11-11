from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    
    plantillas = db.relationship('Plantilla', backref='autor', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.email}>'

@login.user_loader
def load_user(id):
    return Usuario.query.get(int(id))

class Plantilla(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_plantilla = db.Column(db.String(140))
    tipo_archivo = db.Column(db.String(10)) # 'Excel' o 'Word'
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    filename_seguro = db.Column(db.String(255)) 
    
    # --- ¡NUEVOS CAMPOS! ---
    # Guardará el nombre de la hoja de Excel seleccionada por el usuario (ej. "Casos de Prueba")
    sheet_name = db.Column(db.String(100), nullable=True)
    # Guardará el número de fila donde están los encabezados (ej. 10)
    header_row = db.Column(db.Integer, nullable=True)
    
    # ---
    
    mapas = db.relationship('MapaPlantilla', backref='plantilla_padre', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Plantilla {self.nombre_plantilla}>'

class MapaPlantilla(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Ahora 'etiqueta' guardará el nombre del encabezado (ej. "ID del caso de prueba")
    etiqueta = db.Column(db.String(140), index=True) 
    
    # 'coordenada' guardará la columna (ej. "A", "B")
    coordenada = db.Column(db.String(140))
    
    # 'tipo_mapa' seguirá siendo 'fila_tabla' o 'celda_simple'
    tipo_mapa = db.Column(db.String(50), default='simple') 
    
    id_plantilla = db.Column(db.Integer, db.ForeignKey('plantilla.id'))

    def __repr__(self):
        return f'<Mapa {self.etiqueta} @ {self.coordenada} (Tipo: {self.tipo_mapa})>'