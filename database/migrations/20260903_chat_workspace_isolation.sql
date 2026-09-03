-- Phase 3 ("Bob Core") tenant isolation: chat_sessions, history, and
-- session_memory gain workspace_id so a workspace switch never leaks
-- conversation memory across tenants. See design doc section 8.7's "cache/
-- conversation context must not leak across tenants" requirement and
-- ke_hoach_6_giai_doan_note.txt's "workspace memory isolation" priority.
--
-- Existing rows all predate any Business workspace, so they backfill
-- unambiguously to the owning user's personal workspace. Safe to run
-- multiple times.

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE history ADD COLUMN IF NOT EXISTS workspace_id UUID;
ALTER TABLE session_memory ADD COLUMN IF NOT EXISTS workspace_id UUID;

INSERT INTO workspaces (type, name, owner_user_id, status)
SELECT 'personal', 'Personal', u.user_id, 'active'
FROM users u
WHERE NOT EXISTS (
    SELECT 1 FROM workspaces w WHERE w.owner_user_id = u.user_id AND w.type = 'personal'
)
ON CONFLICT (owner_user_id) WHERE type = 'personal' DO NOTHING;

INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
SELECT w.id, w.owner_user_id, 'owner', 'active'
FROM workspaces w
WHERE w.type = 'personal'
ON CONFLICT (workspace_id, user_id) DO NOTHING;

UPDATE chat_sessions cs
SET workspace_id = w.id
FROM workspaces w
WHERE w.owner_user_id = cs.user_id AND w.type = 'personal' AND cs.workspace_id IS NULL;

UPDATE history h
SET workspace_id = cs.workspace_id
FROM chat_sessions cs
WHERE h.chat_session_id = cs.id AND h.workspace_id IS NULL;

UPDATE history h
SET workspace_id = w.id
FROM workspaces w
WHERE w.owner_user_id = h.user_id AND w.type = 'personal' AND h.workspace_id IS NULL;

UPDATE session_memory sm
SET workspace_id = cs.workspace_id
FROM chat_sessions cs
WHERE sm.chat_session_id = cs.id AND sm.workspace_id IS NULL;

ALTER TABLE chat_sessions ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE history ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE session_memory ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chat_sessions_workspace_fkey') THEN
        ALTER TABLE chat_sessions
            ADD CONSTRAINT chat_sessions_workspace_fkey
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'history_workspace_fkey') THEN
        ALTER TABLE history
            ADD CONSTRAINT history_workspace_fkey
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'session_memory_workspace_fkey') THEN
        ALTER TABLE session_memory
            ADD CONSTRAINT session_memory_workspace_fkey
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_workspace ON chat_sessions (workspace_id, user_id);
CREATE INDEX IF NOT EXISTS idx_history_workspace ON history (workspace_id);
CREATE INDEX IF NOT EXISTS idx_session_memory_workspace ON session_memory (workspace_id);
