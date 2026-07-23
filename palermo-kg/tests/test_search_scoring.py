from api.routers.search import score_entity, tokenize


def test_subtype_exacto_supera_score_minimo():
    score, hits = score_entity(tokenize("restaurant"), {
        "name": "Casa de comidas", "subtype": "restaurant", "importance": 0, "properties": []
    })
    assert score >= 0.25
    assert hits == 0


def test_nombre_exacto_tiene_mejor_score_que_contexto():
    exact, _ = score_entity(tokenize("farmacia central"), {
        "name": "Farmacia Central", "subtype": "farmacia", "importance": 0, "properties": []
    })
    contextual, _ = score_entity(tokenize("farmacia central"), {
        "name": "Salud", "subtype": "farmacia", "description": "Farmacia central de Palermo", "importance": 0, "properties": []
    })
    assert exact > contextual
