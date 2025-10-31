from app import create_app, db
from app.models import Usuario

# Creamos la instancia de la aplicación llamando a nuestra factory
app = create_app()

# Esto es para poder usar la base de datos en la terminal
@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'Usuario': Usuario}

if __name__ == '__main__':
    app.run(debug=True)