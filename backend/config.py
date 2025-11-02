import os

# Obtenemos la ruta base de nuestra carpeta 'backend'
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Configuración base de la aplicación."""
    
    # Llave secreta para proteger formularios (CSRF).
    # ¡Cámbiala por cualquier frase aleatoria que quieras!
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una-frase-secreta-muy-dificil-de-adivinar'
    
    # --- Configuración de la Base de Datos (SQLite) ---
    # Le decimos a SQLAlchemy dónde guardar nuestro archivo de base de datos.
    # Lo guardará en la misma carpeta 'backend/' con el nombre 'app.db'.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    
    # Desactiva una función de SQLAlchemy que no necesitamos.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Configuración de Subida de Archivos ---
    # Le dice a la app dónde guardar las plantillas que suban los usuarios.
    # Creará una carpeta 'uploads' dentro de 'backend'
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')