from flask import Blueprint

# Creamos el Blueprint. 'core' será el nombre que usaremos.
bp = Blueprint('core', __name__)

# Importamos las rutas al final
from app.core import routes