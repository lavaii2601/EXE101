// ---------------------------------------------------------------------------
// Work Hub (projects/tasks) and Status Reports (Phase 3, design doc 8.4-8.5)
// ---------------------------------------------------------------------------

function workHubStatusLabel(status) {
    const labels = {
        planning: ui('Lên kế hoạch', 'Planning'),
        active: ui('Đang triển khai', 'Active'),
        on_hold: ui('Tạm dừng', 'On hold'),
        completed: ui('Hoàn thành', 'Completed'),
        archived: ui('Lưu trữ', 'Archived'),
        todo: ui('Cần làm', 'To do'),
        in_progress: ui('Đang làm', 'In progress'),
        blocked: ui('Đang vướng', 'Blocked'),
        done: ui('Xong', 'Done'),
        cancelled: ui('Đã huỷ', 'Cancelled'),
        low: ui('Thấp', 'Low'),
        medium: ui('Trung bình', 'Medium'),
        high: ui('Cao', 'High'),
        urgent: ui('Khẩn cấp', 'Urgent'),
    };
    return labels[status] || status;
}

function workHubBadgeClass(status) {
    if (status === 'blocked') return 'work-hub-badge work-hub-badge-blocked';
    if (status === 'done' || status === 'completed') return 'work-hub-badge work-hub-badge-done';
    return 'work-hub-badge';
}

function currentOrgCanManage() {
    const active = currentOrgWorkspace();
    return !!active && (active.member_role === 'owner' || active.member_role === 'admin');
}

async function loadWorkHubDashboard() {
    const dashboardEl = document.getElementById('workHubDashboard');
    if (!dashboardEl) return;
    let dashboard;
    try {
        const resp = await apiFetch(`${API_BASE}/work-hub/dashboard`);
        const data = await resp.json();
        if (!resp.ok || !data.success) return;
        dashboard = data.dashboard;
    } catch (err) {
        console.warn('loadWorkHubDashboard failed', err);
        return;
    }
    const activeProjects = (dashboard.project_counts?.active || 0) + (dashboard.project_counts?.planning || 0);
    const openTasks = (dashboard.task_counts?.todo || 0) + (dashboard.task_counts?.in_progress || 0);
    const tiles = [
        { value: dashboard.total_projects, label: ui('Dự án', 'Projects') },
        { value: activeProjects, label: ui('Đang triển khai', 'Active') },
        { value: openTasks, label: ui('Nhiệm vụ cần làm', 'Open tasks') },
        { value: dashboard.overdue_tasks, label: ui('Quá hạn', 'Overdue'), warning: dashboard.overdue_tasks > 0 },
        { value: dashboard.active_members, label: ui('Thành viên', 'Members') },
    ];
    dashboardEl.hidden = false;
    dashboardEl.innerHTML = tiles.map((tile) => `
        <div class="work-hub-stat-tile${tile.warning ? ' work-hub-stat-warning' : ''}">
            <strong>${escapeHtml(String(tile.value ?? 0))}</strong>
            <small>${escapeHtml(tile.label)}</small>
        </div>
    `).join('');
}

async function loadWorkHubPage() {
    const emptyEl = document.getElementById('workHubEmpty');
    const contentEl = document.getElementById('workHubContent');
    const dashboardEl = document.getElementById('workHubDashboard');
    const newProjectCard = document.getElementById('workHubNewProjectCard');
    const active = currentOrgWorkspace();
    if (!active || active.type !== 'business') {
        if (emptyEl) emptyEl.hidden = false;
        if (contentEl) contentEl.hidden = true;
        if (dashboardEl) dashboardEl.hidden = true;
        return;
    }
    if (emptyEl) emptyEl.hidden = true;
    if (contentEl) contentEl.hidden = false;
    if (newProjectCard) newProjectCard.hidden = !currentOrgCanManage();

    loadWorkHubDashboard().catch((err) => console.warn('loadWorkHubDashboard failed', err));

    try {
        const resp = await apiFetch(`${API_BASE}/projects`);
        const data = await resp.json();
        if (resp.ok && data.success) workHubProjects = data.projects || [];
    } catch (err) {
        console.warn('loadWorkHubPage projects failed', err);
    }
    if (workHubSelectedProjectId && !workHubProjects.some((p) => p.id === workHubSelectedProjectId)) {
        workHubSelectedProjectId = null;
    }
    renderWorkHubProjects();

    const tasksCard = document.getElementById('workHubTasksCard');
    if (workHubSelectedProjectId) {
        await loadWorkHubTasks(workHubSelectedProjectId);
    } else if (tasksCard) {
        tasksCard.hidden = true;
    }
}

