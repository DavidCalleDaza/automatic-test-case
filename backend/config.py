from dotenv import load_dotenv
import os

# ⚠️ IMPORTANTE: Cargar las variables del .env ANTES de definir la clase Config
load_dotenv()

# Obtenemos la ruta base de nuestra carpeta 'backend'
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Configuración base de la aplicación."""
    
    # Llave secreta para proteger formularios (CSRF).
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-frase-secreta-muy-dificil-de-adivinar'
    
    # --- Configuración de la Base de Datos (SQLite) ---
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Configuración de Subida de Archivos ---
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    # --- 🔑 Configuración de API de Gemini (Google AI) ---
    # La API Key se carga desde el archivo .env
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Verificación en consola (útil para debugging)
    if not GEMINI_API_KEY:
        print("⚠️ WARNING: GEMINI_API_KEY no está configurada en el archivo .env")
    else:
        print(f"✅ GEMINI_API_KEY cargada: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-4:]}")