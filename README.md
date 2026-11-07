# Vectorizador — V2.6

Aplicación para Windows que convierte fotografías de piezas planas tomadas sobre una plantilla A4 en geometría editable 2D, con exportación **STL** y **DXF**. Incluye medición inteligente, corrección dimensional X/Y, ajuste de offset, vista 3D y proyectos guardados en formato `.vect`.

## Estado de esta versión

- **V2.6**: versión que el propietario ha confirmado compilada e instalada en su PC con Windows.
- La validación física de todas las geometrías y resultados de impresión no está acreditada por el hecho de haberla instalado.
- La Suite CAD V0.4 incorpora el motor V2.6. Este repositorio conserva las fuentes de la aplicación independiente.

## Ejecutar desde las fuentes

Requisitos: Python 3.10 o posterior. En Windows:

1. Ejecutar `Instalar_Entorno.bat` una vez con conexión a Internet.
2. Ejecutar `Iniciar.bat` para abrir la aplicación.

En Linux: `bash Instalar_Entorno.sh` y después `bash Iniciar.sh`.

## Preparar el ejecutable Windows

Ejecutar `CREAR_EXE_WINDOWS.bat` en Windows, con Python instalado. El script crea el ejecutable portable bajo `dist/` utilizando PyInstaller. No confundir el código de este repositorio con el EXE ya compilado o con el instalador de la versión instalada.

## Archivos importantes

- `servidor.py`: servidor y API.
- `motor/`: algoritmos de calibración, vectorización y exportación.
- `Vectorizador.html`, `editor.js`, `mejoras.js`, `medidor_stl.js`, `proyectos.js`, `visor_stl.js`: interfaz y edición.
- `plantillas/`: plantillas A4.
- `ejemplos/`: DXF históricos y dos imágenes sintéticas de prueba; las fotografías JPEG originales se han excluido deliberadamente de este repositorio público.
- `Archivos/`: carpetas vacías de trabajo, cuyos contenidos personales se excluyen mediante `.gitignore`.

## Pruebas

- `python COMPROBAR_V2_6.py` requiere las dependencias de `requirements.txt` y valida la versión, la interfaz y la carga de cinco módulos.
- Para otras comprobaciones de precisión geométrica, ver `LEEME.txt` y los informes históricos del proyecto.

## Conservación

El código y los recursos originales de V2.6 no se han modificado al preparar este repositorio. No subir aquí trabajos personales `.vect`, STL, DXF, fotografías privadas, bases de datos ni carpetas `dist/`, `build/`, `.venv/` o `_internal/`.

No se ha añadido una licencia de reutilización: que el repositorio sea público no implica por sí solo permiso para reutilizar el código. Puede elegirse una licencia explícita más adelante.

## Publicación sin fotografías originales

Las fotografías JPEG de `ejemplos/` se han retirado de esta copia para GitHub. El código fuente y el motor V2.6 se mantienen sin cambios. Algunas pruebas de precisión histórica documentadas requieren disponer de las fotografías originales por separado; estas no se publican. Conserva el ZIP original V2.6 y el instalador en una copia privada independiente.
