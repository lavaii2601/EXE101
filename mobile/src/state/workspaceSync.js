import * as SecureStore from 'expo-secure-store';
import { getMobileUserId } from '../api/session';

const WORKSPACE_SYNC_REVISION_KEY = 'flowmate.workspaceSyncRevision';

let pendingWrite = Promise.resolve();

function currentOwner() {
  return getMobileUserId() || 'anonymous';
}

function revisionMapFromStored(stored) {
  if (!stored) return {};
  try {
    const parsed = JSON.parse(stored);
    if (parsed?.revisions && typeof parsed.revisions === 'object') {
      return { ...parsed.revisions };
    }
  } catch {
    return {};
  }
  return {};
}

function normalizeRevision(value) {
  const revision = Number(value);
  return Number.isSafeInteger(revision) && revision >= 0 ? revision : null;
}

export async function loadWorkspaceSyncRevision(expectedOwner = currentOwner()) {
  await pendingWrite.catch(() => {});
  if (expectedOwner !== currentOwner()) return null;

  try {
    const stored = await SecureStore.getItemAsync(WORKSPACE_SYNC_REVISION_KEY);
    if (expectedOwner !== currentOwner()) return null;
    return normalizeRevision(revisionMapFromStored(stored)[expectedOwner]);
  } catch {
    return null;
  }
}

export function persistWorkspaceSyncRevision(value, expectedOwner = currentOwner()) {
  const revision = normalizeRevision(value);
  if (revision === null || expectedOwner !== currentOwner()) {
    return Promise.resolve(false);
  }

  pendingWrite = pendingWrite
    .catch(() => {})
    .then(async () => {
      if (expectedOwner !== currentOwner()) return false;
      const stored = await SecureStore.getItemAsync(WORKSPACE_SYNC_REVISION_KEY);
      if (expectedOwner !== currentOwner()) return false;
      const revisions = revisionMapFromStored(stored);
      revisions[expectedOwner] = revision;
      await SecureStore.setItemAsync(
        WORKSPACE_SYNC_REVISION_KEY,
        JSON.stringify({ version: 1, revisions }),
      );
      return true;
    })
    .catch(() => false);

  return pendingWrite;
}
