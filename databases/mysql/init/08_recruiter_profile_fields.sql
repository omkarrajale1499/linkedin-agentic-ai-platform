USE linkedin_ds;

-- Richer recruiter profiles (demo + future UI)
ALTER TABLE recruiters
  ADD COLUMN headline VARCHAR(280) NULL DEFAULT NULL COMMENT 'Professional headline' AFTER role,
  ADD COLUMN about TEXT NULL COMMENT 'Bio / About section' AFTER headline,
  ADD COLUMN location VARCHAR(200) NULL COMMENT 'Office or region shown on profile' AFTER about,
  ADD COLUMN specialties VARCHAR(800) NULL COMMENT 'Comma-separated hiring focus areas' AFTER location,
  ADD COLUMN hiring_highlights TEXT NULL COMMENT 'JSON array string of profile bullet highlights' AFTER specialties;
