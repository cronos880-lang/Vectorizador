"""Comprobaciones de humo sin dependencias adicionales de test HTTP."""
import unittest
from pathlib import Path
from servidor import app, VERSION, ExportacionSTL

ROOT=Path(__file__).resolve().parents[1]

class SmokeTest(unittest.TestCase):
    def test_version_oficial_no_sustituida(self):
        self.assertEqual(VERSION, "V2.6")

    def test_recursos_interfaz_existen(self):
        rutas={getattr(r, "path", None) for r in app.routes}
        for ruta in ("/", "/api/version", "/api/exportar-stl",
                     "/editor.js", "/visor_stl.js", "/proyectos.js"):
            self.assertIn(ruta, rutas)
        for archivo in ("Vectorizador.html", "editor.js", "mejoras.js",
                        "visor_stl.js", "medidor_stl.js", "proyectos.js"):
            self.assertTrue((ROOT/archivo).is_file(), archivo)

    def test_modo_stl_experimental_explicito(self):
        html=(ROOT/"Vectorizador.html").read_text(encoding="utf-8")
        self.assertIn("extrudeRepairTrial", html)
        self.assertIn("reparacion_stl_prueba:reparar", html)
        self.assertIn("DXF ajustado no disponible", html)
        self.assertIn("reparacion_stl_prueba", ExportacionSTL.model_fields)

if __name__=="__main__":
    unittest.main()
