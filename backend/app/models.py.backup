from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timezone
import hashlib

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    
    plantillas = db.relationship('Plantilla', backref='autor', lazy='dynamic')
    analisis_historial = db.relationship('Analisis', backref='autor', lazy='dynamic')
    requerimientos = db.relationship('Requerimiento', backref='autor', lazy='dynamic')
    auditorias = db.relationship('AnalisisAudit', backref='usuario_editor', lazy='dynamic')

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
    tipo_archivo = db.Column(db.String(10))
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


# 🆕 NUEVA TABLA: Requerimientos únicos (evita duplicados)
class Requerimiento(db.Model):
    """
    Almacena requerimientos únicos basados en hash SHA-256.
    Permite detectar duplicados y evitar análisis redundantes.
    """
    __tablename__ = 'requerimiento'
    
    id = db.Column(db.Integer, primary_key=True)
    contenido_hash = db.Column(db.String(64), unique=True, index=True, nullable=False)  # SHA-256
    contenido_texto = db.Column(db.Text, nullable=False)
    timestamp_creacion = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    nombre_archivo_original = db.Column(db.String(255))  # Nombre del archivo subido
    
    # Relaciones
    analisis_relacionados = db.relationship('Analisis', backref='requerimiento_base', lazy='dynamic')
    
    @staticmethod
    def calcular_hash(texto):
        """Calcula el hash SHA-256 de un texto"""
        return hashlib.sha256(texto.encode('utf-8')).hexdigest()
    
    def __repr__(self):
        return f'<Requerimiento #{self.id} - Hash: {self.contenido_hash[:8]}...>'


class Analisis(db.Model):
    """
    MODIFICADO: Ahora referencia a Requerimiento para evitar duplicados.
    Incluye sistema de versionado y estados.
    """
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=lambda: datetime.now(timezone.utc))
    
    # Relaciones
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    id_plantilla = db.Column(db.Integer, db.ForeignKey('plantilla.id'), nullable=False)
    id_requerimiento = db.Column(db.Integer, db.ForeignKey('requerimiento.id'), nullable=True)  # 🆕 NUEVO
    
    # Sistema de versionado (para ediciones de requerimiento)
    parent_analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=True)  # 🆕 NUEVO
    version_numero = db.Column(db.Integer, default=1)  # 🆕 NUEVO
    
    # Estados posibles: 'active', 'deprecated', 'merged', 'snapshot'
    estado = db.Column(db.String(50), default='active', index=True)  # 🆕 NUEVO
    
    # Campos originales (compatibilidad hacia atrás)
    nombre_requerimiento = db.Column(db.String(255))
    texto_requerimiento_raw = db.Column(db.Text)
    
    # Métricas
    nivel_complejidad = db.Column(db.String(100))
    casos_generados = db.Column(db.Integer)
    criterios_detectados = db.Column(db.Integer)
    palabras_analizadas = db.Column(db.Integer)
    criterios_no_funcionales = db.Column(db.Integer, default=0)
    horas_diseño_estimadas = db.Column(db.Float, default=0)
    horas_ejecucion_estimadas = db.Column(db.Float, default=0)
    
    # Resultado de la IA
    ai_result_json = db.Column(db.Text)
    
    # Relaciones nuevas
    datos = db.relationship("AnalisisDato", backref="analisis", lazy="dynamic", cascade="all, delete-orphan")
    snapshots = db.relationship('AnalisisSnapshot', backref='analisis_origen', lazy='dynamic', cascade="all, delete-orphan")  # 🆕
    auditorias = db.relationship('AnalisisAudit', backref='analisis_modificado', lazy='dynamic', cascade="all, delete-orphan")  # 🆕
    tags = db.relationship('AnalisisTag', backref='analisis_parent', lazy='dynamic', cascade="all, delete-orphan")  # 🆕
    
    # Relación recursiva para versionado
    versiones_hijas = db.relationship('Analisis', backref=db.backref('analisis_padre', remote_side=[id]), lazy='dynamic')  # 🆕

    def __repr__(self):
        return f'<Analisis {self.id} - {self.nombre_requerimiento} (v{self.version_numero})>'


class AnalisisDato(db.Model):
    """Tabla original para datos adicionales (sin cambios)"""
    __tablename__ = "analisis_dato"

    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=False)
    fila_json = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<AnalisisDato {self.id} (Analisis {self.analisis_id})>"


# 🆕 NUEVA TABLA: Snapshots antes de re-análisis
class AnalisisSnapshot(db.Model):
    """
    Almacena instantáneas completas del análisis antes de modificaciones destructivas.
    Permite rollback y auditoría completa.
    """
    __tablename__ = 'analisis_snapshot'
    
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=False, index=True)
    timestamp_snapshot = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # Copia completa del estado anterior
    ai_result_json_snapshot = db.Column(db.Text, nullable=False)
    metricas_snapshot = db.Column(db.JSON, nullable=False)  # {nivel, casos, criterios, etc.}
    requerimiento_texto_snapshot = db.Column(db.Text, nullable=False)
    
    # Metadatos
    motivo = db.Column(db.String(200))  # "re_analisis_manual", "edicion_requerimiento", "fusion"
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    
    def __repr__(self):
        return f'<Snapshot #{self.id} - Analisis {self.analisis_id} @ {self.timestamp_snapshot}>'


# 🆕 NUEVA TABLA: Auditoría granular de cambios
class AnalisisAudit(db.Model):
    """
    Registra CADA cambio individual en la tabla de casos de prueba.
    Cumple con requisitos de auditoría (ISO 9001, SOC 2, GDPR).
    """
    __tablename__ = 'analisis_audit'
    
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    
    # Detalles del cambio
    # Tipos: 'cell_edit', 'cell_delete', 'row_add', 'row_delete', 'bulk_update'
    tipo_cambio = db.Column(db.String(50), nullable=False, index=True)
    coordenadas_json = db.Column(db.JSON)  # {fila: 5, columna: "Pasos de Ejecución"}
    valor_anterior = db.Column(db.Text)
    valor_nuevo = db.Column(db.Text)
    
    # Metadatos técnicos
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(250))
    session_id = db.Column(db.String(100))  # Para agrupar cambios en lote
    
    def __repr__(self):
        return f'<Audit #{self.id} - {self.tipo_cambio} @ {self.timestamp}>'


# 🆕 NUEVA TABLA: Sistema de Tags/Etiquetas (mejora propuesta)
class AnalisisTag(db.Model):
    """
    Sistema de etiquetado para categorizar análisis por estado del ciclo de vida.
    Ejemplos: "produccion", "testing", "aprobado", "rechazado", "revision", "qa"
    """
    __tablename__ = 'analisis_tag'
    
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey('analisis.id'), nullable=False, index=True)
    tag = db.Column(db.String(50), nullable=False, index=True)  # Nombre del tag
    color = db.Column(db.String(7), default='#6c757d')  # Color hex para UI (ej: #28a745)
    timestamp_creacion = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))  # Quién lo asignó
    
    # Constraint: No duplicar tags en el mismo análisis
    __table_args__ = (
        db.UniqueConstraint('analisis_id', 'tag', name='_analisis_tag_uc'),
    )
    
    def __repr__(self):
        return f'<Tag "{self.tag}" - Analisis {self.analisis_id}>'