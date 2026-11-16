"""Regresión de extrusión STL: diagnósticos sin cambios geométricos silenciosos.

Ejecutar: python -m unittest discover -s tests -p 'test_stl_diagnostico.py'
"""
import unittest

from motor.extrusion_stl import construir_stl


def exterior():
    return {'id': 'exterior', 'tipo': 'rectangle', 'capa': 'CONTORNO_EXTERIOR',
            'a': [0.0, 0.0], 'b': [50.0, 50.0]}


def agujero(ident, x, y, radio):
    return {'id': ident, 'tipo': 'circle', 'capa': 'AGUJEROS',
            'cx': x, 'cy': y, 'radio': radio}


class DiagnosticoSTLTest(unittest.TestCase):
    def test_extruye_grosor_2_5_mm_con_agujero(self):
        raw, meta = construir_stl([exterior(), agujero('agujero-1', 25, 25, 4)], 2.5)
        self.assertGreater(len(raw), 84)
        self.assertEqual(meta['grosor_mm'], 2.5)
        self.assertEqual(meta['piezas'], 1)
        self.assertAlmostEqual(meta['ancho_mm'], 50.0)
        self.assertAlmostEqual(meta['alto_mm'], 50.0)

    def test_circulo_espurio_se_identifica_sin_borrarlo(self):
        entidades = [exterior(), agujero('normal', 25, 25, 4),
                     agujero('ruido', 60, 30, 0.031275)]
        with self.assertRaisesRegex(ValueError, 'Entidad 3 .*ruido.*0\\.0313'):
            construir_stl(entidades, 2.5)
        self.assertEqual(len(entidades), 3)

    def test_agujero_fuera_no_se_convierte_en_segundo_solido(self):
        entidades = [exterior(), agujero('fuera', 65, 25, 3)]
        with self.assertRaisesRegex(ValueError, 'El agujero 2 .*fuera.*está fuera'):
            construir_stl(entidades, 2.5)

    def test_agujero_que_cruza_borde_identifica_entidades(self):
        entidades = [exterior(), agujero('cerca-del-borde', 2, 25, 4)]
        with self.assertRaisesRegex(ValueError, 'Contornos 1 y 2.*se cruzan o tocan'):
            construir_stl(entidades, 2.5)


if __name__ == '__main__':
    unittest.main()
