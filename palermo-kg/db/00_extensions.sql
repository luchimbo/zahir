-- ============================================================
-- 00_extensions.sql
-- Extensiones de PostgreSQL necesarias para el proyecto.
-- Ejecutar una sola vez al crear la base de datos.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- búsqueda fuzzy por nombre
CREATE EXTENSION IF NOT EXISTS "unaccent";   -- ignorar tildes en búsquedas
