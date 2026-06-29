from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    iphone = p.devices['iPhone 13']
    browser = p.chromium.launch(channel="msedge")
    context = browser.new_context(**iphone)
    page = context.new_page()

    # 1. Login/auth-gate page as a real mobile visitor would see it first
    page.goto("http://127.0.0.1:5000/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(500)
    page.screenshot(path="mobile_login.png", full_page=True)

    # 2. Bypass auth (same technique as before) to inspect the authenticated shell
    page.evaluate("""
        fetch('/api/user/profile', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin', body: JSON.stringify({user_mode: 'worker'})
        })
    """)
    page.wait_for_timeout(500)
    page.evaluate("""
        document.body.classList.add('workspace-ready');
        document.getElementById('authGate').classList.add('is-hidden');
        if (typeof isAuthenticated !== 'undefined') isAuthenticated = true;
        if (typeof userModeRequired !== 'undefined') userModeRequired = false;
        if (typeof currentUserMode !== 'undefined') currentUserMode = 'worker';
    """)
    page.wait_for_timeout(500)
    page.screenshot(path="mobile_overview.png", full_page=True)

    # Open the sidebar via the hamburger toggle first, as a real mobile user would
    menu_toggle = page.locator('#menuToggle')
    if menu_toggle.count() > 0:
        menu_toggle.first.click()
        page.wait_for_timeout(500)
    page.screenshot(path="mobile_sidebar_open.png", full_page=True)

    nav = page.locator('.nav-btn[data-page="chat"]')
    if nav.count() > 0:
        nav.first.click(force=True)
        page.wait_for_timeout(800)
    page.screenshot(path="mobile_chat.png", full_page=True)

    page.fill("#userInput", "Xin chao")
    page.click("#sendBtn")
    page.wait_for_timeout(2000)
    page.screenshot(path="mobile_chat_msg.png", full_page=True)

    print("Saved mobile screenshots")
    browser.close()
