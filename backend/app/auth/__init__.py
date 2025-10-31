from flask import Blueprint

# Creamos el Blueprint. 'auth' es el nombre que usaremos para referirnos a él
bp = Blueprint('auth', __name__)

# Importamos las rutas al final para evitar errores de importación circular
from app.auth import routes