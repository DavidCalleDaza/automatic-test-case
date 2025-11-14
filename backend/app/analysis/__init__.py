from flask import Blueprint

bp = Blueprint('analysis', __name__, template_folder='templates/analysis')

# Esta es la forma correcta, solo importando las rutas.
# Las rutas, a su vez, importarán los formularios.
from . import routes