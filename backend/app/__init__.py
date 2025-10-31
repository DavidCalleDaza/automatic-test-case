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
    
    # 1. Blueprint de Autenticación (¡NUEVO!)
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # 2. Blueprint Principal (¡NUEVO!)
    # (Lo creamos aquí mismo para la ruta '/')
    from flask import Blueprint
    main_bp = Blueprint('main', __name__)
    @main_bp.route('/')
    def index():
        return "¡El esqueleto de la app funciona! <a href='/auth/login'>Login</a> <a href='/auth/register'>Registro</a>"
    app.register_blueprint(main_bp)

    return app