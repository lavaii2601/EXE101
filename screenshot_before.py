from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda msg: print("CONSOLE:", msg.text))
    page.goto("http://127.0.0.1:5000/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1000)

    status = page.evaluate("""
        fetch('/api/user/profile', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'same-origin',
            body: JSON.stringify({user_mode: 'worker'})
        }).then(r => r.status)
    """)
    print("profile POST status:", status)
    page.wait_for_timeout(500)

    print("userModeRequired before bypass:", page.evaluate("typeof userModeRequired !== 'undefined' ? userModeRequired : 'NOT_FOUND'"))

    page.evaluate("""
        document.body.classList.add('workspace-ready');
        document.getElementById('authGate').classList.add('is-hidden');
        if (typeof userModeRequired !== 'undefined') userModeRequired = false;
        if (typeof currentUserMode !== 'undefined') currentUserMode = 'worker';
        const modal = document.getElementById('userModeModal');
        if (modal) modal.classList.remove('is-required');
        if (modal) modal.style.display = 'none';
    """)
    print("userModeRequired after bypass:", page.evaluate("typeof userModeRequired !== 'undefined' ? userModeRequired : 'NOT_FOUND'"))
    page.wait_for_timeout(300)

    nav = page.locator('.nav-btn[data-page="chat"]')
    nav.first.click()
    page.wait_for_timeout(1000)
    print("userModeRequired after click:", page.evaluate("typeof userModeRequired !== 'undefined' ? userModeRequired : 'NOT_FOUND'"))
    print("current-page attr:", page.evaluate("document.getElementById('workspaceApp').getAttribute('data-current-page')"))

    page.screenshot(path="screenshot_before_chat.png", full_page=False)
    print("Saved screenshot_before_chat.png")
    browser.close()
