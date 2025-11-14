from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    
    plantillas = db.relationship('Plantilla', backref='autor', lazy='dynamic')
    analisis_historial = db.relationship('Analisis', backref='autor', lazy='dynamic')

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
    
    sheet_name = db.Column(db.String(100), nullable=True)
    header_row = db.Column(db.Integer, nullable=True)
    
    desglosar_pasos = db.Column(db.Boolean, default=False)
    
    mapas = db.relationship('MapaPlantilla', backref='plantilla_padre', lazy='dynamic', cascade="all, delete-orphan")
    analisis_historial = db.relationship('Analisis', backref='plantilla_usada', lazy='dynamic')

    def __repr__(self):
        return f'<Plantilla {self.nombre_plantilla}>'

class MapaPlantilla(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    etiqueta = db.Column(db.String(140), index=True) 
    coordenada = db.Column(db.String(140))
    tipo_mapa = db.Column(db.String(50), default='simple') 
    id_plantilla = db.Column(db.Integer, db.ForeignKey('plantilla.id'))

    def __repr__(self):
        return f'<Mapa {self.etiqueta} @ {self.coordenada} (Tipo: {self.tipo_mapa})>'

class Analisis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    id_plantilla = db.Column(db.Integer, db.ForeignKey('plantilla.id'))
    
    nombre_requerimiento = db.Column(db.String(255))
    texto_requerimiento_raw = db.Column(db.Text)
    
    nivel_complejidad = db.Column(db.String(100))
    casos_generados = db.Column(db.Integer)
    criterios_detectados = db.Column(db.Integer)
    palabras_analizadas = db.Column(db.Integer)
    criterios_no_funcionales = db.Column(db.Integer, default=0)
    
    # --- ¡INICIO DE LA ACTUALIZACIÓN (Estimaciones)! ---
    horas_diseño_estimadas = db.Column(db.Float, default=0)
    horas_ejecucion_estimadas = db.Column(db.Float, default=0)
    # --- FIN DE LA ACTUALIZACIÓN ---
    
    ai_result_json = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Analisis {self.id} - {self.nombre_requerimiento}>'