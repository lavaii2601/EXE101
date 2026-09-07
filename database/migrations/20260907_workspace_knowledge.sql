-- Phase 5 ("Advanced workspace and AI", design doc section 8.7 / 15): a third
-- knowledge tier alongside the existing global (user_id IS NULL) and personal
-- (user_id set) rows -- workspace-curated policy/template/FAQ docs, owner/admin
-- authored, visible to every active member of that Business workspace.
--
-- Nullable by design (unlike chat_sessions/history/session_memory's mandatory
-- workspace_id): a knowledge_documents row is global OR personal OR
-- workspace-scoped, never required to carry a workspace_id. No backfill --
-- every existing row keeps meaning exactly what it means today (global or
-- personal). Safe to run multiple times.

ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS created_by_user_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_documents_workspace_fkey') THEN
        ALTER TABLE knowledge_documents
            ADD CONSTRAINT knowledge_documents_workspace_fkey
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_documents_created_by_fkey') THEN
        ALTER TABLE knowledge_documents
            ADD CONSTRAINT knowledge_documents_created_by_fkey
            FOREIGN KEY (created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_workspace ON knowledge_documents (workspace_id);
