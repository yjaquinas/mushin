-- 0006_sub_tally_slug.sql
-- Public/private profile feature (Phase 1): add sub_tally.slug, used in the
-- public activity URL /u/{username}/{activity-slug}. Backfills a slug for
-- every existing row, then adds a per-owner unique partial index.
--
-- Slugify rules: lowercase, fold a common set of accented Latin characters to
-- their plain ASCII equivalent, map every other non [a-z0-9] character (or
-- run of them) to '-', collapse repeated '-' to one, and trim leading and
-- trailing '-'. Characters from non-Latin scripts (e.g. Hangul, CJK) are not
-- transliterated -- they simply become '-' and collapse away. If nothing
-- alphanumeric survives, fall back to 'sub-tally-<id>' (unique on its own).
--
-- De-duplication: rows are ordered by id within each owner_id. The first row
-- with a given slug keeps it -- later rows with the same slug get '-2', '-3',
-- and so on appended to their *original* slug. Nine passes resolve collisions,
-- including cases where an appended suffix (e.g. 'workout-2') collides with
-- another row's natural slug -- covers up to 10 same-named rows per owner,
-- far beyond any real account. Results may look slightly odd in pathological
-- cases (e.g. 'workout-2-2') but are deterministic, non-null, and unique.
--
-- The migration runner (app/models/migrate.py) splits this file on the
-- semicolon character and runs each statement in one transaction -- no
-- executescript(), so a multi-statement, CTE-based approach is fine here.

ALTER TABLE sub_tally ADD COLUMN slug TEXT;

-- Step 1: per-character slugify into `slug` via a recursive CTE: fold a
-- core set of accented Latin characters, lowercase, then map each character
-- to itself if [a-z0-9] or to '-' otherwise.
WITH RECURSIVE charwalk(id, acc, src, i) AS (
    SELECT id, '', LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(name, 'á', 'a'), 'à', 'a'), 'â', 'a'), 'ä', 'a'), 'ã', 'a'), 'å', 'a'), 'é', 'e'), 'è', 'e'), 'ê', 'e'), 'ë', 'e'), 'í', 'i'), 'ì', 'i'), 'î', 'i'), 'ï', 'i'), 'ó', 'o'), 'ò', 'o'), 'ô', 'o'), 'ö', 'o'), 'õ', 'o'), 'ú', 'u'), 'ù', 'u'), 'û', 'u'), 'ü', 'u'), 'ñ', 'n'), 'ç', 'c'), 'ý', 'y')), 1
    FROM sub_tally
    UNION ALL
    SELECT id,
        acc || CASE
            WHEN substr(src, i, 1) GLOB '[a-z0-9]' THEN substr(src, i, 1)
            ELSE '-'
        END,
        src, i + 1
    FROM charwalk
    WHERE i <= length(src)
)
UPDATE sub_tally SET slug = (
    SELECT acc FROM charwalk c WHERE c.id = sub_tally.id AND c.i = length(c.src) + 1
);

-- Step 2: collapse runs of '-' (each pass halves run length, 10 passes
-- handles runs up to 1024) and trim leading/trailing '-'.
UPDATE sub_tally SET slug = TRIM(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(slug, '--', '-'), '--', '-'), '--', '-'), '--', '-'), '--', '-'), '--', '-'), '--', '-'), '--', '-'), '--', '-'), '--', '-'), '-');

-- Step 3: fall back to a guaranteed-unique slug for names with nothing
-- alphanumeric in them (e.g. '!!!').
UPDATE sub_tally SET slug = 'sub-tally-' || id WHERE slug = '' OR slug IS NULL;

-- Step 4: de-duplicate per owner_id. base_slug holds the pre-dedup value so
-- repeated passes always append to the original, not to an already-suffixed
-- slug.
ALTER TABLE sub_tally ADD COLUMN base_slug TEXT;

UPDATE sub_tally SET base_slug = slug;

UPDATE sub_tally
SET slug = base_slug || '-' || 2
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 3
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 4
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 5
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 6
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 7
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 8
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 9
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

UPDATE sub_tally
SET slug = base_slug || '-' || 10
WHERE id IN (
    SELECT a.id FROM sub_tally a
    JOIN sub_tally b ON b.owner_id = a.owner_id AND b.slug = a.slug AND b.id < a.id
);

ALTER TABLE sub_tally DROP COLUMN base_slug;

-- Unique per-owner slug among active (non-archived) sub-tallies, matching
-- the partial-index convention used elsewhere for archived rows.
CREATE UNIQUE INDEX ux_sub_tally_owner_slug
    ON sub_tally (owner_id, slug)
    WHERE archived_at IS NULL;