function renderWorkHubProjects() {
    const listEl = document.getElementById('workHubProjectsList');
    if (!listEl) return;
    if (!workHubProjects.length) {
        listEl.innerHTML = `<div class="chat-session-empty">${ui('Chưa có dự án nào.', 'No projects yet.')}</div>`;
        return;
    }
    const canManage = currentOrgCanManage();
    listEl.innerHTML = workHubProjects.map((project) => `
        <div class="work-hub-item-row${project.id === workHubSelectedProjectId ? ' active' : ''}" data-project-id="${escapeHtml(project.id)}">
            <div class="work-hub-item-info">
                <strong>${escapeHtml(project.name)}</strong>
                <small>${project.due_date ? `${ui('Hạn', 'Due')} ${escapeHtml(project.due_date)}` : ui('Không có hạn', 'No due date')}</small>
            </div>
            <span class="${workHubBadgeClass(project.status)}">${escapeHtml(workHubStatusLabel(project.status))}</span>
            ${canManage ? `<div class="work-hub-item-actions"><button type="button" class="btn-secondary" data-delete-project="${escapeHtml(project.id)}">${ui('Xoá', 'Delete')}</button></div>` : ''}
        </div>
    `).join('');
    listEl.querySelectorAll('[data-project-id]').forEach((row) => {
        row.addEventListener('click', (event) => {
            if (event.target.closest('[data-delete-project]')) return;
            selectWorkHubProject(row.getAttribute('data-project-id'));
        });
    });
    listEl.querySelectorAll('[data-delete-project]').forEach((btn) => {
        btn.addEventListener('click', (event) => {
            event.stopPropagation();
            deleteWorkHubProject(btn.getAttribute('data-delete-project'));
        });
    });
}

function selectWorkHubProject(projectId) {
    workHubSelectedProjectId = projectId;
    renderWorkHubProjects();
    loadWorkHubTasks(projectId);
}

async function loadWorkHubTasks(projectId) {
    const card = document.getElementById('workHubTasksCard');
    const label = document.getElementById('workHubTasksLabel');
    const project = workHubProjects.find((p) => p.id === projectId);
    if (card) card.hidden = false;
    if (label) label.textContent = project ? `${ui('NHIỆM VỤ', 'TASKS')} · ${project.name}` : ui('NHIỆM VỤ', 'TASKS');
    try {
        const resp = await apiFetch(`${API_BASE}/tasks?project_id=${encodeURIComponent(projectId)}`);
        const data = await resp.json();
        if (resp.ok && data.success) workHubTasks = data.tasks || [];
    } catch (err) {
        console.warn('loadWorkHubTasks failed', err);
    }
    renderWorkHubTasks();
}

function renderWorkHubTasks() {
    const listEl = document.getElementById('workHubTasksList');
    if (!listEl) return;
    if (!workHubTasks.length) {
        listEl.innerHTML = `<div class="chat-session-empty">${ui('Chưa có nhiệm vụ nào.', 'No tasks yet.')}</div>`;
        return;
    }
    listEl.innerHTML = workHubTasks.map((task) => `
        <div class="work-hub-item-row" data-task-id="${escapeHtml(task.id)}">
            <div class="work-hub-item-info">
                <strong>${escapeHtml(task.title)}</strong>
                <small>${escapeHtml(workHubStatusLabel(task.priority))}${task.due_date ? ` · ${escapeHtml(task.due_date)}` : ''}</small>
            </div>
            <span class="${workHubBadgeClass(task.status)}" data-cycle-task="${escapeHtml(task.id)}" title="${ui('Bấm để đổi trạng thái', 'Click to change status')}">${escapeHtml(workHubStatusLabel(task.status))}</span>
            <div class="work-hub-item-actions"><button type="button" class="btn-secondary" data-delete-task="${escapeHtml(task.id)}">${ui('Xoá', 'Delete')}</button></div>
        </div>
    `).join('');
    listEl.querySelectorAll('[data-cycle-task]').forEach((badge) => {
        badge.addEventListener('click', () => cycleWorkHubTaskStatus(badge.getAttribute('data-cycle-task')));
    });
    listEl.querySelectorAll('[data-delete-task]').forEach((btn) => {
        btn.addEventListener('click', () => deleteWorkHubTask(btn.getAttribute('data-delete-task')));
    });
}

