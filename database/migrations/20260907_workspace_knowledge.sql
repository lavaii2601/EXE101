-- Originally added a third, workspace-curated knowledge tier (workspace_id,
-- FK'd to workspaces(id)) alongside global/personal knowledge_documents
-- rows, plus created_by_user_id. Business mode is gone and workspaces no
-- longer exists, so the workspace_id column + FK + index are removed here
-- (20261106_remove_business_workspaces.sql already dropped the live
-- column; re-adding it here would just recreate a dead column, and its FK
-- would fail with UndefinedTable on every replay from here on --
-- deploy_postgres_schema.py re-applies every migration file on every
-- deploy with no tracking table).
--
-- created_by_user_id is NOT workspace-specific -- models/knowledge.py and
-- services/knowledge_service.py still read/write it for personal and
-- global documents -- so it stays.

ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS created_by_user_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_documents_created_by_fkey') THEN
        ALTER TABLE knowledge_documents
            ADD CONSTRAINT knowledge_documents_created_by_fkey
            FOREIGN KEY (created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL;
    END IF;
END;
$$;
