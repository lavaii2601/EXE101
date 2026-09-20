"""Permanent, user-initiated FlowMate account deletion.

Personal data is removed immediately. A Business workspace with another
active member is transferred before the user row is deleted, so one person's
privacy request never destroys collaborators' shared work. A sole-member
Business workspace is deleted with the account through PostgreSQL cascades.
"""

import logging
import os
import sqlite3

from config import Config
from models import postgres_db as pg
from models.user import User
from utils.user_context import (
    CredentialStoreError,
    delete_google_credentials,
    get_user_db_path,
)


logger = logging.getLogger(__name__)


class AccountDeletionError(RuntimeError):
    """Raised when an account cannot be completely and safely deleted."""


def _remove_private_files(user_id):
    """Remove per-user SQLite data and cached Google credentials."""
    try:
        delete_google_credentials(user_id)
    except CredentialStoreError as exc:
        raise AccountDeletionError(
            'Could not invalidate the connected Google credentials.'
        ) from exc

    db_path = os.path.abspath(get_user_db_path(user_id))
    users_dir = os.path.abspath(os.path.join(os.path.dirname(Config.DATABASE_PATH), 'users'))
    if os.path.commonpath((db_path, users_dir)) != users_dir:
        raise AccountDeletionError('Resolved user data path is outside the user-data directory.')

    for candidate in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
        try:
            os.remove(candidate)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise AccountDeletionError('Could not remove all local user data.') from exc


def _delete_postgres_account(user_id):
    transferred = []
    deleted_workspaces = []
    with pg.connection() as conn:
        owned_workspaces = conn.execute(
            """
            SELECT id, name
            FROM workspaces
            WHERE owner_user_id = %s AND type = 'business'
            ORDER BY created_at ASC
            FOR UPDATE
            """,
            (user_id,),
        ).fetchall()

        for workspace in owned_workspaces:
            replacement = conn.execute(
                """
                SELECT user_id
                FROM workspace_memberships
                WHERE workspace_id = %s
                  AND user_id <> %s
                  AND status = 'active'
                ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END,
                         joined_at ASC,
                         id ASC
                LIMIT 1
                FOR UPDATE
                """,
                (workspace['id'], user_id),
            ).fetchone()
            if replacement:
                replacement_user_id = replacement['user_id']
                conn.execute(
                    """
                    UPDATE workspace_memberships
                    SET role = 'owner', updated_at = NOW()
                    WHERE workspace_id = %s AND user_id = %s
                    """,
                    (workspace['id'], replacement_user_id),
                )
                conn.execute(
                    """
                    UPDATE workspaces
                    SET owner_user_id = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (replacement_user_id, workspace['id']),
                )
                transferred.append(workspace.get('name') or str(workspace['id']))
            else:
                # The workspace still points to the deleting user and is
                # intentionally removed by ON DELETE CASCADE below.
                deleted_workspaces.append(workspace.get('name') or str(workspace['id']))

        # Personal learned knowledge predates its FK and therefore needs an
        # explicit delete. Workspace documents remain with the workspace;
        # their created_by_user_id is nulled by its FK.
        conn.execute(
            """
            DELETE FROM knowledge_documents
            WHERE user_id = %s AND workspace_id IS NULL
            """,
            (user_id,),
        )
        deleted_user = conn.execute(
            "DELETE FROM users WHERE user_id = %s",
            (user_id,),
        )
        if deleted_user.rowcount != 1:
            raise AccountDeletionError('Account was not found or was already deleted.')

    return {
        'transferred_business_workspaces': len(transferred),
        'deleted_business_workspaces': len(deleted_workspaces),
    }


def _delete_sqlite_account(user_id):
    User.init_db()
    conn = sqlite3.connect(Config.DATABASE_PATH)
    try:
        try:
            conn.execute(
                "DELETE FROM knowledge_documents WHERE user_id = ?",
                (user_id,),
            )
        except sqlite3.OperationalError as exc:
            if 'no such table' not in str(exc).lower():
                raise
        deleted_user = conn.execute(
            "DELETE FROM users WHERE user_id = ?",
            (user_id,),
        )
        if deleted_user.rowcount != 1:
            raise AccountDeletionError('Account was not found or was already deleted.')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        'transferred_business_workspaces': 0,
        'deleted_business_workspaces': 0,
    }


def delete_account(user_id):
    user_id = str(user_id or '').strip()
    if not user_id or user_id == 'default':
        raise AccountDeletionError('A signed-in account is required.')

    # Invalidate credentials and remove local private files before deleting
    # the durable identity. If local cleanup fails, the transaction never
    # starts and the user can safely retry.
    _remove_private_files(user_id)
    result = (
        _delete_postgres_account(user_id)
        if pg.enabled()
        else _delete_sqlite_account(user_id)
    )
    logger.info('FlowMate account permanently deleted: %s', user_id)
    return result