async function cycleWorkHubTaskStatus(taskId) {
    const task = workHubTasks.find((t) => t.id === taskId);
    if (!task) return;
    const cycle = ['todo', 'in_progress', 'blocked', 'done'];
    const nextStatus = cycle[(cycle.indexOf(task.status) + 1) % cycle.length];
    try {
        const resp = await apiFetch(`${API_BASE}/tasks/${task.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: nextStatus }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'update_failed');
        task.status = data.task.status;
        renderWorkHubTasks();
    } catch (err) {
        showNotification(ui('Không cập nhật được nhiệm vụ', 'Could not update task'), 'error');
    }
}

async function deleteWorkHubTask(taskId) {
    if (!confirm(ui('Xoá nhiệm vụ này?', 'Delete this task?'))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/tasks/${taskId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'delete_failed');
        workHubTasks = workHubTasks.filter((t) => t.id !== taskId);
        renderWorkHubTasks();
    } catch (err) {
        showNotification(ui('Không xoá được nhiệm vụ', 'Could not delete task'), 'error');
    }
}

async function deleteWorkHubProject(projectId) {
    if (!confirm(ui('Xoá dự án này? Toàn bộ nhiệm vụ trong dự án cũng sẽ bị xoá.', 'Delete this project? All of its tasks will be deleted too.'))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/projects/${projectId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'delete_failed');
        workHubProjects = workHubProjects.filter((p) => p.id !== projectId);
        if (workHubSelectedProjectId === projectId) {
            workHubSelectedProjectId = null;
            document.getElementById('workHubTasksCard')?.setAttribute('hidden', '');
        }
        renderWorkHubProjects();
    } catch (err) {
        showNotification(ui('Không xoá được dự án', 'Could not delete project'), 'error');
    }
}

async function submitWorkHubNewProject(event) {
    event.preventDefault();
    const name = document.getElementById('workHubProjectName')?.value.trim();
    if (!name) return;
    const payload = {
        name,
        description: document.getElementById('workHubProjectDescription')?.value.trim() || undefined,
        status: document.getElementById('workHubProjectStatus')?.value,
        visibility: document.getElementById('workHubProjectVisibility')?.value,
        start_date: document.getElementById('workHubProjectStartDate')?.value || undefined,
        due_date: document.getElementById('workHubProjectDueDate')?.value || undefined,
    };
    try {
        const resp = await apiFetch(`${API_BASE}/projects`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'create_failed');
        document.getElementById('workHubNewProjectForm')?.reset();
        showNotification(ui('Đã tạo dự án', 'Project created'), 'success');
        await loadWorkHubPage();
    } catch (err) {
        showNotification(ui('Không tạo được dự án', 'Could not create project'), 'error');
    }
}

async function submitWorkHubNewTask(event) {
    event.preventDefault();
    if (!workHubSelectedProjectId) return;
    const title = document.getElementById('workHubTaskTitle')?.value.trim();
    if (!title) return;
    const payload = {
        project_id: workHubSelectedProjectId,
        title,
        priority: document.getElementById('workHubTaskPriority')?.value,
        due_date: document.getElementById('workHubTaskDueDate')?.value || undefined,
    };
    try {
        const resp = await apiFetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'create_failed');
        document.getElementById('workHubNewTaskForm')?.reset();
        await loadWorkHubTasks(workHubSelectedProjectId);
    } catch (err) {
        showNotification(ui('Không tạo được nhiệm vụ', 'Could not create task'), 'error');
    }
}

// ---------------------------------------------------------------------------
// Business Knowledge (Phase 5, design doc 8.7) -- workspace-curated docs
// Bob's RAG also searches. See routes/workspace_knowledge.py.
// ---------------------------------------------------------------------------

async function loadWorkspaceKnowledgePage() {
    const emptyEl = document.getElementById('workspaceKnowledgeEmpty');
    const contentEl = document.getElementById('workspaceKnowledgeContent');
    const newCard = document.getElementById('workspaceKnowledgeNewCard');
    const active = currentOrgWorkspace();
    if (!active || active.type !== 'business') {
        if (emptyEl) emptyEl.hidden = false;
        if (contentEl) contentEl.hidden = true;
        return;
    }
    if (emptyEl) emptyEl.hidden = true;
    if (contentEl) contentEl.hidden = false;
    if (newCard) newCard.hidden = !currentOrgCanManage();

    try {
        const resp = await apiFetch(`${API_BASE}/workspace-knowledge`);
        const data = await resp.json();
        if (resp.ok && data.success) workspaceKnowledgeDocs = data.documents || [];
    } catch (err) {
        console.warn('loadWorkspaceKnowledgePage failed', err);
    }
    renderWorkspaceKnowledgeList();
}

function renderWorkspaceKnowledgeList() {
    const listEl = document.getElementById('workspaceKnowledgeList');
    if (!listEl) return;
    if (!workspaceKnowledgeDocs.length) {
        listEl.innerHTML = `<div class="chat-session-empty">${ui('Chưa có tài liệu nào.', 'No documents yet.')}</div>`;
        return;
    }
    const canManage = currentOrgCanManage();
    listEl.innerHTML = workspaceKnowledgeDocs.map((doc) => `
        <div class="work-hub-item-row" data-doc-id="${escapeHtml(doc.id)}">
            <div class="work-hub-item-info">
                <strong>${escapeHtml(doc.title)}</strong>
                <small>${escapeHtml((doc.content || '').slice(0, 140))}${(doc.content || '').length > 140 ? '…' : ''}</small>
            </div>
            ${canManage ? `<div class="work-hub-item-actions"><button type="button" class="btn-secondary" data-delete-knowledge-doc="${escapeHtml(doc.id)}">${ui('Xoá', 'Delete')}</button></div>` : ''}
        </div>
    `).join('');
    listEl.querySelectorAll('[data-delete-knowledge-doc]').forEach((btn) => {
        btn.addEventListener('click', () => deleteWorkspaceKnowledgeDoc(btn.getAttribute('data-delete-knowledge-doc')));
    });
}

async function submitWorkspaceKnowledgeNew(event) {
    event.preventDefault();
    const title = document.getElementById('workspaceKnowledgeTitle')?.value.trim();
    const content = document.getElementById('workspaceKnowledgeContentInput')?.value.trim();
    if (!title || !content) return;
    const payload = {
        title,
        content,
        tags: document.getElementById('workspaceKnowledgeTags')?.value.trim() || undefined,
    };
    try {
        const resp = await apiFetch(`${API_BASE}/workspace-knowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'create_failed');
        document.getElementById('workspaceKnowledgeNewForm')?.reset();
        showNotification(ui('Đã lưu tài liệu', 'Document saved'), 'success');
        await loadWorkspaceKnowledgePage();
    } catch (err) {
        showNotification(ui('Không lưu được tài liệu', 'Could not save document'), 'error');
    }
}

