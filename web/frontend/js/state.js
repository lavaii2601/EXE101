// API Configuration
const API_BASE = '/api';

// DOM Elements - will be selected during initApp after DOM is ready
let chatMessages;
let chatJumpLatest;
let userInput;
let sendBtn;
let newChatBtn;
let newChatSidebarBtn;
let newChatPanelBtn;
let chatSessionsList;
let chatRetentionSelect;
let navBtns;
let tabBtns;
let emailDetailModal;
let closeModal;
let clearBtn;
let composeForm;
let scheduleForm;
let gmailLoginBtn;
let gmailLogoutBtn;
let gmailAccountBadge;
let gmailProfileCard;
let gmailAvatar;
let gmailName;
let gmailEmail;
let openGmailBtn;
let emailFilterSelect;
let userModeSelect;
let userModeModal;
let emailSearchInput;
let emailSearchTimer;
let emailLoadController;

// State
let currentPage = 'overview';
let currentEmailPage = 1;
// Smart Inbox (Phase 4): a second, independent filter dimension alongside
// the existing category filter (emailFilterSelect) -- '' means no bucket
// filter applied (show every bucket).
let currentSmartBucketFilter = '';
let currentWeekStart; // set in initApp() (main.js) — see hazard note in the split plan:
// classic <script> tags don't hoist function declarations across files, so
// calling getMonday() here at top-level parse time would be fragile/order-
// dependent. initApp() runs after every script has loaded (DOMContentLoaded).
let currentDetailEmail = null;
let currentUserMode = 'worker';
let pendingUserMode = '';
let userModeRequired = false;
let pendingPageAfterMode = '';
let isAuthenticated = false;
let lastAuthStatus = null;
let authFormMode = 'login';
let currentLanguage = localStorage.getItem('flowmate-language') === 'en' ? 'en' : 'vi';
let activeChatSessionId = localStorage.getItem('flowmate-active-chat-session') || createChatSessionId();
let activeChatSessionTitle = localStorage.getItem('flowmate-active-chat-title') || '';
let agentProfile = null;
let newMailPollTimer = null;
let overviewRefreshTimer = null;
let lastSeenMailId = localStorage.getItem('flowmate-last-mail-id') || null;
let workspaceSyncPollTimer = null;
let workspaceSyncInFlight = false;
let workspaceSyncRevision = null;
let workspaceSyncOwnerId = '';
let workspaceSyncHasBaseline = false;
let workspaceSyncListenersBound = false;
let workspaceSyncPollAfterMs = 12000;
let workspaceSyncGeneration = 0;
let workspaceSyncAbortController = null;
let currentSubscription = null;
let selectedSubscriptionPlan = 'monthly';
let selectedSubscriptionPaymentMethod = 'BANK_TRANSFER';
// Multi-tenant Business workspace state (Worker Business Phase 1). Named
// "orgWorkspace*" throughout to avoid colliding with the pre-existing
// workspaceSync*/#workspaceApp vocabulary above, which means something
// unrelated: the personal single-tenant app shell's own sync/polling cursor.
let currentOrgWorkspaceId = null;
let orgWorkspaces = [];
let orgWorkspaceMembers = [];
let orgWorkspacePendingInvitations = [];
// Phase 2 (Subscription/Seat foundation): Business subscription status and
// pending "need more seats" requests for the active workspace.
let orgWorkspaceSubscription = null;
let orgWorkspaceSeatRequests = [];
// Phase 3 ("Work Hub"): shared projects/tasks and manual Status Reports for
// the active Business workspace. See routes/work_hub.py.
let workHubProjects = [];
let workHubTasks = [];
let workHubSelectedProjectId = null;
let statusReportDrafts = [];
let statusReportPublished = [];
// Phase 5 ("Advanced workspace and AI"): workspace-curated policy/template/
// FAQ docs Bob's RAG also searches. See routes/workspace_knowledge.py.
let workspaceKnowledgeDocs = [];
// Phase 4 ("Smart Inbox + privacy-first sharing"): the email currently
// staged in the share-confirmation modal, or null when the modal is closed.
let shareArtifactSourceEmail = null;
let sharingCenterArtifacts = [];
// Gmail push should be configured in production for true server-side push.
// This short watcher is the resilient foreground fallback and feels instant
// even when Pub/Sub is unavailable or the browser just resumed.
const NEW_MAIL_POLL_INTERVAL_MS = 5000;
const WORKSPACE_SYNC_POLL_MIN_MS = 10000;
const WORKSPACE_SYNC_POLL_MAX_MS = 15000;
const OVERVIEW_REFRESH_POLL_INTERVAL_MS = 2500;
const OVERVIEW_REFRESH_MAX_POLLS = 48;

function createChatSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
        const value = Math.random() * 16 | 0;
        const next = char === 'x' ? value : (value & 0x3 | 0x8);
        return next.toString(16);
    });
}

function persistChatSessionId() {
    localStorage.setItem('flowmate-active-chat-session', activeChatSessionId);
}

function persistChatSessionTitle() {
    if (activeChatSessionTitle) {
        localStorage.setItem('flowmate-active-chat-title', activeChatSessionTitle);
    } else {
        localStorage.removeItem('flowmate-active-chat-title');
    }
}
