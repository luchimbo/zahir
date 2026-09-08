# Reglas del Knowledge Graph — Palermo

Estas reglas garantizan que la base de datos se mantenga consistente a medida que crece.
**Toda persona que toque el código debe leer y respetar estas reglas.**

---

## 1. Entidades duplicadas — nunca borrar

Si el scraper encuentra que una entidad ya existe con otro nombre:
- NO eliminar la entidad duplicada
- Asignar `canonical_id` apuntando a la entidad canónica (la original)
- La entidad duplicada queda en la DB como registro histórico
- Agregar el nombre alternativo al array `all_names` de la entidad canónica

```sql
-- Marcar duplicado
UPDATE entities SET canonical_id = '<uuid-canonico>' WHERE id = '<uuid-duplicado>';

-- Agregar nombre alternativo a la canónica
UPDATE entities SET all_names = all_names || '{"Nombre Alternativo"}' WHERE id = '<uuid-canonico>';
```

**Todos los queries normales deben filtrar `canonical_id IS NULL`.**

---

## 2. Propiedades históricas — nunca borrar

Cuando el valor de una propiedad cambia (ej: el precio de alquiler subió):
- NO actualizar el registro existente
- Cerrar el registro anterior con `valid_until = CURRENT_DATE`
- Insertar un nuevo registro con el valor nuevo

```sql
-- Cerrar propiedad anterior
SELECT close_property('<prop-id>');  -- función en 09_functions.sql

-- Insertar nueva
INSERT INTO properties (entity_id, key, value, value_type, valid_from, source_id)
VALUES ('<entity-id>', 'price_usd', '1200', 'number', CURRENT_DATE, '<source-id>');
```

La vista `active_properties` filtra automáticamente las propiedades vigentes.

---

## 3. Tipos de entidad — PascalCase, no eliminar

- Siempre PascalCase: `Organization`, `LegalEntity`, `HistoricalRecord`
- Para agregar un tipo nuevo: INSERT en `entity_types` + agregar aquí
- Nunca eliminar un tipo que tenga entidades (la FK lo impide)

**Tipos actuales:**
`Location` | `Facility` | `Organization` | `Property` | `Event` | `Transport` | `LegalEntity` | `Trademark` | `LegalCase` | `Parcel` | `HistoricalRecord` | `MarketIndex` | `Security` | `EconomicSeries` | `Regulation`

Los últimos cuatro son la **capa nacional/contextual** (ver §11): se crean siempre con `lat=NULL, lng=NULL`, nunca compiten con entidades geográficas de CABA.

---

## 4. Keys de properties — siempre snake_case

- Correcto: `price_usd`, `hours_open`, `rating`, `area_m2`
- Incorrecto: `priceUSD`, `HoursOpen`, `Rating`
- Usar unidades en el nombre cuando corresponda: `price_usd`, `area_m2`, `duration_min`

**Keys estándar por tipo de entidad:**

| Entidad | Keys comunes |
|---|---|
| Organization | `address`, `phone`, `website`, `instagram`, `hours_open`, `hours_close`, `rating`, `review_count`, `price_range`, `cuisine_type` |
| Property | `listing_type`, `price_usd`, `area_m2`, `rooms`, `bathrooms`, `expenses_ars`, `source_url` |
| Facility | `is_free`, `admission_price_ars`, `hours_open`, `area_m2`, `rating` |
| Location | `avg_rent_usd`, `avg_sale_usd_m2`, `walkability_score`, `population_estimate` |
| LegalEntity | `cuit`, `estado`, `tipo_sociedad`, `fecha_constitucion` |
| MarketIndex | `ticker`, `market`, `currency`, `series_description` |
| Security | `ticker`, `market`, `isin`, `currency`, `issuer_name`, `series_description` |
| EconomicSeries | `series_code`, `series_description`, `unit`, `frequency`, `publisher` |
| Regulation | `document_number`, `document_letter`, `publication_date`, `document_url`, `summary`, `publisher`, `topic` |

---

## 5. Tags — lowercase con guiones, sin espacios

- Correcto: `pet-friendly`, `sin-tacc`, `vegano`, `vista-al-verde`
- Incorrecto: `Pet Friendly`, `SinTacc`, `VEGANO`
- El constraint `tag_format` en la tabla lo garantiza automáticamente

---

## 6. source_name — siempre snake_case

- Correcto: `ba_data`, `google_places`, `boletin_oficial`
- Incorrecto: `BA Data`, `GooglePlaces`, `BoletinOficial`

---

## 7. Confidence score — basado en número de fuentes

Usar la función `calc_confidence(nb_sources)` definida en `09_functions.sql`:

| Fuentes que confirman | confidence |
|---|---|
| 1 fuente | 0.50 |
| 2 fuentes | 0.75 |
| 3 o más | 1.00 |

```sql
SELECT calc_confidence(2);  -- devuelve 0.75
```

---

## 8. canonical_id — regla de uso en queries

- `canonical_id IS NULL` → entidad canónica → **usar en todos los queries normales**
- `canonical_id IS NOT NULL` → duplicado → **ignorar en queries normales**

