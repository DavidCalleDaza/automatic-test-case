from flask import Blueprint

# Creamos el Blueprint. 'analysis' es el nombre que usaremos.
bp = Blueprint('analysis', __name__)

# Importamos las rutas al final
from app.analysis import routes