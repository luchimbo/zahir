# Plan de desarrollo - Palermo Knowledge Graph

Este archivo queda como índice de continuidad del proyecto.

La documentación operativa vigente está en:

- `palermo-kg/RETOMAR.md`: guía para retomar trabajo.
- `palermo-kg/README.md`: descripción, setup y contratos principales.
- `palermo-kg/PLAN.md`: roadmap vivo.
- `palermo-kg/db/RULES.md`: reglas obligatorias antes de tocar DB o scrapers.

## Estado actual

Palermo Knowledge Graph ya tiene una v1 funcional con API, frontend, scrapers principales y búsqueda natural con citas. La referencia actual documentada es de 46.711 entidades canónicas activas.

## Prioridad inmediata

La prioridad no es sumar más fuentes, sino consolidar:

1. Documentación alineada.
2. Textos y encoding corregidos.
3. Smoke tests de búsqueda/citas.
4. Verificación de API y frontend.
5. Vista de entidad más clara como siguiente mejora de producto.

## Fuera de alcance inmediato

No correr sin aprobación:

- `palermo-kg/scrapers/zonaprop.py`
- `palermo-kg/scrapers/argenprop.py`
- futuro scraper de MercadoLibre inmuebles
- nuevas APIs pagas
- ingestas masivas que puedan exceder límites de Neon Free
