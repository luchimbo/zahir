-- ============================================================
-- 08_constraints.sql
-- Constraints adicionales de integridad de negocio.
-- Los constraints de cada tabla ya están en sus propios archivos.
-- Aquí van los que requieren que todas las tablas existan.
-- ============================================================

-- Asegurar que canonical_id siempre apunta a una entidad canónica
-- (es decir, canonical_id no puede apuntar a otra entidad que también es duplicado)
-- Esto se verifica en el Entity Resolver antes de insertar, no con constraint
-- para evitar dependencias circulares en cadena.

-- Comentario: este archivo existe para futuros constraints inter-tabla.
-- Por ahora los constraints están distribuidos en cada tabla.
