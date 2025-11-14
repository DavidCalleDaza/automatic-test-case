import os
import json
from pathlib import Path

# --- Configuración ---

# Directorios que el script ignorará por completo
# Puedes agregar 'dist', 'build', o cualquier carpeta de artefactos
IGNORE_DIRS = {
    '.git',
    'node_modules',
    '.venv',
    'venv',
    '__pycache__',
    'env',
    '.vscode'
}

# Archivos específicos a ignorar
IGNORE_FILES = {
    '.DS_Store',
    '.gitignore'
}

# Extensiones que consideramos "scripts" o "código fuente"
# Ajusta esta lista según las tecnologías de tu proyecto
CODE_EXTENSIONS = {
    '.py',      # Python
    '.js',      # JavaScript
    '.jsx',     # React JS
    '.ts',      # TypeScript
    '.tsx',     # React TS
    '.html',    # HTML
    '.css',     # CSS
    '.scss',    # SASS
    '.sh',      # Shell
    '.ps1',     # PowerShell
    '.sql',     # SQL
    '.ipynb'    # Jupyter Notebook
}

# --- Fin de Configuración ---


def analyze_project(start_dir="."):
    """
    Escanea el proyecto desde start_dir, generando un informe de estructura
    y un informe de tecnologías/dependencias.
    """
    project_root = Path(start_dir).resolve()
    
    structure_lines = [f"🌳 Análisis de Estructura del Proyecto: {project_root.name}\n"]
    tech_lines = [f"🔬 Informe de Tecnologías y Dependencias: {project_root.name}\n"]
    
    scripts_found = []
    technologies_inferred = set()
    dependencies = {
        "python": set(),
        "javascript": set()
    }

    print(f"Iniciando escaneo en: {project_root}")
    print("Ignorando directorios:", IGNORE_DIRS)

    for root, dirs, files in os.walk(project_root, topdown=True):
        # 1. Pruning: Evita que os.walk entre en directorios ignorados
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        current_path = Path(root)
        try:
            relative_path = current_path.relative_to(project_root)
        except ValueError:
            continue  # En caso de algún problema con los paths

        # 2. Construir el árbol de directorios para 'project_structure.txt'
        if relative_path.name != ".":
            depth = len(relative_path.parts)
            indent = "    " * (depth - 1)
            structure_lines.append(f"{indent}└── 📂 {relative_path.name}/")
        else:
            depth = 0
        
        indent_files = "    " * depth

        for f in files:
            if f in IGNORE_FILES:
                continue
            
            file_path = current_path / f
            file_ext = file_path.suffix.lower()

            # 3. Agregar archivos al árbol
            structure_lines.append(f"{indent_files}    └── 📄 {f}")

            # 4. Identificar scripts y tecnologías por extensión
            if file_ext in CODE_EXTENSIONS:
                scripts_found.append(str(relative_path / f))
                
                if file_ext == '.py':
                    technologies_inferred.add("Python")
                if file_ext in {'.js', '.jsx', '.ts', '.tsx'}:
                    technologies_inferred.add("JavaScript/TypeScript")
                    if file_ext in {'.jsx', '.tsx'}:
                        technologies_inferred.add("React (JSX/TSX detectado)")
                if file_ext in {'.html', '.css', '.scss'}:
                    technologies_inferred.add("Web (HTML/CSS)")
                if file_ext == '.sql':
                    technologies_inferred.add("SQL")

            # 5. Analizar archivos de dependencias
            if f == "requirements.txt":
                technologies_inferred.add("Python (requirements.txt)")
                try:
                    with open(file_path, 'r', encoding='utf-8') as req_file:
                        for line in req_file:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                dependencies["python"].add(line)
                except Exception as e:
                    tech_lines.append(f"\n[Error] No se pudo leer {file_path}: {e}")

            if f == "package.json":
                technologies_inferred.add("Node.js (package.json)")
                try:
                    with open(file_path, 'r', encoding='utf-8') as pkg_file:
                        pkg_data = json.load(pkg_file)
                        
                        # Inferir React/Angular/Vue, etc.
                        all_deps = {**pkg_data.get('dependencies', {}), **pkg_data.get('devDependencies', {})}
                        if 'react' in all_deps:
                            technologies_inferred.add("React")
                        if '@angular/core' in all_deps:
                            technologies_inferred.add("Angular")
                        if 'vue' in all_deps:
                            technologies_inferred.add("Vue.js")

                        # Capturar dependencias
                        deps = pkg_data.get('dependencies', {})
                        dev_deps = pkg_data.get('devDependencies', {})
                        
                        for dep, ver in deps.items():
                            dependencies["javascript"].add(f"{dep}: {ver}")
                        for dep, ver in dev_deps.items():
                            dependencies["javascript"].add(f"{dep}: {ver} (dev)")
                            
                except Exception as e:
                    tech_lines.append(f"\n[Error] No se pudo leer o parsear {file_path}: {e}")

    # --- Generar Reporte de Estructura ---
    structure_lines.append("\n\n" + "="*30)
    structure_lines.append("📜 RESUMEN DE SCRIPTS Y CÓDIGO")
    structure_lines.append("="*30 + "\n")
    if scripts_found:
        structure_lines.extend(sorted(scripts_found))
    else:
        structure_lines.append("No se encontraron archivos de código con las extensiones definidas.")

    try:
        with open("project_structure.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(structure_lines))
        print(f"\n✅ Reporte de estructura guardado en 'project_structure.txt'")
    except Exception as e:
        print(f"\n❌ Error al guardar 'project_structure.txt': {e}")

    # --- Generar Reporte de Tecnología ---
    tech_lines.append("\n\n" + "="*30)
    tech_lines.append("💻 TECNOLOGÍAS INFERIDAS")
    tech_lines.append("="*30 + "\n")
    if technologies_inferred:
        for tech in sorted(list(technologies_inferred)):
            tech_lines.append(f"* {tech}")
    else:
        tech_lines.append("No se pudieron inferir tecnologías.")

    tech_lines.append("\n\n" + "="*30)
    tech_lines.append("🐍 DEPENDENCIAS DE PYTHON (de requirements.txt)")
    tech_lines.append("="*30 + "\n")
    if dependencies["python"]:
        for dep in sorted(list(dependencies["python"])):
            tech_lines.append(f"- {dep}")
    else:
        tech_lines.append("No se encontró 'requirements.txt' o estaba vacío.")

    tech_lines.append("\n\n" + "="*30)
    tech_lines.append("📦 DEPENDENCIAS DE JAVASCRIPT (de package.json)")
    tech_lines.append("="*30 + "\n")
    if dependencies["javascript"]:
        for dep in sorted(list(dependencies["javascript"])):
            tech_lines.append(f"- {dep}")
    else:
        tech_lines.append("No se encontró 'package.json' o no tiene dependencias.")
        
    try:
        with open("tech_report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(tech_lines))
        print(f"✅ Reporte de tecnología guardado en 'tech_report.txt'")
    except Exception as e:
        print(f"❌ Error al guardar 'tech_report.txt': {e}")


# --- Punto de entrada ---
if __name__ == "__main__":
    # Escanea el directorio actual por defecto
    # Puedes cambiarlo a una ruta específica, ej: analyze_project("C:/Ruta/A/Tu/Proyecto")
    analyze_project(".")
    print("\nAnálisis completado.")