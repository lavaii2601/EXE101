function normalizePages() {
    document.querySelectorAll('.page').forEach(p => {
        if (p.classList.contains('active')) {
            // make sure active page uses flex to match CSS
            p.style.display = 'flex';
        } else {
            p.style.display = 'none';
        }
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
    console.log('🚀 Initializing app...');
    // currentWeekStart (state.js) is intentionally uninitialized at parse
    // time -- see the comment next to its declaration. Set it here, first,
    // now that every script (including utils.js's getMonday) has loaded.
    currentWeekStart = getMonday(new Date());
    // Select DOM elements now that DOMContentLoaded fired
    chatMessages = document.getElementById('chatMessages');
    chatJumpLatest = document.getElementById('chatJumpLatest');
    userInput = document.getElementById('userInput');
    sendBtn = document.getElementById('sendBtn');
    newChatBtn = document.getElementById('newChatBtn');
    newChatSidebarBtn = document.getElementById('newChatSidebarBtn');
    newChatPanelBtn = document.getElementById('newChatPanelBtn');
    chatSessionsList = document.getElementById('chatSessionsList');
    chatRetentionSelect = document.getElementById('chatRetentionSelect');
    navBtns = document.querySelectorAll('[data-page]');
    tabBtns = document.querySelectorAll('[data-tab]');
    emailDetailModal = document.getElementById('emailDetailModal');
    closeModal = document.querySelector('.close');
    clearBtn = document.getElementById('clearBtn');
    composeForm = document.getElementById('composeForm');
    scheduleForm = document.getElementById('scheduleForm');
    gmailLoginBtn = document.getElementById('gmailLoginBtn');
    gmailLogoutBtn = document.getElementById('gmailLogoutBtn');
    gmailAccountBadge = document.getElementById('gmailAccountBadge');
    gmailProfileCard = document.getElementById('gmailProfileCard');
    gmailAvatar = document.getElementById('gmailAvatar');
    gmailName = document.getElementById('gmailName');
    gmailEmail = document.getElementById('gmailEmail');
    openGmailBtn = document.getElementById('openGmailBtn');
    emailFilterSelect = document.getElementById('emailFilterSelect');
    userModeSelect = document.getElementById('userModeSelect');
    userModeModal = document.getElementById('userModeModal');
    emailSearchInput = document.getElementById('emailSearchInput');
    setupAuthGate();
    setupWorkspaceShell();
    setupOrgWorkspaceUI();
    setupNotificationUI();
    setupWorkHubUI();
    setupSharingUI();
    applyLanguage();
    setupDateTimePreviews();
    const savedTheme = localStorage.getItem('flowmate-theme');
    document.body.classList.toggle('dark-theme', savedTheme === 'dark');
    // Normalize page visibility on startup to avoid stale CSS/inline styles
    normalizePages();
    
    // Manually attach event listeners (setupEventListeners has scope issues)
    try {
        // Send message button
        if (sendBtn) {
            sendBtn.addEventListener('click', () => sendMessage());
        }
        if (newChatBtn) {
            newChatBtn.addEventListener('click', startNewChat);
        }
        if (newChatSidebarBtn) {
            newChatSidebarBtn.addEventListener('click', startNewChat);
        }
        if (newChatPanelBtn) {
            newChatPanelBtn.addEventListener('click', startNewChat);
        }
        if (chatRetentionSelect) {
            chatRetentionSelect.addEventListener('change', updateChatRetention);
        }
        if (chatMessages) {
            chatMessages.addEventListener('scroll', () => {
                if (!chatJumpLatest) return;
                const distFromBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight;
                chatJumpLatest.classList.toggle('visible', distFromBottom > 200);
            });
        }
        if (chatJumpLatest) {
            chatJumpLatest.addEventListener('click', () => {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        }
        
        // Enter key in input
        if (userInput) {
            userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }
        
        // Page navigation
        navBtns.forEach(btn => {
            btn.addEventListener('click', () => handlePageChange(btn));
        });
        
        // Tab switching
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => handleTabChange(btn));
        });

        const refreshOverviewBtn = document.getElementById('refreshOverviewBtn');
        const overviewDate = document.getElementById('overviewDate');
        if (overviewDate && !overviewDate.value) {
            overviewDate.value = formatDateForApi(new Date());
        }
        if (refreshOverviewBtn) {
            refreshOverviewBtn.addEventListener('click', () => loadOverviewPage({ force: true }));
        }
        if (overviewDate) {
            overviewDate.addEventListener('change', () => loadOverviewPage({ force: false }));
        }

        // New schedule form submit
        if (scheduleForm) {
            scheduleForm.addEventListener('submit', handleScheduleSubmit);
            bindScheduleTimeLogic();
        }

        // Edit schedule form submit
        const editScheduleForm = document.getElementById('editScheduleForm');
        if (editScheduleForm) {
            editScheduleForm.addEventListener('submit', handleEditScheduleSubmit);
        }
        bindEditScheduleModal();

        // Create event button (opens the new-schedule popup)
        const createEventBtn = document.getElementById('createEventBtn');
        if (createEventBtn) {
            createEventBtn.addEventListener('click', () => openNewScheduleModal());
        }

        // New Schedule modal close handlers (X button and Hủy button)
        const newScheduleModal = document.getElementById('newScheduleModal');
        if (newScheduleModal) {
            newScheduleModal.querySelectorAll('[data-modal="newScheduleModal"]').forEach(el => {
                el.addEventListener('click', () => closeNewScheduleModal());
            });
        }

        // Compose email form submit
        if (composeForm) {
            composeForm.addEventListener('submit', handleComposeSubmit);
        }

        // Email detail modal action buttons
        const summarizeBtn = document.getElementById('summarizeBtn');
        if (summarizeBtn) {
            summarizeBtn.addEventListener('click', handleSummarizeEmail);
        }
        const replyBtn = document.getElementById('replyBtn');
        if (replyBtn) {
            replyBtn.addEventListener('click', handleAutoReply);
        }
        const emailDetailCloseBtn = emailDetailModal
            ? emailDetailModal.querySelector('.email-detail-close')
            : null;
        if (emailDetailCloseBtn) {
            emailDetailCloseBtn.addEventListener('click', closeModalWindow);
        }
        if (emailDetailModal) {
            emailDetailModal.addEventListener('click', (event) => {
                if (event.target === emailDetailModal) closeModalWindow();
            });
        }
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && emailDetailModal?.classList.contains('show')) {
                closeModalWindow();
            }
            if (event.key === 'Escape' && userModeModal?.classList.contains('show')) {
                closeUserModeModal();
            }
            if (event.key === 'Escape' && document.getElementById('subscriptionModal')?.classList.contains('show')) {
                closeSubscriptionModal();
            }
        });

        // Clear history
        if (clearBtn) {
            clearBtn.addEventListener('click', clearConversation);
        }

        // Gmail buttons
        const userAvatar = document.getElementById('userAvatar');
        if (userAvatar) userAvatar.addEventListener('click', gmailLogin);
        if (gmailLoginBtn) gmailLoginBtn.addEventListener('click', gmailLogin);
        if (gmailLogoutBtn) gmailLogoutBtn.addEventListener('click', gmailLogout);
        if (openGmailBtn) openGmailBtn.addEventListener('click', () => openExternalUrl('https://mail.google.com'));
        if (userModeSelect) {
            userModeSelect.addEventListener('change', () => saveUserMode(userModeSelect.value));
            updateUserModeUI(currentUserMode);
        }
        const openUserModeBtn = document.getElementById('openUserModeBtn');
        if (openUserModeBtn) openUserModeBtn.addEventListener('click', () => openUserModeModal(false));
        const userModeClose = userModeModal?.querySelector('.user-mode-close');
        if (userModeClose) userModeClose.addEventListener('click', closeUserModeModal);
        const userModeCancelBtn = document.getElementById('userModeCancelBtn');
        if (userModeCancelBtn) userModeCancelBtn.addEventListener('click', closeUserModeModal);
        const userModeConfirmBtn = document.getElementById('userModeConfirmBtn');
        if (userModeConfirmBtn) {
            userModeConfirmBtn.addEventListener('click', () => {
                if (pendingUserMode) saveUserMode(pendingUserMode, true);
            });
        }
        if (userModeModal) {
            userModeModal.addEventListener('click', (event) => {
                if (event.target === userModeModal) closeUserModeModal();
            });
        }

        // Email filter
        if (emailFilterSelect) {
            emailFilterSelect.addEventListener('change', () => {
                console.log(`🔍 Filter changed: ${emailFilterSelect.value}`);
                updateEmailFilterUI();
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true, silent: true });
            });
        }

        const emailFilterBtn = document.getElementById('emailFilterBtn');
        const emailFilterPopup = document.getElementById('emailFilterPopup');
        if (emailFilterBtn && emailFilterPopup) {
            emailFilterBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                const isOpen = emailFilterPopup.classList.toggle('show');
                emailFilterBtn.setAttribute('aria-expanded', String(isOpen));
            });
            emailFilterPopup.querySelectorAll('[data-filter]').forEach((button) => {
                button.addEventListener('click', () => {
                    emailFilterSelect.value = button.dataset.filter;
                    emailFilterSelect.dispatchEvent(new Event('change'));
                    emailFilterPopup.classList.remove('show');
                    emailFilterBtn.setAttribute('aria-expanded', 'false');
                });
            });
            document.addEventListener('click', (event) => {
                if (!event.target.closest('.email-filter-control')) {
                    emailFilterPopup.classList.remove('show');
                    emailFilterBtn.setAttribute('aria-expanded', 'false');
                }
            });
        }
        document.querySelectorAll('#smartInboxBar [data-smart-bucket]').forEach((chip) => {
            chip.addEventListener('click', () => {
                currentSmartBucketFilter = chip.dataset.smartBucket;
                document.querySelectorAll('#smartInboxBar [data-smart-bucket]').forEach((el) => {
                    el.classList.toggle('active', el === chip);
                });
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true, silent: true });
            });
        });
        if (emailSearchInput) {
            emailSearchInput.addEventListener('input', () => {
                clearTimeout(emailSearchTimer);
                emailSearchTimer = setTimeout(() => {
                    currentEmailPage = 1;
                    loadEmails(1, { cacheOnly: true, silent: true });
                }, 300);
            });
        }
        const clearEmailSearchBtn = document.getElementById('clearEmailSearchBtn');
        if (clearEmailSearchBtn) {
            clearEmailSearchBtn.addEventListener('click', () => {
                if (!emailSearchInput) return;
                emailSearchInput.value = '';
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true, silent: true });
                emailSearchInput.focus();
            });
        }
        const settingsModeBtn = document.getElementById('settingsModeBtn');
        if (settingsModeBtn) settingsModeBtn.addEventListener('click', () => openUserModeModal(false));
        const settingsRefreshBtn = document.getElementById('settingsRefreshBtn');
        if (settingsRefreshBtn) settingsRefreshBtn.addEventListener('click', loadSettingsPage);
        const subscriptionHeaderBtn = document.getElementById('subscriptionHeaderBtn');
        if (subscriptionHeaderBtn) subscriptionHeaderBtn.addEventListener('click', openSubscriptionModal);
        const settingsSubscriptionBtn = document.getElementById('settingsSubscriptionBtn');
        if (settingsSubscriptionBtn) settingsSubscriptionBtn.addEventListener('click', openSubscriptionModal);
        const subscriptionModal = document.getElementById('subscriptionModal');
        const subscriptionModalClose = document.getElementById('subscriptionModalClose');
        if (subscriptionModalClose) subscriptionModalClose.addEventListener('click', closeSubscriptionModal);
        if (subscriptionModal) {
            subscriptionModal.addEventListener('click', (event) => {
                if (event.target === subscriptionModal) closeSubscriptionModal();
            });
        }
        const studentToolsModal = document.getElementById('studentToolsModal');
        const studentToolsClose = studentToolsModal?.querySelector('.student-tools-close');
        if (studentToolsClose) studentToolsClose.addEventListener('click', closeStudentToolsModal);
        if (studentToolsModal) {
            studentToolsModal.addEventListener('click', (event) => {
                if (event.target === studentToolsModal) closeStudentToolsModal();
            });
        }
        document.querySelectorAll('[data-subscription-plan]').forEach((button) => {
            button.addEventListener('click', () => selectSubscriptionPlan(button.dataset.subscriptionPlan));
        });
        document.querySelectorAll('[data-payment-method]').forEach((button) => {
            button.addEventListener('click', () => selectSubscriptionPaymentMethod(button.dataset.paymentMethod));
        });
        const subscriptionContinueBtn = document.getElementById('subscriptionContinueBtn');
        if (subscriptionContinueBtn) subscriptionContinueBtn.addEventListener('click', showSubscriptionPaymentStep);
        const subscriptionBackBtn = document.getElementById('subscriptionBackBtn');
        if (subscriptionBackBtn) subscriptionBackBtn.addEventListener('click', showSubscriptionPlanStep);
        const subscriptionChangePlanBtn = document.getElementById('subscriptionChangePlanBtn');
        if (subscriptionChangePlanBtn) subscriptionChangePlanBtn.addEventListener('click', showSubscriptionPlanStep);
        const subscriptionSubmitBtn = document.getElementById('subscriptionSubmitBtn');
        if (subscriptionSubmitBtn) subscriptionSubmitBtn.addEventListener('click', submitSubscriptionIntent);
        const settingsDarkMode = document.getElementById('settingsDarkMode');
        if (settingsDarkMode) {
            settingsDarkMode.checked = document.body.classList.contains('dark-theme');
            settingsDarkMode.addEventListener('change', () => {
                document.body.classList.toggle('dark-theme', settingsDarkMode.checked);
                localStorage.setItem('flowmate-theme', settingsDarkMode.checked ? 'dark' : 'light');
                setSettingsState('Đã lưu giao diện');
            });
        }
        const settingsGoogleBtn = document.getElementById('settingsGoogleBtn');
        if (settingsGoogleBtn) settingsGoogleBtn.addEventListener('click', handleSettingsGoogleAction);
        const settingsLogoutBtn = document.getElementById('settingsLogoutBtn');
        if (settingsLogoutBtn) settingsLogoutBtn.addEventListener('click', appLogout);
        const settingsClearDataBtn = document.getElementById('settingsClearDataBtn');
        if (settingsClearDataBtn) settingsClearDataBtn.addEventListener('click', clearAllUserHistory);
        document.querySelectorAll('[data-language]').forEach((button) => {
            button.addEventListener('click', () => setLanguage(button.dataset.language));
        });

        // Include read checkbox
        const includeReadCheckbox = document.getElementById('includeReadCheckbox');
        if (includeReadCheckbox) {
            includeReadCheckbox.addEventListener('change', () => {
                console.log(`📬 Include read: ${includeReadCheckbox.checked}`);
                currentEmailPage = 1;
                loadEmails(1, { cacheOnly: true, silent: true });
            });
        }

        // Refresh emails
        const refreshEmailsBtn = document.getElementById('refreshEmailsBtn');
        if (refreshEmailsBtn && refreshEmailsBtn.dataset.refreshBound !== 'true') {
            refreshEmailsBtn.dataset.refreshBound = 'true';
            refreshEmailsBtn.addEventListener('click', () => {
                console.log('🔄 Refreshing emails');
                refreshEmailsFromGmail()
                    .catch(err => console.error('Cache clear error:', err));
            });
        }

        // Generate daily report
        const generateReportBtn = document.getElementById('generateReportBtn');
        if (generateReportBtn) {
            generateReportBtn.addEventListener('click', generateDailyReport);
        }

        // Calendar buttons
    const refreshCalendarBtn = document.getElementById('refreshCalendarBtn');
    if (refreshCalendarBtn && refreshCalendarBtn.dataset.refreshBound !== 'true') {
        refreshCalendarBtn.dataset.refreshBound = 'true';
        refreshCalendarBtn.addEventListener('click', () => {
            console.log('🔄 Refreshing calendar events');
            scheduleMeetingSuggestionRefresh({ scan: false, delay: 0 });
            refreshCalendarScheduleData({ notify: true, continueOnError: true })
                .catch(err => console.warn('Schedule refresh error:', err));
        });
    }

        const openCalendarBtn = document.getElementById('openCalendarBtn');
        if (openCalendarBtn) {
            openCalendarBtn.addEventListener('click', () => openExternalUrl('https://calendar.google.com'));
        }

        // Weekly schedule table navigation
        bindWeekNavigation();

        // Listen for postMessage from OAuth popup to update UI without redirect
        window.addEventListener('message', async (ev) => {
            try {
                if (ev.origin === window.location.origin && ev.data && ev.data.type === 'gmail_auth' && ev.data.status === 'success') {
                    console.log('📥 Received gmail_auth success message');
                    const authenticatedAfterOAuth = await resolveInitialAuthState();
                    if (!authenticatedAfterOAuth) return;
                    if (shouldShowAdminAccessChoice()) {
                        showAdminAccessChoice();
                        return;
                    }
                    await refreshAuthButtons();
                    await loadUserProfile();
                    await startWorkspaceSyncWatcher();
                    if (userModeRequired) {
                        pendingPageAfterMode = 'overview';
                    } else {
                        showWorkspace();
                        if (currentPage === 'emails') {
                            setTimeout(() => loadEmails(1, { cacheOnly: true }), 300);
                        }
                    }
                }
            } catch (e) {
                console.warn('PostMessage handling error', e);
            }
        });

        setupSidebarMenu();

        console.log('✅ Event listeners attached');
    } catch (err) {
        console.error('❌ Error attaching event listeners:', err);
    }
    
    await checkOAuthCallback();
    const authenticated = await resolveInitialAuthState();
    if (!authenticated) {
        checkRuntimeConfig();
        console.log('✅ App initialized in signed-out state');
        return;
    }

    if (shouldShowAdminAccessChoice()) {
        showAdminAccessChoice();
        console.log('✅ App initialized at admin destination choice');
        return;
    }

    if (await ensureGoogleCalendarPermission()) {
        return;
    }

    // Establish the cross-client cursor before loading the initial page.
    // This closes the gap where a remote mutation could otherwise land after
    // the page read but be swallowed by a later first-time baseline.
    await startWorkspaceSyncWatcher();
    await loadUserProfile();
    showSepayReturnNotice();
    await loadOrgWorkspaces();
    checkPendingOrgInvitationFromUrl();
    if (!userModeRequired) {
        showWorkspace();
        updateChatSessionTitle();
        await loadChatSessions();
        await loadChatHistory();
        const activeNavButton = document.querySelector('.sidebar-nav .nav-btn.active');
        if (activeNavButton) {
            await handlePageChange(activeNavButton);
        }
    }
    await refreshAuthButtons();
    startNewMailWatcher();
    checkRuntimeConfig();
    loadAgentProfile();
    
    // Auto-load emails if user is on emails page and authenticated
    if (currentPage === 'emails') {
        console.log('📧 Auto-loading emails on init...');
        setTimeout(() => loadEmails(1, { cacheOnly: true }), 500);
    }
    
    console.log('✅ App initialized');
}
