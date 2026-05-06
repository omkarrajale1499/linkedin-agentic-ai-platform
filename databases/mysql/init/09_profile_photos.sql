USE linkedin_ds;

-- Data URLs need more than VARCHAR(500); recruiters need a photo column.
ALTER TABLE members MODIFY COLUMN profile_photo_url LONGTEXT NULL;

ALTER TABLE recruiters
  ADD COLUMN profile_photo_url LONGTEXT NULL COMMENT 'Profile photo (JPEG data URL or HTTPS URL)';
