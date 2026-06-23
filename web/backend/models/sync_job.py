from models import postgres_db as pg


class SyncJob:
    @staticmethod
    def start(user_id, job_type, metadata=None, db_path=None):
        if not pg.enabled():
            return None
        user_id = user_id or pg.user_id_from_db_path(db_path)
        pg.ensure_user(user_id)
        with pg.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO sync_jobs (user_id, job_type, status, started_at, metadata)
                VALUES (%s, %s, 'running', NOW(), %s)
                RETURNING id
                """,
                (user_id, job_type, pg.json_value(metadata or {})),
            ).fetchone()
            return row['id'] if row else None

    @staticmethod
    def finish(job_id, status='success', metadata=None, error_message=None):
        if not pg.enabled() or not job_id:
            return False
        with pg.connection() as conn:
            cur = conn.execute(
                """
                UPDATE sync_jobs
                SET status = %s,
                    finished_at = NOW(),
                    error_message = %s,
                    metadata = COALESCE(metadata, '{}'::JSONB) || %s
                WHERE id = %s
                """,
                (status, error_message, pg.json_value(metadata or {}), job_id),
            )
            return cur.rowcount > 0
