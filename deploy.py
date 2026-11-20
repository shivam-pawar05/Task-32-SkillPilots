#!/usr/bin/env python3
"""Apply timestamp-ordered SQL migrations from a Git repository to PostgreSQL."""
import argparse
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

PATTERN = re.compile(r'^\d{14}_[A-Za-z0-9_.-]+\.sql$')
LOCK_ID = 72819461


def git(args, cwd=None):
    subprocess.run(['git', *args], cwd=str(cwd) if cwd else None, check=True)


def prepare_repo(url, repo_dir, branch):
    if (repo_dir / '.git').exists():
        logging.info('Updating migrations repository: %s', repo_dir)
        git(['fetch', 'origin', branch], repo_dir)
        git(['checkout', branch], repo_dir)
        git(['pull', '--ff-only', 'origin', branch], repo_dir)
    else:
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        logging.info('Cloning migrations repository: %s', repo_dir)
        git(['clone', '--branch', branch, '--depth', '1', url, str(repo_dir)])


def main():
    parser = argparse.ArgumentParser(description='Deploy pending PostgreSQL SQL migrations.')
    parser.add_argument('--repo-url', default=os.getenv('MIGRATIONS_REPO_URL'))
    parser.add_argument('--branch', default=os.getenv('MIGRATIONS_BRANCH', 'main'))
    parser.add_argument('--repo-dir', type=Path, default=Path(os.getenv('MIGRATIONS_DIR', './migration-repo')))
    parser.add_argument('--sql-dir', default=os.getenv('MIGRATIONS_SQL_DIR', 'migrations'))
    parser.add_argument('--dry-run', action='store_true', help='Show pending migrations without executing them.')
    parser.add_argument('--log-file', type=Path, default=Path(os.getenv('DEPLOY_LOG', './logs/deploy.log')))
    args = parser.parse_args()
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(args.log_file, encoding='utf-8'), logging.StreamHandler(sys.stdout)])
    if not args.repo_url:
        logging.error('Set MIGRATIONS_REPO_URL or pass --repo-url.')
        return 2
    try:
        prepare_repo(args.repo_url, args.repo_dir, args.branch)
        migration_dir = args.repo_dir / args.sql_dir
        if not migration_dir.is_dir():
            raise FileNotFoundError(f'Migration directory not found: {migration_dir}')
        migrations = sorted(p for p in migration_dir.iterdir() if p.is_file() and PATTERN.match(p.name))
        db = dict(host=os.getenv('PGHOST', 'localhost'), port=int(os.getenv('PGPORT', '5432')),
                  dbname=os.getenv('PGDATABASE', 'postgres'), user=os.getenv('PGUSER', 'postgres'),
                  password=os.getenv('PGPASSWORD', ''), connect_timeout=10)
        logging.info('Connecting to database %s at %s:%s', db['dbname'], db['host'], db['port'])
        with psycopg2.connect(**db) as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TABLE IF NOT EXISTS schema_version (
                    id SMALLINT PRIMARY KEY CHECK (id = 1), version VARCHAR(255) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
                cur.execute("INSERT INTO schema_version(id, version) VALUES (1, '0') ON CONFLICT (id) DO NOTHING")
                cur.execute('''CREATE TABLE IF NOT EXISTS migration_log (
                    migration_name VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    execution_seconds DOUBLE PRECISION NOT NULL DEFAULT 0)''')
                cur.execute('SELECT migration_name FROM migration_log')
                applied = {row[0] for row in cur.fetchall()}
            pending = [p for p in migrations if p.name not in applied]
            logging.info('%d pending migration(s).', len(pending))
            for path in pending:
                logging.info('%s', '[DRY RUN] Would apply ' + path.name if args.dry_run else 'Applying ' + path.name)
                if args.dry_run:
                    continue
                sql_text = path.read_text(encoding='utf-8')
                if not sql_text.strip():
                    logging.warning('Skipping empty migration %s', path.name)
                    continue
                started = time.perf_counter()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
                            cur.execute(sql_text)
                            elapsed = time.perf_counter() - started
                            cur.execute('INSERT INTO migration_log(migration_name, execution_seconds) VALUES (%s, %s)', (path.name, elapsed))
                            cur.execute('UPDATE schema_version SET version=%s, applied_at=NOW() WHERE id=1', (path.name,))
                    logging.info('Applied %s in %.3f seconds', path.name, elapsed)
                except Exception:
                    logging.exception('Migration %s failed; transaction rolled back.', path.name)
                    raise
        logging.info('Deployment completed.')
        return 0
    except (OSError, subprocess.CalledProcessError, psycopg2.Error, RuntimeError) as exc:
        logging.error('Deployment stopped: %s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
