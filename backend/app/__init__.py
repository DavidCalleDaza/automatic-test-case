from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

# --- Inicialización de la Base de Datos ---
db = SQLAlchemy()
login = LoginManager()
migrate = Migrate()
login.login_view = 'auth.login'
login.login_message = 'Por favor, inicia sesión para acceder a esta página.'

# --- Factory de la Aplicación ---
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login.init_app(app)
    migrate.init_app(app, db)

    # --- Registrar Blueprints (Módulos) ---
    
    # 1. Blueprint de Autenticación
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # 2. Blueprint Principal
    from flask import Blueprint, redirect, url_for
    from flask_login import current_user
    
    main_bp = Blueprint('main', __name__)
    @main_bp.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('core.dashboard'))
        return redirect(url_for('auth.login'))
        
    app.register_blueprint(main_bp)

    # 3. Blueprint del Core (Dashboard/Plantillas)
    from app.core import bp as core_bp
    app.register_blueprint(core_bp)

    # 4. Blueprint de Análisis (¡NUEVO!)
    from app.analysis import bp as analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/analysis') # Opcional: prefijo de ruta

    return app