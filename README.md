# Python PostgreSQL Migration Deployer

This project clones or updates a Git repository, sorts timestamp-named SQL files, checks which migrations are already recorded, applies pending migrations, and logs successful executions.

## Folder structure

```text
postgres_python_migration_deployer/
├── deploy.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── logs/
└── migrations/
    ├── 20261120090000_create_authors.sql
    └── 20261120100000_create_books.sql
```

## Migration filename format

Use `YYYYMMDDHHMMSS_description.sql`, for example `20261120103000_add_book_price.sql`. Files are sorted by filename. Do not edit a migration after it has been applied; create a new migration instead.

## Requirements and setup

- Python 3.10 or newer
- Git installed and available on PATH
- PostgreSQL reachable using the configured connection details

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Set the environment variables listed in `.env.example`. Do not commit real passwords. Example PowerShell setup:

```powershell
$env:MIGRATIONS_REPO_URL="https://github.com/your-org/your-migrations-repo.git"
$env:PGHOST="localhost"
$env:PGDATABASE="bookstore"
$env:PGUSER="postgres"
$env:PGPASSWORD="your-password"
```

## Run

Preview without executing migration SQL:

```bash
python deploy.py --dry-run
```

Apply pending migrations:

```bash
python deploy.py
```

Optional arguments include `--repo-url`, `--branch`, `--repo-dir`, `--sql-dir`, and `--log-file`.

## Tracking and transaction behavior

The tool creates `schema_version` and `migration_log` tables. Each migration runs in its own transaction; the migration log insert and current schema version update are committed with the migration. If a migration fails, its transaction is rolled back. A PostgreSQL advisory transaction lock helps serialize deployer instances.

## Important cautions

SQL migration files are executable database code: only deploy from a trusted repository and review the SQL first. Back up important data and test in a development or staging database. This sample does not automatically reverse already committed migrations; use a new forward migration to correct a change. Some PostgreSQL statements (such as `CREATE INDEX CONCURRENTLY`) cannot run inside a transaction block and need a separate non-transactional migration workflow.
