import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { apiGet, apiPost } from '../api/client';
import { getCurrentWorkspaceId, setCurrentWorkspaceId } from '../api/session';

// Multi-tenant workspace state (personal/business switcher, Phase 1 of
// WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md). Named "OrgWorkspace*" throughout
// to avoid colliding with the pre-existing "workspaceSync*" background-poll
// cursor in src/state/workspaceSync.js, an unrelated concept.
const OrgWorkspaceContext = createContext(null);

export function OrgWorkspaceProvider({ children }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [currentWorkspaceId, setCurrentWorkspaceIdState] = useState(null);
  const [loading, setLoading] = useState(false);

  const switchWorkspace = useCallback((id) => {
    setCurrentWorkspaceIdState(id || null);
    setCurrentWorkspaceId(id || '');
  }, []);

  const loadWorkspaces = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet('/workspaces');
      if (data?.success) {
        const list = data.workspaces || [];
        setWorkspaces(list);
        const saved = getCurrentWorkspaceId();
        const savedValid = saved && list.some((w) => w.id === saved);
        if (savedValid) {
          switchWorkspace(saved);
        } else {
          const personal = list.find((w) => w.type === 'personal');
          switchWorkspace(personal ? personal.id : (list[0] ? list[0].id : null));
        }
      }
    } catch {
      // Offline or not signed in yet: leave whatever was already loaded.
    } finally {
      setLoading(false);
    }
  }, [switchWorkspace]);

  const createBusinessWorkspace = useCallback(async (name) => {
    const data = await apiPost('/workspaces', { name });
    if (data?.success && data.workspace) {
      await loadWorkspaces();
      switchWorkspace(data.workspace.id);
    }
    return data?.workspace;
  }, [loadWorkspaces, switchWorkspace]);

  const acceptInvitation = useCallback(async (token) => {
    const data = await apiPost(`/workspace-invitations/${encodeURIComponent(token)}/accept`, {});
    if (data?.success && data.invitation) {
      await loadWorkspaces();
      switchWorkspace(data.invitation.workspace_id);
    }
    return data?.invitation;
  }, [loadWorkspaces, switchWorkspace]);

  const reset = useCallback(() => {
    setWorkspaces([]);
    setCurrentWorkspaceIdState(null);
    setCurrentWorkspaceId('');
  }, []);

  const current = useMemo(
    () => workspaces.find((w) => w.id === currentWorkspaceId) || null,
    [workspaces, currentWorkspaceId]
  );
  const isBusiness = current?.type === 'business';
  const currentRole = current?.member_role || null;
  const canManage = currentRole === 'owner' || currentRole === 'admin';

  const value = useMemo(() => ({
    workspaces,
    currentWorkspaceId,
    current,
    isBusiness,
    currentRole,
    canManage,
    loading,
    loadWorkspaces,
    switchWorkspace,
    createBusinessWorkspace,
    acceptInvitation,
    reset,
  }), [
    workspaces, currentWorkspaceId, current, isBusiness, currentRole, canManage, loading,
    loadWorkspaces, switchWorkspace, createBusinessWorkspace, acceptInvitation, reset,
  ]);

  return <OrgWorkspaceContext.Provider value={value}>{children}</OrgWorkspaceContext.Provider>;
}

export function useOrgWorkspace() {
  return useContext(OrgWorkspaceContext);
}