async function deleteWorkspaceKnowledgeDoc(docId) {
    if (!confirm(ui('Xoá tài liệu này khỏi kiến thức doanh nghiệp?', 'Delete this document from Business Knowledge?'))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspace-knowledge/${docId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'delete_failed');
        workspaceKnowledgeDocs = workspaceKnowledgeDocs.filter((d) => String(d.id) !== String(docId));
        renderWorkspaceKnowledgeList();
    } catch (err) {
        showNotification(ui('Không xoá được tài liệu', 'Could not delete document'), 'error');
    }
}

function renderStatusReportProjectOptions() {
    const select = document.getElementById('statusReportProject');
    if (!select) return;
    const current = select.value;
    select.innerHTML = `<option value="">${ui('Không gắn với dự án cụ thể', 'Not tied to a specific project')}</option>` +
        workHubProjects.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join('');
    if (workHubProjects.some((p) => p.id === current)) select.value = current;
}

async function loadStatusReportsPage() {
    const emptyEl = document.getElementById('statusReportsEmpty');
    const contentEl = document.getElementById('statusReportsContent');
    const active = currentOrgWorkspace();
    if (!active || active.type !== 'business') {
        if (emptyEl) emptyEl.hidden = false;
        if (contentEl) contentEl.hidden = true;
        return;
    }
    if (emptyEl) emptyEl.hidden = true;
    if (contentEl) contentEl.hidden = false;

    try {
        const resp = await apiFetch(`${API_BASE}/projects`);
        const data = await resp.json();
        if (resp.ok && data.success) workHubProjects = data.projects || [];
    } catch (err) {
        console.warn('loadStatusReportsPage projects failed', err);
    }
    renderStatusReportProjectOptions();

    try {
        const resp = await apiFetch(`${API_BASE}/status-reports?status=draft`);
        const data = await resp.json();
        if (resp.ok && data.success) statusReportDrafts = data.reports || [];
    } catch (err) {
        console.warn('loadStatusReportsPage drafts failed', err);
    }
    try {
        const resp = await apiFetch(`${API_BASE}/status-reports?status=published`);
        const data = await resp.json();
        if (resp.ok && data.success) statusReportPublished = data.reports || [];
    } catch (err) {
        console.warn('loadStatusReportsPage published failed', err);
    }
    renderStatusReportsList('statusReportDraftsList', statusReportDrafts, { draft: true });
    renderStatusReportsList('statusReportPublishedList', statusReportPublished, { draft: false });
}

