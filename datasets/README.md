## Dataset Seeding (Section 9)

Place dataset CSV files in `datasets/raw` before running `python databases/seed.py`.

Useful run modes:

- `python databases/seed.py` -> full-scale seed
- `python databases/seed.py --fast` -> quick local verification seed
- `python databases/seed.py --keep --fast` -> quick top-up without wiping

Expected filenames:

- `datasets/raw/jobs.csv`
- `datasets/raw/resumes.csv`

Optional: override paths with environment variables:

- `SEED_JOBS_CSV`
- `SEED_RESUMES_CSV`

The seeder maps common column names automatically:

- Jobs: `title`, `job_title`, `description`, `company`, `city`, `state`, `country`, `skills`
- Resumes: `resume`, `resume_text`, `resume_str`, `category`, `skills`

If a field is missing, the script fills it with synthetic fallback data so the pipeline still runs.
