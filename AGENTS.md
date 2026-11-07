# Instrucciones para Codex — Vectorizador

- Mantener la interfaz y los mensajes en castellano.
- Considerar V2.6 como referencia del código fuente original subido a este repositorio. No declararlo una nueva versión ni modificarlo sin petición explícita.
- Respetar los proyectos `.vect` existentes y su compatibilidad, sin borrar ni migrar datos personales automáticamente.
- Conservar las cuatro opciones principales de la interfaz; no añadir redondeo de esquinas sin autorización.
- Los ajustes de escala, corrección X/Y y offset deben mantenerse coherentes entre medidas visualizadas, STL y DXF.
- Mantener independientes el programa y la Suite CAD; coordinar integraciones sin cambiar otros módulos por defecto.
- Nunca incluir `Archivos/` con datos del usuario, `.venv`, `dist`, `build` o ejecutables generados en un commit.
- Antes de entregar cambios, ejecutar las pruebas adecuadas, documentar cuáles se han ejecutado realmente y señalar las que queden pendientes. Si se modifica el motor, verificar tanto DXF como STL.
- Guardar las versiones estables; conservar la posibilidad de volver a la versión anterior. No sobreescribir datos ni versiones históricas.
- El propietario decide qué versión se declara oficial, cuándo publicar y qué cambios integrar.
- Si la petición es una actualización de archivos, entregar únicamente los modificados salvo que el propietario pida un paquete completo.
