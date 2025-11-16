from datetime import datetime
from app import db, login
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# --- ¡NUEVA TABLA PARA AUDITORÍA! (Req. #5) ---
class HistorialCambios(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # A qué análisis pertenece este cambio
    id_analisis = db.Column(db.Integer, db.ForeignKey('analisis.id'))
    # Quién hizo el cambio
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    # "REQUERIMIENTO_MODIFICADO" o "CASOS_MODIFICADOS"
    tipo_cambio = db.Column(db.String(50))
    # Copia de seguridad del JSON *antes* del cambio
    datos_json_antiguos = db.Column(db.Text) 
    
    autor = db.relationship('Usuario', back_populates='historial_cambios')
    analisis = db.relationship('Analisis', back_populates='historial_cambios')

class Plantilla(db.Model):
    __tablename__ = 'plantilla'
    id = db.Column(db.Integer, primary_key=True)
    nombre_plantilla = db.Column(db.String(140))
    tipo_archivo = db.Column(db.String(10))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    filename_seguro = db.Column(db.String(255))
    
    # Campos para el mapeo de Excel
    sheet_name = db.Column(db.String(100), nullable=True)
    header_row = db.Column(db.Integer, nullable=True)
    
    # Campo para la lógica de generación de Excel
    desglosar_pasos = db.Column(db.Boolean, default=False)

    autor = db.relationship('Usuario', back_populates='plantillas')
    mapas = db.relationship('MapaPlantilla', back_populates='plantilla', lazy='dynamic', cascade="all, delete-orphan")
    analisis_usados = db.relationship('Analisis', back_populates='plantilla_usada', lazy='dynamic')

    def __repr__(self):
        return f'<Plantilla {self.nombre_plantilla}>'

class MapaPlantilla(db.Model):
    __tablename__ = 'mapa_plantilla'
    id = db.Column(db.Integer, primary_key=True)
    etiqueta = db.Column(db.String(140), index=True) # El nombre real de la columna (ej. "Pasos")
    coordenada = db.Column(db.String(140)) # La coordenada Excel (ej. "B")
    tipo_mapa = db.Column(db.String(50), default='columna') # Para futura expansión
    id_plantilla = db.Column(db.Integer, db.ForeignKey('plantilla.id'))

    plantilla = db.relationship('Plantilla', back_populates='mapas')

    def __repr__(self):
        return f'<Mapa {self.etiqueta} -> {self.coordenada}>'

class Analisis(db.Model):
    __tablename__ = 'analisis'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    id_plantilla = db.Column(db.Integer, db.ForeignKey('plantilla.id'))
    
    # Metadatos del requerimiento
    nombre_requerimiento = db.Column(db.String(255))
    texto_requerimiento_raw = db.Column(db.Text)
    
    # Métricas calculadas
    nivel_complejidad = db.Column(db.String(100))
    casos_generados = db.Column(db.Integer)
    criterios_detectados = db.Column(db.Integer)
    palabras_analizadas = db.Column(db.Integer)
    criterios_no_funcionales = db.Column(db.Integer)

    # Resultados
    ai_result_json = db.Column(db.Text, nullable=True) 
    
    # Módulo de Estimaciones
    horas_diseño_estimadas = db.Column(db.Float)
    horas_ejecucion_estimadas = db.Column(db.Float)
    
    # --- ¡NUEVO CAMPO PARA SOFT DELETE! (Req. #3) ---
    is_active = db.Column(db.Boolean, default=True, index=True)

    autor = db.relationship('Usuario', back_populates='analisis_historial')
    plantilla_usada = db.relationship('Plantilla', back_populates='analisis_usados')
    datos_analisis = db.relationship('AnalisisDato', back_populates='analisis', lazy='dynamic', cascade="all, delete-orphan")
    
    # --- ¡NUEVA RELACIÓN DE AUDITORÍA! (Req. #5) ---
    historial_cambios = db.relationship('HistorialCambios', 
                                        back_populates='analisis', 
                                        lazy='dynamic', 
                                        cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Analisis {self.nombre_requerimiento} - {self.timestamp}>'

class AnalisisDato(db.Model):
    __tablename__ = 'analisis_dato'
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=False)
    fila_json = db.Column(db.JSON, nullable=False) # Almacena un único caso de prueba como JSON
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    
    analisis = db.relationship('Analisis', back_populates='datos_analisis')

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256)) 
    
    plantillas = db.relationship('Plantilla', back_populates='autor', lazy='dynamic')
    analisis_historial = db.relationship('Analisis', back_populates='autor', lazy='dynamic')
    
    # --- ¡NUEVA RELACIÓN DE AUDITORÍA! (Req. #5) ---
    historial_cambios = db.relationship('HistorialCambios', back_populates='autor', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Usuario {self.email}>'

@login.user_loader
def load_user(id):
    return Usuario.query.get(int(id))