-- Phase 3 ("Bob Core và Status Report", design doc sections 8.4-8.5, 9.6):
-- shared projects/tasks and manual Status Reports. Postgres-only, same
-- justification as workspaces/subscriptions -- inherently cross-user
-- business data. Safe to run multiple times.
--
-- Permission model note: v1 deliberately does not add a separate
-- project_members join table -- it reuses the existing owner_user_id
-- column as the single per-project delegate, while workspace membership
-- continues to gate baseline visibility of 'workspace'-visibility rows.
-- See postgres_schema.sql's copy of this DDL and models/project.py for
-- the full rationale.

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'planning',
    visibility TEXT NOT NULL DEFAULT 'workspace',
    owner_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    start_date DATE,
    due_date DATE,
    created_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    updated_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT projects_status_check CHECK (
        status IN ('planning', 'active', 'on_hold', 'completed', 'archived')
    ),
    CONSTRAINT projects_visibility_check CHECK (visibility IN ('workspace', 'private')),
    CONSTRAINT projects_date_range_check CHECK (
        start_date IS NULL OR due_date IS NULL OR due_date >= start_date
    )
);

CREATE INDEX IF NOT EXISTS idx_projects_workspace_status
    ON projects (workspace_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_projects_owner
    ON projects (owner_user_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'medium',
    visibility TEXT NOT NULL DEFAULT 'workspace',
    assignee_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    due_date DATE,
    source TEXT NOT NULL DEFAULT 'manual',
    blocker TEXT,
    created_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    updated_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT tasks_status_check CHECK (
        status IN ('todo', 'in_progress', 'blocked', 'done', 'cancelled')
    ),
    CONSTRAINT tasks_priority_check CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    CONSTRAINT tasks_visibility_check CHECK (visibility IN ('workspace', 'private'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status
    ON tasks (workspace_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_project
    ON tasks (project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_assignee
    ON tasks (assignee_user_id, status) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS status_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    author_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    report_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT NOT NULL DEFAULT 'draft',
    visibility TEXT NOT NULL DEFAULT 'workspace',
    done_text TEXT NOT NULL DEFAULT '',
    doing_text TEXT NOT NULL DEFAULT '',
    blocked_text TEXT NOT NULL DEFAULT '',
    next_text TEXT NOT NULL DEFAULT '',
    risks_text TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ,
    created_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    updated_by_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT status_reports_status_check CHECK (status IN ('draft', 'published')),
    CONSTRAINT status_reports_visibility_check CHECK (visibility IN ('workspace', 'private'))
);

CREATE INDEX IF NOT EXISTS idx_status_reports_workspace_status
    ON status_reports (workspace_id, status, report_date DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_status_reports_author
    ON status_reports (author_user_id, report_date DESC) WHERE deleted_at IS NULL;

DROP TRIGGER IF EXISTS trg_projects_updated_at ON projects;
CREATE TRIGGER trg_projects_updated_at
BEFORE UPDATE ON projects
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tasks_updated_at ON tasks;
CREATE TRIGGER trg_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_status_reports_updated_at ON status_reports;
CREATE TRIGGER trg_status_reports_updated_at
BEFORE UPDATE ON status_reports
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