function statusReportProjectName(projectId) {
    const project = workHubProjects.find((p) => p.id === projectId);
    return project ? project.name : null;
}

function renderStatusReportsList(elementId, reports, { draft }) {
    const listEl = document.getElementById(elementId);
    if (!listEl) return;
    if (!reports.length) {
        listEl.innerHTML = `<div class="chat-session-empty">${draft
            ? ui('Chưa có báo cáo nháp.', 'No drafts yet.')
            : ui('Chưa có báo cáo nào được công bố.', 'No published reports yet.')}</div>`;
        return;
    }
    listEl.innerHTML = reports.map((report) => {
        const projectName = statusReportProjectName(report.project_id);
        const fields = [
            ['Done', report.done_text], ['Doing', report.doing_text], ['Blocked', report.blocked_text],
            ['Next', report.next_text], ['Risks', report.risks_text],
        ].filter(([, text]) => (text || '').trim());
        return `
            <div class="work-hub-report-body" data-report-id="${escapeHtml(report.id)}">
                <div class="work-hub-item-row" style="cursor:default;">
                    <div class="work-hub-item-info">
                        <strong>${escapeHtml(report.report_date)}</strong>
                        <small>${projectName ? escapeHtml(projectName) : ui('Không gắn dự án', 'No project')}</small>
                    </div>
                    ${draft ? `
                        <div class="work-hub-item-actions">
                            <button type="button" class="btn-primary" data-publish-report="${escapeHtml(report.id)}">${ui('Công bố', 'Publish')}</button>
                            <button type="button" class="btn-secondary" data-delete-report="${escapeHtml(report.id)}">${ui('Xoá', 'Delete')}</button>
                        </div>
                    ` : ''}
                </div>
                ${fields.map(([label, text]) => `<p><strong>${label}:</strong> ${escapeHtml(text)}</p>`).join('')}
            </div>
        `;
    }).join('');
    if (draft) {
        listEl.querySelectorAll('[data-publish-report]').forEach((btn) => {
            btn.addEventListener('click', () => publishStatusReport(btn.getAttribute('data-publish-report')));
        });
        listEl.querySelectorAll('[data-delete-report]').forEach((btn) => {
            btn.addEventListener('click', () => deleteStatusReport(btn.getAttribute('data-delete-report')));
        });
    }
}