```sql
-- CORRECTO
SELECT * FROM entities WHERE is_active = true AND canonical_id IS NULL;

-- INCORRECTO (puede devolver duplicados)
SELECT * FROM entities WHERE is_active = true;
```

La API filtra esto automáticamente. Solo se accede a duplicados cuando se investiga la historia de deduplicación.

---

## 9. Normativa de escritura — OBLIGATORIO

### Idioma
- **Keys de properties** → siempre en **inglés**, snake_case
  - ✓ `address`, `rating`, `hours_open`, `price_usd`, `area_m2`
  - ✗ `direccion`, `calificacion`, `horario_apertura`
- **Tipos de entidad** → inglés, PascalCase: `Organization`, `LegalEntity`, `Facility`
- **Tipos de relación** → inglés, UPPER_SNAKE: `LOCATED_IN`, `OWNED_BY`
- **Subtypes** → inglés, snake_case: `restaurant`, `beauty_salon`, `estacion_subte`
  - Excepción: términos sin traducción directa pueden quedar en español (`estacion_subte`)

### Formato de valores de texto
- **Valores de texto** → siempre **Title Case**
  - ✓ `"Palermo Soho"`, `"Sociedad Anónima"`, `"El Desnivel"`
  - ✗ `"PALERMO SOHO"`, `"palermo soho"`, `"EL DESNIVEL"`
- **Valores numéricos** → string del número sin formato: `"1200"`, `"4.5"`, `"85"`
- **Valores booleanos** → `"true"` o `"false"` (lowercase)
- **Nombres de entidades** → Title Case, respetando siglas: `"SRL"`, `"SA"`, `"CABA"`

### Normalización en scrapers
Todo scraper debe aplicar estas funciones antes de insertar (definidas en `scrapers/shared/normalizer.py`):
```python
from scrapers.shared.normalizer import normalize_name, normalize_value

name = normalize_name("EL DESNIVEL PALERMO")   # → "El Desnivel Palermo"
val  = normalize_value("ACTIVA")               # → "Activa"
```

---

## 10. Agregar un nuevo tipo de relación

Para agregar un tipo de relación nuevo al constraint de `relationships`:

```sql
ALTER TABLE relationships DROP CONSTRAINT valid_relationship_type;
ALTER TABLE relationships ADD CONSTRAINT valid_relationship_type
    CHECK (relationship_type IN (
        'LOCATED_IN', 'NEAR', 'BELONGS_TO', 'OFFERS',
        'CONNECTS_TO', 'OWNED_BY', 'PART_OF', 'RELATED_TO',
        'NUEVO_TIPO'  -- agregar aquí
    ));
```

Y documentar el nuevo tipo en esta sección de RULES.md.

---

## 10. Orden de ejecución de los SQLs

Siempre ejecutar en este orden (las FKs dependen del orden):

```
00_extensions.sql
01_entity_types.sql
02_sources.sql
03_entities.sql
04_properties.sql
05_relationships.sql
06_tags.sql
07_indexes.sql
08_constraints.sql
09_functions.sql
10_triggers.sql
seed/entity_types.sql
seed/sources.sql
```

---

## 11. Series temporales (`observations`) — capa nacional/contextual

Para datos que llegan como **puntos fechados de una serie** (cotización diaria de un índice o acción, variable monetaria del BCRA), no usar `properties` (pensada para el *estado vigente* de una entidad, una fila por cambio) ni `legal_entity_records` (hechos jurídicos de IGJ, `record_type` fijo). Usar la tabla `observations` (`db/12_observations.sql`).

**Cuándo usar cada tabla:**
- `properties` → el valor *actual* de un atributo de una entidad (`price_usd`, `rating`).
- `legal_entity_records` → hechos jurídicos repetibles de IGJ (domicilio, autoridades, asambleas, balances).
- `observations` → una serie temporal: muchos puntos fechados, misma entidad, mismo `series_key`, uno por período.

**`series_key`** sigue la misma regex que las property keys: `^[a-z][a-z0-9_]{0,149}$`, con la convención `<fuente>_<sujeto>_<medida>` (ej.: `ambito_merval_close`, `byma_ypfd_price`, `bcra_var_1`). Es estable en el tiempo aunque cambie la descripción humana de la serie (esa vive en una `property` o en `payload`).

**`unit`** usa un vocabulario corto: `ARS`, `USD`, `pct`, `index`, `shares`.

**Revisión, no reemplazo:** un valor que cambia genera una **fila nueva** con otro `record_key` (hash de `series_key|observed_period|payload`), nunca un `UPDATE` sobre el valor. `ON DUPLICATE KEY UPDATE` sólo toca `last_seen_at`. Ver `scrapers/shared/db_helpers.bulk_upsert_observations`.

**Entidades nacionales sin geografía:** `MarketIndex`, `Security`, `EconomicSeries` y `Regulation` se crean siempre con `lat=NULL, lng=NULL`. Esto es intencional: son series de alcance nacional, no ubicaciones de CABA, y no deben aparecer en `scripts/caba_readiness.py` como "entidades sin asignar".
