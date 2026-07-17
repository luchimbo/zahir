from scrapers.shared.normalizer import (
    clean_cuit,
    normalize_bool,
    normalize_name,
    normalize_number,
    normalize_value,
)


class TestNormalizeName:
    def test_title_case_basico(self):
        assert normalize_name("EL DESNIVEL PALERMO") == "El Desnivel Palermo"

    def test_preserva_siglas(self):
        assert normalize_name("GLOBAL OIL S.R.L.") == "Global Oil S.R.L."
        assert normalize_name("empresa sa") == "Empresa SA"

    def test_preposiciones_en_minuscula_menos_la_primera(self):
        assert normalize_name("PARQUE DE LOS LEONES") == "Parque de los Leones"
        assert normalize_name("de la vega") == "De la Vega"

    def test_vacio(self):
        assert normalize_name("") == ""

    def test_espacios_extra(self):
        assert normalize_name("  bar   chino  ") == "Bar Chino"


class TestNormalizeValue:
    def test_title_case(self):
        assert normalize_value("ACTIVA") == "Activa"
        assert normalize_value("capital federal") == "Capital Federal"

    def test_vacio(self):
        assert normalize_value("") == ""


class TestNormalizeBool:
    def test_bool_nativo(self):
        assert normalize_bool(True) == "true"
        assert normalize_bool(False) == "false"

    def test_strings(self):
        assert normalize_bool("si") == "true"
        assert normalize_bool("sí") == "true"
        assert normalize_bool("yes") == "true"
        assert normalize_bool("1") == "true"
        assert normalize_bool("no") == "false"

    def test_numeros(self):
        assert normalize_bool(1) == "true"
        assert normalize_bool(0) == "false"


class TestNormalizeNumber:
    def test_entero(self):
        assert normalize_number("50") == "50"
        assert normalize_number(20.0) == "20"

    def test_decimal_con_coma(self):
        assert normalize_number("1234,5") == "1234.5"

    def test_invalido(self):
        assert normalize_number("abc") is None
        assert normalize_number(None) is None


class TestCleanCuit:
    def test_cuit_con_guiones(self):
        assert clean_cuit("30-12345678-9") == "30123456789"

    def test_vacio(self):
        assert clean_cuit("") is None
        assert clean_cuit("   ") is None