async function submitStatusReportDraft(event) {
    event.preventDefault();
    const payload = {
        project_id: document.getElementById('statusReportProject')?.value || undefined,
        done_text: document.getElementById('statusReportDone')?.value.trim() || '',
        doing_text: document.getElementById('statusReportDoing')?.value.trim() || '',
        blocked_text: document.getElementById('statusReportBlocked')?.value.trim() || '',
        next_text: document.getElementById('statusReportNext')?.value.trim() || '',
        risks_text: document.getElementById('statusReportRisks')?.value.trim() || '',
    };
    try {
        const resp = await apiFetch(`${API_BASE}/status-reports`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'create_failed');
        document.getElementById('statusReportNewForm')?.reset();
        showNotification(ui('Đã lưu báo cáo nháp', 'Draft saved'), 'success');
        await loadStatusReportsPage();
    } catch (err) {
        showNotification(ui('Không lưu được báo cáo', 'Could not save report'), 'error');
    }
}

async function publishStatusReport(reportId) {
    if (!confirm(ui(
        'Công bố báo cáo này vào không gian doanh nghiệp? Sau khi công bố sẽ không thể chỉnh sửa nội dung nữa.',
        'Publish this report to the workspace? Once published, its content can no longer be edited.'
    ))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/status-reports/${reportId}/publish`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            if (data.error === 'report_empty') {
                throw new Error(ui('Báo cáo trống, hãy điền ít nhất một mục trước khi công bố.', 'The report is empty -- fill in at least one field before publishing.'));
            }
            throw new Error(data.error || 'publish_failed');
        }
        showNotification(ui('Đã công bố báo cáo', 'Report published'), 'success');
        await loadStatusReportsPage();
    } catch (err) {
        showNotification(err.message || ui('Không công bố được báo cáo', 'Could not publish report'), 'error');
    }
}

async function deleteStatusReport(reportId) {
    if (!confirm(ui('Xoá báo cáo nháp này?', 'Delete this draft?'))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/status-reports/${reportId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'delete_failed');
        statusReportDrafts = statusReportDrafts.filter((r) => r.id !== reportId);
        renderStatusReportsList('statusReportDraftsList', statusReportDrafts, { draft: true });
    } catch (err) {
        showNotification(ui('Không xoá được báo cáo', 'Could not delete report'), 'error');
    }
}

// ---------------------------------------------------------------------------
// Privacy-first sharing (Phase 4): confirm-before-sharing an email into a
// Business workspace, and the "Trung tâm chia sẻ" (Sharing Center) page.
// ---------------------------------------------------------------------------

function openShareArtifactModal(email) {
    const modal = document.getElementById('shareArtifactModal');
    const preview = document.getElementById('shareArtifactPreview');
    const select = document.getElementById('shareArtifactWorkspace');
    if (!modal || !preview || !select) return;

    const businessWorkspaces = orgWorkspaces.filter((w) => w.type === 'business');
    if (!businessWorkspaces.length) {
        showNotification(ui(
            'Bạn chưa tham gia không gian doanh nghiệp nào để chia sẻ.',
            "You aren't a member of any Business workspace to share into."
        ), 'error');
        return;
    }

    shareArtifactSourceEmail = email;
    preview.innerHTML = `
        <p><strong>${ui('Tiêu đề', 'Subject')}:</strong> ${escapeHtml(email.subject || '')}</p>
        <p><strong>${ui('Từ', 'From')}:</strong> ${escapeHtml(email.sender || '')}</p>
        <p><strong>${ui('Nội dung', 'Content')}:</strong> ${escapeHtml(email.summary || email.snippet || '')}</p>
    `;
    select.innerHTML = businessWorkspaces.map((w) => `<option value="${escapeHtml(w.id)}">${escapeHtml(w.name)}</option>`).join('');
    modal.classList.add('show');
    document.body.classList.add('modal-open');
}

function closeShareArtifactModal() {
    document.getElementById('shareArtifactModal')?.classList.remove('show');
    document.body.classList.remove('modal-open');
    shareArtifactSourceEmail = null;
}

async function submitShareArtifact(event) {
    event.preventDefault();
    const email = shareArtifactSourceEmail;
    const workspaceId = document.getElementById('shareArtifactWorkspace')?.value;
    if (!email || !workspaceId) return;
    if (!confirm(ui(
        'Xác nhận chia sẻ email này vào không gian đã chọn? Chủ sở hữu/quản trị sẽ thấy được nội dung.',
        'Confirm sharing this email into the selected workspace? The owner/admin will be able to see this content.'
    ))) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${workspaceId}/shared-artifacts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_type: 'email_summary',
                title: email.subject || ui('Email đã chia sẻ', 'Shared email'),
                content: {
                    subject: email.subject || '',
                    sender: email.sender || '',
                    summary: email.summary || email.snippet || '',
                    date: email.date || '',
                },
            }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'share_failed');
        showNotification(ui('Đã chia sẻ vào không gian doanh nghiệp', 'Shared to the workspace'), 'success');
        closeShareArtifactModal();
    } catch (err) {
        showNotification(ui('Không chia sẻ được', 'Could not share'), 'error');
    }
}

async function loadSharingCenter() {
    const listEl = document.getElementById('sharingCenterList');
    if (!listEl) return;
    try {
        const resp = await apiFetch(`${API_BASE}/user/sharing`);
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'load_failed');
        sharingCenterArtifacts = data.artifacts || [];
        renderSharingCenter(sharingCenterArtifacts);
    } catch (err) {
        console.warn('loadSharingCenter failed', err);
    }
}

function renderSharingCenter(artifacts) {
    const listEl = document.getElementById('sharingCenterList');
    if (!listEl) return;
    if (!artifacts.length) {
        listEl.innerHTML = `<div class="chat-session-empty">${ui('Bạn chưa chia sẻ nội dung nào.', "You haven't shared anything yet.")}</div>`;
        return;
    }
    listEl.innerHTML = artifacts.map((artifact) => `
        <div class="work-hub-item-row" data-artifact-id="${escapeHtml(artifact.id)}">
            <div class="work-hub-item-info">
                <strong>${escapeHtml(artifact.title)}</strong>
                <small>${escapeHtml(artifact.workspace_name || '')} · ${escapeHtml(artifact.source_type)}</small>
            </div>
            <div class="work-hub-item-actions">
                <button type="button" class="btn-secondary" data-revoke-artifact="${escapeHtml(artifact.id)}">${ui('Thu hồi', 'Revoke')}</button>
            </div>
        </div>
    `).join('');
    listEl.querySelectorAll('[data-revoke-artifact]').forEach((btn) => {
        btn.addEventListener('click', () => revokeSharedArtifact(btn.getAttribute('data-revoke-artifact')));
    });
}

async function revokeSharedArtifact(artifactId) {
    if (!confirm(ui('Thu hồi chia sẻ này? Không gian sẽ không còn thấy nội dung này nữa.', 'Revoke this share? The workspace will no longer see this content.'))) return;
    const workspaceId = sharingCenterArtifacts.find((a) => a.id === artifactId)?.workspace_id;
    if (!workspaceId) return;
    try {
        const resp = await apiFetch(`${API_BASE}/workspaces/${workspaceId}/shared-artifacts/${artifactId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'revoke_failed');
        await loadSharingCenter();
    } catch (err) {
        showNotification(ui('Không thu hồi được', 'Could not revoke'), 'error');
    }
}

function setupSharingUI() {
    document.getElementById('shareArtifactForm')?.addEventListener('submit', submitShareArtifact);
    document.getElementById('shareArtifactModal')?.querySelectorAll('[data-modal="shareArtifactModal"]').forEach((el) => {
        el.addEventListener('click', closeShareArtifactModal);
    });
}

function setupWorkHubUI() {
    document.getElementById('workHubNewProjectForm')?.addEventListener('submit', submitWorkHubNewProject);
    document.getElementById('workspaceKnowledgeNewForm')?.addEventListener('submit', submitWorkspaceKnowledgeNew);
    document.getElementById('workHubNewTaskForm')?.addEventListener('submit', submitWorkHubNewTask);
    document.getElementById('statusReportNewForm')?.addEventListener('submit', submitStatusReportDraft);
}
