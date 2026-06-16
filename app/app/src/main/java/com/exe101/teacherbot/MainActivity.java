package com.exe101.teacherbot;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.Html;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.gms.auth.api.signin.GoogleSignIn;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInClient;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.common.api.ApiException;
import com.google.android.gms.tasks.Task;
import androidx.security.crypto.EncryptedSharedPreferences;
import androidx.security.crypto.MasterKey;
import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Calendar;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.net.URLEncoder;
import java.io.File;

public class MainActivity extends Activity {
    private static final int BG = Color.rgb(14, 14, 18);
    private static final int PANEL = Color.rgb(22, 22, 29);
    private static final int PANEL_SOFT = Color.rgb(30, 30, 40);
    private static final int PANEL_RAISED = Color.rgb(37, 37, 51);
    private static final int TEXT = Color.rgb(240, 240, 248);
    private static final int MUTED = Color.rgb(145, 145, 168);
    private static final int TEXT_DIM = Color.rgb(92, 92, 112);
    private static final int BORDER = Color.rgb(48, 48, 62);
    private static final int PRIMARY = Color.rgb(108, 99, 255);
    private static final int PRIMARY_DARK = Color.rgb(86, 78, 220);
    private static final int ACCENT = Color.rgb(167, 139, 250);
    private static final int INFO = Color.rgb(56, 189, 248);
    private static final int SUCCESS = Color.rgb(52, 211, 153);
    private static final int WARNING = Color.rgb(251, 191, 36);
    private static final int DANGER = Color.rgb(248, 113, 113);
    private static final int RC_SIGN_IN = 9001;

    private ApiClient api;
    private GoogleSignInClient mGoogleSignInClient;
    private SharedPreferences prefs;
    private LinearLayout content;
    private LinearLayout tabBar;
    private LinearLayout chatList;
    private LinearLayout emailList;
    private String activeTab = "chat";
    private String emailFilter = "all";
    private String emailSearch = "";
    private boolean emailIncludeRead = true;
    private String selectedRole = "";
    private String selectedScheduleDate = "";
    private String appLanguage = "vi";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = securePreferences();
        selectedRole = prefs.getString("role", "");
        appLanguage = prefs.getString("language", "vi");
        api = new ApiClient(prefs.getString("baseUrl", "http://10.0.2.2:5000/api"));
        api.setAccessToken(prefs.getString("accessToken", ""));

        GoogleSignInOptions gso = new GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                .requestEmail()
                .requestScopes(new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/gmail.readonly"),
                               new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/gmail.send"),
                               new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/gmail.modify"),
                               new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/calendar.events"),
                               new com.google.android.gms.common.api.Scope("https://www.googleapis.com/auth/userinfo.profile"))
                .requestServerAuthCode(getString(R.string.google_web_client_id), true)
                .build();
        mGoogleSignInClient = GoogleSignIn.getClient(this, gso);

        buildShell();
        if (
                prefs.getString("userId", "").isEmpty()
                        || prefs.getString("accessToken", "").isEmpty()
                        || !prefs.getBoolean("googleAuthenticated", false)
        ) {
            showLoginScreen();
        } else if (selectedRole.isEmpty()) {
            showRoleSelection();
        } else {
            showChat();
        }
    }

    private SharedPreferences securePreferences() {
        try {
            MasterKey masterKey = new MasterKey.Builder(this)
                    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                    .build();
            SharedPreferences encrypted = EncryptedSharedPreferences.create(
                    this,
                    "teacherbot_secure",
                    masterKey,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            );
            SharedPreferences legacy = getSharedPreferences("teacherbot", MODE_PRIVATE);
            if (!legacy.getAll().isEmpty() && encrypted.getAll().isEmpty()) {
                SharedPreferences.Editor editor = encrypted.edit();
                for (java.util.Map.Entry<String, ?> entry : legacy.getAll().entrySet()) {
                    Object value = entry.getValue();
                    if (value instanceof String) editor.putString(entry.getKey(), (String) value);
                    else if (value instanceof Boolean) editor.putBoolean(entry.getKey(), (Boolean) value);
                    else if (value instanceof Integer) editor.putInt(entry.getKey(), (Integer) value);
                    else if (value instanceof Long) editor.putLong(entry.getKey(), (Long) value);
                    else if (value instanceof Float) editor.putFloat(entry.getKey(), (Float) value);
                }
                editor.apply();
                legacy.edit().clear().apply();
            }
            return encrypted;
        } catch (Exception error) {
            throw new IllegalStateException("Unable to initialize encrypted app storage", error);
        }
    }

    private void buildShell() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);

        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setBackgroundColor(BG);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));

        tabBar = new LinearLayout(this);
        tabBar.setOrientation(LinearLayout.HORIZONTAL);
        tabBar.setPadding(dp(10), dp(8), dp(10), dp(10));
        tabBar.setBackgroundColor(BG);
        tabBar.setElevation(dp(10));
        renderTabs();
        root.addView(tabBar, new LinearLayout.LayoutParams(-1, dp(76)));

        setContentView(root);
    }

    private void updateSubtitle() {
        renderTabs();
    }

    private void showSettingsMenu() {
        String[] options = {"Change mode", "Disconnect Google"};
        new AlertDialog.Builder(this)
                .setTitle("FlowMate settings")
                .setItems(options, (dialog, which) -> {
                    if (which == 0) {
                        showRoleSelection();
                    } else {
                        disconnectAndReturnToLogin();
                    }
                })
                .setNegativeButton("Close", null)
                .show();
    }

    private void showSettings() {
        setAppChromeVisible(true);
        setActiveTab("settings");
        content.removeAllViews();
        content.addView(titleRow(tr("Cài đặt", "Settings")));

        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);

        LinearLayout account = card();
        account.addView(label(tr("TÀI KHOẢN", "ACCOUNT"), 11, Typeface.BOLD, ACCENT));
        account.addView(label(prefs.getString("userId", tr("Chưa kết nối Google", "Google not connected")), 16, Typeface.BOLD, TEXT));
        TextView accountStatus = label(
                prefs.getBoolean("googleAuthenticated", false)
                        ? tr("Google Workspace đã kết nối", "Google Workspace connected")
                        : tr("Chưa kết nối Google", "Google not connected"),
                12,
                Typeface.NORMAL,
                prefs.getBoolean("googleAuthenticated", false) ? SUCCESS : WARNING
        );
        accountStatus.setPadding(0, dp(5), 0, dp(10));
        account.addView(accountStatus);
        Button refresh = secondaryButton(tr("Làm mới trạng thái", "Refresh status"));
        refresh.setOnClickListener(v -> runApi(() -> api.get("/status"), data ->
                toast(data.optString("status", tr("Đã làm mới trạng thái", "Status refreshed")))));
        account.addView(refresh);
        body.addView(account);

        LinearLayout personalization = card();
        personalization.addView(label(tr("CÁ NHÂN HÓA", "PERSONALIZATION"), 11, Typeface.BOLD, ACCENT));
        personalization.addView(label(roleTitle(selectedRole), 17, Typeface.BOLD, TEXT));
        TextView roleDetail = label(roleFocus(selectedRole), 13, Typeface.NORMAL, MUTED);
        roleDetail.setPadding(0, dp(5), 0, dp(10));
        personalization.addView(roleDetail);
        Button changeMode = secondaryButton(tr("Đổi chế độ người dùng", "Change user mode"));
        changeMode.setOnClickListener(v -> showRoleSelection());
        personalization.addView(changeMode);
        body.addView(personalization);

        LinearLayout appearance = card();
        appearance.addView(label(tr("GIAO DIỆN & THÔNG BÁO", "APPEARANCE & NOTIFICATIONS"), 11, Typeface.BOLD, ACCENT));
        appearance.addView(label(tr("Giao diện tối", "Dark theme"), 15, Typeface.BOLD, TEXT));
        appearance.addView(label(tr("Giao diện tối được tối ưu cho mobile.", "Dark appearance optimized for mobile."), 12, Typeface.NORMAL, MUTED));
        CheckBox emailNotifications = new CheckBox(this);
        emailNotifications.setText(tr("Thông báo email quan trọng", "Important email notifications"));
        emailNotifications.setTextColor(TEXT);
        emailNotifications.setChecked(prefs.getBoolean("emailNotifications", true));
        emailNotifications.setOnCheckedChangeListener((buttonView, checked) ->
                prefs.edit().putBoolean("emailNotifications", checked).apply());
        appearance.addView(emailNotifications);
        CheckBox scheduleNotifications = new CheckBox(this);
        scheduleNotifications.setText(tr("Nhắc lịch hẹn", "Schedule reminders"));
        scheduleNotifications.setTextColor(TEXT);
        scheduleNotifications.setChecked(prefs.getBoolean("scheduleNotifications", true));
        scheduleNotifications.setOnCheckedChangeListener((buttonView, checked) ->
                prefs.edit().putBoolean("scheduleNotifications", checked).apply());
        appearance.addView(scheduleNotifications);
        body.addView(appearance);

        LinearLayout language = card();
        language.addView(label(tr("NGÔN NGỮ", "LANGUAGE"), 11, Typeface.BOLD, ACCENT));
        language.addView(label(tr("Ngôn ngữ hiển thị", "Display language"), 16, Typeface.BOLD, TEXT));
        TextView languageHint = label(
                tr("Áp dụng ngay và được ghi nhớ trên thiết bị này.", "Applied immediately and remembered on this device."),
                12,
                Typeface.NORMAL,
                MUTED
        );
        languageHint.setPadding(0, dp(5), 0, dp(10));
        language.addView(languageHint);
        LinearLayout languageActions = rowWrap();
        Button vietnamese = secondaryButton("Tiếng Việt");
        Button english = secondaryButton("English");
        styleLanguageButton(vietnamese, "vi");
        styleLanguageButton(english, "en");
        vietnamese.setOnClickListener(v -> setAppLanguage("vi"));
        english.setOnClickListener(v -> setAppLanguage("en"));
        languageActions.addView(vietnamese);
        languageActions.addView(english);
        language.addView(languageActions);
        body.addView(language);

        LinearLayout connection = card();
        connection.addView(label(tr("KẾT NỐI BACKEND", "BACKEND CONNECTION"), 11, Typeface.BOLD, ACCENT));
        connection.addView(label(api.getBaseUrl(), 13, Typeface.NORMAL, MUTED));
        Button changeBackend = secondaryButton(tr("Thay đổi Backend API", "Change Backend API"));
        changeBackend.setOnClickListener(v -> showBackendUrlDialog());
        connection.addView(changeBackend);
        body.addView(connection);

        LinearLayout data = card();
        data.addView(label(tr("DỮ LIỆU & QUYỀN RIÊNG TƯ", "DATA & PRIVACY"), 11, Typeface.BOLD, ACCENT));
        Button clearHistory = secondaryButton(tr("Xóa toàn bộ lịch sử", "Clear all history"));
        clearHistory.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle(tr("Xóa toàn bộ lịch sử?", "Clear all history?"))
                .setMessage(tr("Chat, hoạt động email và lịch đã ghi nhận sẽ bị xóa.", "Saved chat, email activity, and calendar history will be deleted."))
                .setNegativeButton(tr("Hủy", "Cancel"), null)
                .setPositiveButton(tr("Xóa", "Delete"), (dialog, which) ->
                        runApi(() -> api.post("/chat/clear-all", new JSONObject()), result ->
                                toast(tr("Đã xóa ", "Deleted ") + result.optInt("deleted_count", 0) + tr(" mục", " items"))))
                .show());
        data.addView(clearHistory);
        Button disconnect = secondaryButton(tr("Đăng xuất Google", "Sign out of Google"));
        disconnect.setOnClickListener(v -> disconnectAndReturnToLogin());
        LinearLayout.LayoutParams disconnectParams = new LinearLayout.LayoutParams(-1, dp(46));
        disconnectParams.setMargins(0, dp(8), 0, 0);
        data.addView(disconnect, disconnectParams);
        body.addView(data);

        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    }

    private void showBackendUrlDialog() {
        EditText backendInput = input("http://10.0.2.2:5000/api", false);
        backendInput.setText(api.getBaseUrl());
        new AlertDialog.Builder(this)
                .setTitle("Backend API")
                .setMessage(tr("Dùng 10.0.2.2 cho Android emulator, hoặc IP máy tính khi dùng điện thoại thật.", "Use 10.0.2.2 for the Android emulator, or your computer's IP address on a physical phone."))
                .setView(backendInput)
                .setNegativeButton(tr("Hủy", "Cancel"), null)
                .setPositiveButton(tr("Lưu", "Save"), (dialog, which) -> {
                    api.setBaseUrl(backendInput.getText().toString());
                    prefs.edit().putString("baseUrl", api.getBaseUrl()).apply();
                    toast(tr("Đã lưu Backend API", "Backend API saved"));
                    showSettings();
                })
                .show();
    }

    private String tr(String vietnamese, String english) {
        return "en".equals(appLanguage) ? english : vietnamese;
    }

    private void setAppLanguage(String language) {
        appLanguage = "en".equals(language) ? "en" : "vi";
        prefs.edit().putString("language", appLanguage).apply();
        buildShell();
        showSettings();
        toast(tr("Đã đổi sang Tiếng Việt", "Language changed to English"));
    }

    private void styleLanguageButton(Button button, String language) {
        boolean active = language.equals(appLanguage);
        button.setTextColor(active ? Color.WHITE : TEXT);
        button.setBackground(round(active ? PRIMARY : PANEL_RAISED, active ? PRIMARY : BORDER));
    }

    private String emailFilterLabel(String value) {
        if ("education".equals(value)) return tr("Giáo dục", "Education");
        if ("work".equals(value)) return tr("Công việc", "Work");
        if ("finance".equals(value)) return tr("Tài chính", "Finance");
        if ("meeting".equals(value)) return tr("Lịch họp", "Meetings");
        if ("promotion".equals(value)) return tr("Khuyến mãi", "Promotions");
        if ("personal".equals(value)) return tr("Cá nhân", "Personal");
        if ("other".equals(value)) return tr("Khác", "Other");
        return tr("Tất cả", "All");
    }

    private void showEmailFilterMenu(View anchor) {
        PopupMenu popup = new PopupMenu(this, anchor);
        String[] values = {"all", "education", "work", "finance", "meeting", "promotion", "personal", "other"};
        for (int i = 0; i < values.length; i++) {
            android.view.MenuItem item = popup.getMenu().add(0, i, i, emailFilterLabel(values[i]));
            item.setCheckable(true);
            item.setChecked(values[i].equals(emailFilter));
        }
        popup.setOnMenuItemClickListener(item -> {
            emailFilter = values[item.getItemId()];
            showEmailInbox();
            return true;
        });
        popup.show();
    }

    private void setActiveTab(String tab) {
        activeTab = tab;
        renderTabs();
    }

    private void renderTabs() {
        if (tabBar == null) return;
        tabBar.removeAllViews();
        tabBar.addView(tabItem("chat", R.drawable.ic_tab_chat, "Chat", this::showChat), weightParams());
        tabBar.addView(tabItem("email", R.drawable.ic_tab_mail, "Email", this::showEmailInbox), weightParams());
        tabBar.addView(tabItem("schedule", R.drawable.ic_tab_calendar, tr("Lịch", "Calendar"), this::showScheduleList), weightParams());
        tabBar.addView(tabItem("history", R.drawable.ic_tab_history, tr("Hoạt động", "Activity"), this::showHistory), weightParams());
        tabBar.addView(tabItem("settings", R.drawable.ic_tab_settings, tr("Cài đặt", "Settings"), this::showSettings), weightParams());
    }

    private View tabItem(String key, int iconRes, String text, Runnable action) {
        boolean active = key.equals(activeTab);
        int color = active ? Color.WHITE : MUTED;

        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.VERTICAL);
        item.setGravity(Gravity.CENTER);
        item.setPadding(dp(4), dp(6), dp(4), dp(5));
        item.setBackground(round(active ? PRIMARY : PANEL, active ? ACCENT : BORDER));
        item.setElevation(active ? dp(5) : 0);
        item.setClickable(true);
        item.setFocusable(true);
        item.setContentDescription(text);
        item.setOnClickListener(v -> {
            if (!key.equals(activeTab)) action.run();
        });

        ImageView icon = new ImageView(this);
        icon.setImageResource(iconRes);
        icon.setColorFilter(color);
        LinearLayout.LayoutParams iconParams = new LinearLayout.LayoutParams(dp(22), dp(22));
        item.addView(icon, iconParams);

        TextView label = label(text, 10, Typeface.BOLD, color);
        label.setGravity(Gravity.CENTER);
        label.setSingleLine(true);
        label.setPadding(0, dp(2), 0, 0);
        item.addView(label);
        return item;
    }

    private void setAppChromeVisible(boolean visible) {
        tabBar.setVisibility(visible ? View.VISIBLE : View.GONE);
    }

    private void showLoginScreen() {
        setAppChromeVisible(false);
        content.removeAllViews();
        content.setBackgroundColor(PANEL);

        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(24), dp(46), dp(24), dp(30));

        TextView orb = loginOrb();
        LinearLayout.LayoutParams orbParams = new LinearLayout.LayoutParams(dp(96), dp(96));
        orbParams.gravity = Gravity.CENTER_HORIZONTAL;
        body.addView(orb, orbParams);

        TextView brand = label("FlowMate AI", 30, Typeface.BOLD, TEXT);
        brand.setGravity(Gravity.CENTER);
        brand.setPadding(0, dp(18), 0, 0);
        body.addView(brand);

        TextView headline = label("Turn information into action", 24, Typeface.BOLD, TEXT);
        headline.setGravity(Gravity.CENTER);
        headline.setPadding(0, dp(34), 0, dp(10));
        body.addView(headline);

        TextView intro = label(
                "Sign in with your Google email to connect Gmail and Calendar, then choose a workspace built for the way you work.",
                15,
                Typeface.NORMAL,
                MUTED
        );
        intro.setGravity(Gravity.CENTER);
        body.addView(intro);

        LinearLayout policy = card();
        LinearLayout.LayoutParams policyParams = new LinearLayout.LayoutParams(-1, -2);
        policyParams.setMargins(0, dp(30), 0, dp(18));
        policy.setLayoutParams(policyParams);
        policy.addView(label("Your data, your control", 17, Typeface.BOLD, TEXT));
        policy.addView(policyLine("Gmail", "Read and summarize messages, deadlines, and requests."));
        policy.addView(policyLine("Google Calendar", "Show events and create changes only after confirmation."));
        policy.addView(policyLine("Privacy", "Store summaries and actions, not full email content unless needed."));
        policy.addView(policyLine("Control", "Disconnect Google and delete activity history at any time."));
        body.addView(policy);

        Button signIn = primaryButton("Login by Google");
        signIn.setOnClickListener(v -> showGooglePermissionExplanation());
        LinearLayout.LayoutParams signInParams = new LinearLayout.LayoutParams(-1, dp(52));
        signInParams.setMargins(0, 0, 0, dp(14));
        signIn.setLayoutParams(signInParams);
        body.addView(signIn);

        TextView consent = label(
                "By continuing, you agree to FlowMate AI's privacy policy and allow the permissions shown on Google's consent screen.",
                12,
                Typeface.NORMAL,
                MUTED
        );
        consent.setGravity(Gravity.CENTER);
        body.addView(consent);

        scroll.addView(body);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, -1));
    }

    private TextView loginOrb() {
        GradientDrawable orb = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{PRIMARY, ACCENT, INFO}
        );
        orb.setShape(GradientDrawable.OVAL);
        TextView view = label("✦", 32, Typeface.BOLD, Color.WHITE);
        view.setGravity(Gravity.CENTER);
        view.setBackground(orb);
        return view;
    }

    private View policyLine(String title, String detail) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(0, dp(13), 0, 0);
        row.addView(label(title, 14, Typeface.BOLD, TEXT));
        row.addView(label(detail, 13, Typeface.NORMAL, MUTED));
        return row;
    }

    private void showRoleSelection() {
        setAppChromeVisible(false);
        content.removeAllViews();
        content.setBackgroundColor(BG);

        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);
        body.setPadding(dp(20), dp(28), dp(20), dp(30));
        body.addView(label("Choose your role", 28, Typeface.BOLD, TEXT));

        TextView account = label("Signed in as " + prefs.getString("userId", ""), 13, Typeface.NORMAL, MUTED);
        account.setPadding(0, dp(6), 0, dp(8));
        body.addView(account);

        TextView description = label(
                "Each mode changes your dashboard, AI behavior, email priorities, reports, and suggested actions.",
                15,
                Typeface.NORMAL,
                MUTED
        );
        description.setPadding(0, 0, 0, dp(18));
        body.addView(description);

        String[] pendingRole = {selectedRole};
        Button continueButton = primaryButton("Continue");
        continueButton.setEnabled(!pendingRole[0].isEmpty());
        continueButton.setAlpha(continueButton.isEnabled() ? 1f : 0.45f);

        GridLayout roleGrid = new GridLayout(this);
        roleGrid.setColumnCount(2);
        roleGrid.setUseDefaultMargins(false);
        addModeCard(roleGrid, "student", "Student", "Assignments, deadlines and study schedule", pendingRole, continueButton);
        addModeCard(roleGrid, "worker", "Office Worker", "Meetings, reports and team communication", pendingRole, continueButton);
        addModeCard(roleGrid, "freelancer", "Freelancer", "Clients, projects, invoices and proposals", pendingRole, continueButton);
        addModeCard(roleGrid, "mentor", "Mentor / Teacher", "Sessions, student progress and feedback", pendingRole, continueButton);
        addModeCard(roleGrid, "business", "Business", "Operations, strategy, teams and decisions", pendingRole, continueButton);
        addModeCard(roleGrid, "creator", "Creator", "Content calendar, partnerships and campaigns", pendingRole, continueButton);
        body.addView(roleGrid, new LinearLayout.LayoutParams(-1, -2));

        continueButton.setOnClickListener(v -> {
            if (pendingRole[0].isEmpty()) return;
            selectedRole = pendingRole[0];
            prefs.edit().putString("role", selectedRole).apply();
            syncRolePreference(selectedRole);
            updateSubtitle();
            showChat();
        });
        LinearLayout.LayoutParams continueParams = new LinearLayout.LayoutParams(-1, dp(52));
        continueParams.setMargins(0, dp(12), 0, dp(12));
        body.addView(continueButton, continueParams);

        Button signOut = secondaryButton("Use another Google account");
        signOut.setOnClickListener(v -> disconnectAndReturnToLogin());
        body.addView(signOut, new LinearLayout.LayoutParams(-1, dp(46)));

        content.addView(scroll, new LinearLayout.LayoutParams(-1, -1));
    }

    private void addModeCard(
            GridLayout parent,
            String value,
            String title,
            String subtitle,
            String[] pendingRole,
            Button continueButton
    ) {
        boolean selected = value.equals(pendingRole[0]);
        LinearLayout mode = new LinearLayout(this);
        mode.setOrientation(LinearLayout.VERTICAL);
        mode.setPadding(dp(14), dp(14), dp(14), dp(14));
        mode.setBackground(round(selected ? Color.rgb(39, 34, 60) : PANEL, selected ? PRIMARY : BORDER));
        mode.setTag(value);

        TextView icon = label(roleInitial(value), 13, Typeface.BOLD, Color.WHITE);
        icon.setGravity(Gravity.CENTER);
        icon.setBackground(round(selected ? PRIMARY : PANEL_RAISED, selected ? PRIMARY : BORDER));
        mode.addView(icon, new LinearLayout.LayoutParams(dp(38), dp(38)));

        TextView titleView = label(title, 15, Typeface.BOLD, TEXT);
        titleView.setPadding(0, dp(10), 0, dp(4));
        mode.addView(titleView);
        TextView subtitleView = label(subtitle, 12, Typeface.NORMAL, MUTED);
        subtitleView.setMaxLines(3);
        mode.addView(subtitleView);
        mode.setClickable(true);
        mode.setContentDescription("Choose " + title + " mode");
        mode.setOnClickListener(v -> {
            pendingRole[0] = value;
            continueButton.setEnabled(true);
            continueButton.setAlpha(1f);
            for (int i = 0; i < parent.getChildCount(); i++) {
                View child = parent.getChildAt(i);
                boolean active = value.equals(child.getTag());
                child.setBackground(round(active ? Color.rgb(39, 34, 60) : PANEL, active ? PRIMARY : BORDER));
                if (child instanceof LinearLayout && ((LinearLayout) child).getChildCount() > 0) {
                    View childIcon = ((LinearLayout) child).getChildAt(0);
                    childIcon.setBackground(round(active ? PRIMARY : PANEL_RAISED, active ? PRIMARY : BORDER));
                }
            }
        });

        GridLayout.LayoutParams params = new GridLayout.LayoutParams();
        params.width = 0;
        params.height = dp(174);
        params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
        params.setMargins(dp(5), dp(5), dp(5), dp(5));
        parent.addView(mode, params);
    }

    private String roleInitial(String role) {
        if ("student".equals(role)) return "ST";
        if ("worker".equals(role)) return "OW";
        if ("freelancer".equals(role)) return "FR";
        if ("mentor".equals(role)) return "MT";
        if ("business".equals(role)) return "BS";
        if ("creator".equals(role)) return "CR";
        return "FM";
    }

    private void syncRolePreference(String role) {
        new Thread(() -> {
            try {
                JSONObject payload = new JSONObject();
                payload.put("user_mode", role);
                api.post("/user/profile", payload);
            } catch (Exception ignored) {
                // Local mode remains usable while the backend is unavailable.
            }
        }).start();
    }

    private String roleTitle(String role) {
        if ("student".equals(role)) return "Student Mode";
        if ("freelancer".equals(role)) return "Freelancer Mode";
        if ("creator".equals(role)) return "Creator Mode";
        if ("worker".equals(role)) return "Worker Mode";
        if ("business".equals(role)) return "Business Mode";
        if ("mentor".equals(role)) return "Mentor / Teacher Mode";
        return "FlowMate Mode";
    }

    private String roleFocus(String role) {
        if ("student".equals(role)) return tr("Ưu tiên deadline, bài tập, email lớp và họp nhóm.", "Prioritize deadlines, assignments, class email, and group meetings.");
        if ("freelancer".equals(role)) return tr("Ưu tiên tin nhắn khách hàng, deadline dự án và lịch bàn giao.", "Prioritize client messages, project deadlines, and delivery dates.");
        if ("creator".equals(role)) return tr("Ưu tiên thương hiệu, lịch nội dung, chiến dịch và lịch đăng bài.", "Prioritize brands, content calendars, campaigns, and publishing dates.");
        if ("worker".equals(role)) return tr("Ưu tiên email công việc, cuộc họp, báo cáo và tác vụ đang chờ.", "Prioritize work email, meetings, reports, and pending tasks.");
        if ("business".equals(role)) return tr("Ưu tiên vận hành, quyết định, lịch nhóm và email điều hành.", "Prioritize operations, decisions, team calendars, and executive email.");
        if ("mentor".equals(role)) return tr("Ưu tiên email học viên, lịch hướng dẫn và hạn phản hồi.", "Prioritize student email, mentoring sessions, and response deadlines.");
        return tr("Biến email và lịch thành hành động rõ ràng.", "Turn email and calendars into clear actions.");
    }

    private String[] rolePrompts(String role) {
        if ("student".equals(role)) {
            return new String[]{
                    tr("Email nào có deadline trong tuần này?", "Which emails have deadlines this week?"),
                    tr("Tóm tắt email lớp học hôm nay", "Summarize today's class email"),
                    tr("Hiện các tác vụ chưa hoàn thành", "Show incomplete tasks")
            };
        }
        if ("freelancer".equals(role)) {
            return new String[]{
                    tr("Email khách hàng nào cần trả lời?", "Which client emails need a reply?"),
                    tr("Deadline dự án nào sắp tới?", "Which project deadlines are coming up?"),
                    tr("Chuẩn bị báo cáo công việc tuần", "Prepare a weekly work report")
            };
        }
        if ("creator".equals(role)) {
            return new String[]{
                    tr("Tóm tắt email từ nhãn hàng", "Summarize brand emails"),
                    tr("Lập lịch nội dung cho tuần này", "Plan this week's content calendar"),
                    tr("Tìm các yêu cầu hợp tác cần phản hồi", "Find partnership requests that need a reply")
            };
        }
        if ("worker".equals(role)) {
            return new String[]{
                    tr("Tóm tắt email quan trọng hôm nay", "Summarize today's important email"),
                    tr("Hôm nay tôi có bao nhiêu cuộc họp?", "How many meetings do I have today?"),
                    tr("Tạo báo cáo công việc trong ngày", "Create today's work report")
            };
        }
        if ("business".equals(role)) {
            return new String[]{
                    tr("Email điều hành nào cần chú ý?", "Which executive emails need attention?"),
                    tr("Tóm tắt các quyết định trong tuần", "Summarize this week's decisions"),
                    tr("Chuẩn bị báo cáo vận hành", "Prepare an operations report")
            };
        }
        return new String[]{
                tr("Email học viên nào cần phản hồi?", "Which student emails need a reply?"),
                tr("Lịch hướng dẫn nào sắp tới?", "Which mentoring sessions are coming up?"),
                tr("Tìm các deadline phản hồi", "Find response deadlines")
        };
    }

    private void addRoleWelcome(LinearLayout parent) {
        LinearLayout card = card();
        card.setBackground(round(Color.rgb(31, 27, 48), PRIMARY_DARK));
        TextView eyebrow = label("FLOWMATE BRIEF", 11, Typeface.BOLD, ACCENT);
        eyebrow.setLetterSpacing(0.08f);
        card.addView(eyebrow);
        card.addView(label(roleTitle(selectedRole), 20, Typeface.BOLD, TEXT));
        TextView focus = label(roleFocus(selectedRole), 14, Typeface.NORMAL, MUTED);
        focus.setPadding(0, dp(6), 0, 0);
        card.addView(focus);
        TextView ready = chip("AI ready", SUCCESS);
        LinearLayout.LayoutParams readyParams = new LinearLayout.LayoutParams(-2, dp(30));
        readyParams.setMargins(0, dp(12), 0, 0);
        card.addView(ready, readyParams);
        parent.addView(card);
    }

    private String[][] roleFeatures(String role) {
        if ("student".equals(role)) {
            return new String[][]{
                    {"Assignment inbox", "Class emails and assignment requests", "education"},
                    {"Deadline planner", "Upcoming submissions and reminders", "schedule"},
                    {"Study digest", "Daily summary of important class email", "report"},
                    {"Group projects", "Meetings and shared project activity", "activity"}
            };
        }
        if ("freelancer".equals(role)) {
            return new String[][]{
                    {"Client inbox", "Messages and requests that need a reply", "work"},
                    {"Project deadlines", "Delivery dates and project milestones", "schedule"},
                    {"Invoice follow-ups", "Payment and billing messages", "finance"},
                    {"Weekly work report", "Summarize progress for your clients", "report"}
            };
        }
        if ("creator".equals(role)) {
            return new String[][]{
                    {"Brand messages", "Partnership and sponsorship email", "work"},
                    {"Content calendar", "Publishing dates and campaign events", "calendar"},
                    {"Campaign briefs", "Summarize requirements and deliverables", "report"},
                    {"Publishing reminder", "Create your next content reminder", "create"}
            };
        }
        if ("worker".equals(role)) {
            return new String[][]{
                    {"Priority inbox", "Important work email and requests", "work"},
                    {"Meeting day", "Today's meetings and upcoming events", "calendar"},
                    {"Daily brief", "Email and task summary for the day", "report"},
                    {"Task follow-up", "Pending schedules and unfinished work", "schedule"}
            };
        }
        if ("business".equals(role)) {
            return new String[][]{
                    {"Executive inbox", "High-priority business communication", "work"},
                    {"Team calendar", "Meetings, deadlines and team events", "calendar"},
                    {"Decision log", "AI and user actions with status", "activity"},
                    {"Operations report", "Daily email and action summary", "report"}
            };
        }
        return new String[][]{
                {"Student inbox", "Questions and messages needing response", "education"},
                {"Session planner", "Mentoring and teaching appointments", "schedule"},
                {"Feedback queue", "Emails and tasks waiting for feedback", "work"},
                {"Mentoring recap", "Daily communication summary", "report"}
        };
    }

    private void addRoleFeatures(LinearLayout parent) {
        TextView heading = label("Tools for " + roleTitle(selectedRole), 15, Typeface.BOLD, TEXT);
        heading.setPadding(0, dp(2), 0, dp(8));
        parent.addView(heading);

        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(2);
        for (String[] feature : roleFeatures(selectedRole)) {
            LinearLayout item = new LinearLayout(this);
            item.setOrientation(LinearLayout.VERTICAL);
            item.setPadding(dp(15), dp(13), dp(15), dp(13));
            item.setBackground(round(PANEL, BORDER));
            TextView marker = label(feature[0].substring(0, 1), 13, Typeface.BOLD, ACCENT);
            marker.setGravity(Gravity.CENTER);
            marker.setBackground(round(Color.rgb(39, 34, 60), PRIMARY_DARK));
            item.addView(marker, new LinearLayout.LayoutParams(dp(34), dp(34)));
            item.addView(label(feature[0], 15, Typeface.BOLD, TEXT));
            TextView detail = label(feature[1], 13, Typeface.NORMAL, MUTED);
            detail.setPadding(0, dp(3), 0, 0);
            detail.setMaxLines(3);
            item.addView(detail);
            item.setClickable(true);
            item.setOnClickListener(v -> openRoleFeature(feature[2]));

            GridLayout.LayoutParams params = new GridLayout.LayoutParams();
            params.width = 0;
            params.height = dp(154);
            params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
            params.setMargins(dp(4), dp(4), dp(4), dp(4));
            grid.addView(item, params);
        }
        parent.addView(grid, new LinearLayout.LayoutParams(-1, -2));
    }

    private void openRoleFeature(String action) {
        if ("education".equals(action) || "work".equals(action) || "finance".equals(action)) {
            emailFilter = action;
            showEmailInbox();
        } else if ("schedule".equals(action)) {
            showScheduleList();
        } else if ("calendar".equals(action)) {
            showCalendarEvents();
        } else if ("activity".equals(action)) {
            showHistory();
        } else if ("report".equals(action)) {
            showEmailReport();
        } else if ("create".equals(action)) {
            showScheduleCreate();
        }
    }

    private View quickPromptsRow(EditText input) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(dp(12), dp(2), dp(12), dp(6));
        for (String prompt : rolePrompts(selectedRole)) {
            row.addView(promptChip(prompt, () -> {
                input.setText(prompt);
                input.setSelection(input.length());
            }));
        }
        return horizontal(row);
    }

    private Button promptChip(String text, Runnable action) {
        Button chip = new Button(this);
        chip.setText(text);
        chip.setTextColor(MUTED);
        chip.setTextSize(11);
        chip.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        chip.setAllCaps(false);
        chip.setMinHeight(dp(34));
        chip.setPadding(dp(14), 0, dp(14), 0);
        chip.setBackground(round(PANEL_RAISED, BORDER));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(34));
        params.setMargins(0, 0, dp(8), 0);
        chip.setLayoutParams(params);
        chip.setOnClickListener(v -> action.run());
        return chip;
    }

    private void showGooglePermissionExplanation() {
        new AlertDialog.Builder(this)
                .setTitle(tr("Kết nối Google với FlowMate AI", "Connect Google to FlowMate AI"))
                .setMessage(tr(
                        "FlowMate cần quyền hồ sơ để hiển thị tên và email; Gmail để đọc, tóm tắt và tìm deadline; Google Calendar để tạo, sửa, xóa sự kiện sau khi bạn xác nhận.\n\nỨng dụng chỉ lưu tóm tắt, tác vụ đã trích xuất và nhật ký hoạt động khi cần. Bạn có thể ngắt kết nối bất cứ lúc nào.",
                        "FlowMate needs profile access to display your name and email, Gmail access to read, summarize, and find deadlines, and Google Calendar access to create, edit, or delete events after you confirm.\n\nThe app only stores summaries, extracted tasks, and activity history when needed. You can disconnect at any time."
                ))
                .setNegativeButton(tr("Để sau", "Later"), null)
                .setPositiveButton(tr("Đăng nhập bằng Google", "Sign in with Google"), (dialog, which) -> {
                    Intent signInIntent = mGoogleSignInClient.getSignInIntent();
                    startActivityForResult(signInIntent, RC_SIGN_IN);
                })
                .show();
    }

    private void clearLocalSession() {
        api.setAccessToken("");
        selectedRole = "";
        prefs.edit()
                .remove("userId")
                .remove("accessToken")
                .remove("role")
                .remove("googleAuthenticated")
                .apply();
        updateSubtitle();
    }

    private void disconnectAndReturnToLogin() {
        new Thread(() -> {
            try {
                api.post("/email/logout", new JSONObject());
            } catch (Exception ignored) {
                // Local sign-out must still work if the backend is temporarily offline.
            }
            runOnUiThread(() -> mGoogleSignInClient.signOut().addOnCompleteListener(task -> {
                clearLocalSession();
                showLoginScreen();
            }));
        }).start();
    }

    private void showChat() {
        setAppChromeVisible(true);
        content.setBackgroundColor(BG);
        setActiveTab("chat");
        content.removeAllViews();
        LinearLayout top = titleRow("Assistant");
        Button mode = secondaryButton(roleTitle(selectedRole));
        mode.setOnClickListener(v -> showRoleSelection());
        top.addView(mode);
        Button clear = secondaryButton("Clear");
        clear.setOnClickListener(v -> runApi(() -> api.post("/chat/clear", new JSONObject()), data -> {
            chatList.removeAllViews();
            toast(tr("Đã xóa lịch sử chat", "Chat history cleared"));
        }));
        top.addView(clear);
        content.addView(top);

        ScrollView scroll = new ScrollView(this);
        chatList = new LinearLayout(this);
        chatList.setOrientation(LinearLayout.VERTICAL);
        chatList.setPadding(dp(16), dp(8), dp(16), dp(12));
        addRoleWelcome(chatList);
        addRoleFeatures(chatList);
        scroll.addView(chatList);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        EditText input = input(tr("Hỏi FlowMate về email, lịch và công việc...", "Ask FlowMate about email, calendars, and work..."), true);
        content.addView(quickPromptsRow(input));

        LinearLayout composer = new LinearLayout(this);
        composer.setOrientation(LinearLayout.HORIZONTAL);
        composer.setPadding(dp(12), dp(10), dp(12), dp(10));
        composer.setBackgroundColor(BG);
        Button send = primaryButton(tr("Gửi", "Send"));
        send.setOnClickListener(v -> {
            String message = input.getText().toString().trim();
            if (message.isEmpty()) return;
            input.setText("");
            addBubble(message, true);
            runApi(() -> {
                JSONObject body = new JSONObject();
                body.put("message", message);
                body.put("mode", selectedRole);
                return api.post("/chat/message", body);
            }, data -> {
                addBubble(data.optString("response", tr("Không có phản hồi.", "No response received.")), false);
                JSONObject suggestion = data.optJSONObject("schedule_suggestion");
                if (suggestion != null) addScheduleSuggestion(suggestion);
                scroll.post(() -> scroll.fullScroll(View.FOCUS_DOWN));
            });
        });
        composer.addView(input, new LinearLayout.LayoutParams(0, dp(72), 1));
        composer.addView(send, new LinearLayout.LayoutParams(dp(72), dp(72)));
        content.addView(composer);

        runApi(() -> api.get("/chat/history?limit=20"), data -> {
            JSONArray history = data.optJSONArray("history");
            if (history == null || history.length() == 0) {
                addMuted(chatList, tr("Thử một gợi ý ở trên, hoặc nhập yêu cầu của bạn.", "Try a suggestion above, or enter your request."));
                return;
            }
            for (int i = history.length() - 1; i >= 0; i--) {
                JSONObject item = history.optJSONObject(i);
                if (item == null) continue;
                if (!item.optString("user_message").isEmpty()) addBubble(item.optString("user_message"), true);
                if (!item.optString("assistant_response").isEmpty()) addBubble(item.optString("assistant_response"), false);
            }
        });
    }

    private void addBubble(String text, boolean user) {
        TextView bubble = label(text, 15, Typeface.NORMAL, user ? Color.WHITE : TEXT);
        bubble.setPadding(dp(12), dp(10), dp(12), dp(10));
        bubble.setBackground(round(user ? PRIMARY : PANEL_RAISED, user ? PRIMARY : BORDER));
        LinearLayout row = new LinearLayout(this);
        row.setGravity(user ? Gravity.END : Gravity.START);
        row.setPadding(0, dp(5), 0, dp(5));
        row.addView(bubble, new LinearLayout.LayoutParams(-2, -2));
        chatList.addView(row);
    }

    private void addScheduleSuggestion(JSONObject suggestion) {
        LinearLayout card = card();
        card.addView(label(tr("Gợi ý tạo lịch", "Event suggestion"), 15, Typeface.BOLD, TEXT));
        card.addView(label(suggestion.optString("title", tr("Lịch hẹn", "Appointment")), 14, Typeface.NORMAL, TEXT));
        card.addView(label(suggestion.optString("start_time", tr("Chưa có thời gian", "Time not specified")), 12, Typeface.NORMAL, MUTED));
        Button create = primaryButton(tr("Tạo lịch", "Create event"));
        create.setOnClickListener(v -> runApi(() -> {
            JSONObject body = new JSONObject();
            body.put("title", suggestion.optString("title", tr("Lịch hẹn", "Appointment")));
            body.put("description", suggestion.optString("description", ""));
            body.put("start_time", suggestion.optString("start_time"));
            body.put("attendees", suggestion.optJSONArray("attendees") == null ? new JSONArray() : suggestion.optJSONArray("attendees"));
            return api.post("/schedule/create", body);
        }, data -> toast(tr("Đã tạo lịch", "Event created"))));
        card.addView(create);
        chatList.addView(card);
    }

    private void showEmailInbox() {
        setAppChromeVisible(true);
        setActiveTab("email");
        content.removeAllViews();
        content.addView(titleRow("Email"));
        content.addView(emailNav());

        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(16), dp(10), dp(16), dp(20));
        scroll.addView(body);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout config = card();
        config.addView(label("GOOGLE WORKSPACE", 11, Typeface.BOLD, SUCCESS));
        TextView connectedEmail = label(prefs.getString("userId", ""), 14, Typeface.NORMAL, MUTED);
        connectedEmail.setPadding(0, dp(5), 0, dp(4));
        config.addView(connectedEmail);
        config.addView(label("Gmail and Calendar are connected.", 12, Typeface.NORMAL, SUCCESS));
        body.addView(config);

        LinearLayout actions = rowWrap();
        Button openGmail = secondaryButton(tr("Mở Gmail", "Open Gmail"));
        openGmail.setOnClickListener(v -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://mail.google.com"))));
        Button logout = secondaryButton(tr("Ngắt kết nối", "Disconnect"));
        logout.setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle(tr("Ngắt tài khoản Google?", "Disconnect Google account?"))
                .setMessage(tr("FlowMate AI sẽ xóa phiên kết nối trên thiết bị. Lịch sử hoạt động vẫn được giữ cho đến khi bạn xóa.", "FlowMate AI will remove the connected session from this device. Activity history remains until you delete it."))
                .setNegativeButton(tr("Hủy", "Cancel"), null)
                .setPositiveButton(tr("Ngắt kết nối", "Disconnect"), (dialog, which) ->
                        runApi(() -> api.post("/email/logout", new JSONObject()), data ->
                                mGoogleSignInClient.signOut().addOnCompleteListener(task -> {
                                    toast(tr("Đã ngắt kết nối Google", "Google disconnected"));
                                    clearLocalSession();
                                    showLoginScreen();
                                })
                        )
                )
                .show());
        actions.addView(openGmail);
        actions.addView(logout);
        body.addView(horizontal(actions));

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        EditText search = input(tr("Tìm người gửi, tiêu đề, nội dung...", "Search sender, subject, content..."), false);
        search.setSingleLine(true);
        search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        Button searchButton = primaryButton(tr("Tìm", "Search"));
        View.OnClickListener runSearch = v -> {
            emailSearch = search.getText().toString().trim();
            loadEmails(emailIncludeRead);
        };
        searchButton.setOnClickListener(runSearch);
        search.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                runSearch.onClick(v);
                return true;
            }
            return false;
        });
        searchRow.addView(search, new LinearLayout.LayoutParams(0, dp(48), 1));
        Button filterButton = secondaryButton("≡");
        filterButton.setContentDescription(tr("Lọc email", "Filter email"));
        filterButton.setOnClickListener(v -> showEmailFilterMenu(filterButton));
        LinearLayout.LayoutParams filterParams = new LinearLayout.LayoutParams(dp(48), dp(48));
        filterParams.setMargins(dp(8), 0, 0, 0);
        searchRow.addView(filterButton, filterParams);
        LinearLayout.LayoutParams searchButtonParams = new LinearLayout.LayoutParams(-2, dp(48));
        searchButtonParams.setMargins(dp(8), 0, 0, 0);
        searchRow.addView(searchButton, searchButtonParams);
        body.addView(searchRow);

        LinearLayout filters = rowWrap();
        filters.addView(chip(
                tr("Bộ lọc: ", "Filter: ") + emailFilterLabel(emailFilter),
                ACCENT
        ));
        CheckBox includeRead = new CheckBox(this);
        includeRead.setText(tr("Giữ email đã đọc", "Include read email"));
        includeRead.setTextColor(TEXT);
        includeRead.setChecked(emailIncludeRead);
        includeRead.setOnCheckedChangeListener((buttonView, checked) -> {
            emailIncludeRead = checked;
            loadEmails(checked);
        });
        filters.addView(includeRead);
        body.addView(filters);

        emailList = new LinearLayout(this);
        emailList.setOrientation(LinearLayout.VERTICAL);
        body.addView(emailList);
        loadEmails(emailIncludeRead);
    }

    private void loadEmails(boolean includeRead) {
        if (emailList == null) return;
        emailIncludeRead = includeRead;
        emailList.removeAllViews();
        addMuted(emailList, tr("Đang quét tối đa 70 email...", "Scanning up to 70 emails..."));
        runApi(() -> api.get(
                "/email/get-unread?max_results=70&page=1&filter=" + emailFilter
                        + "&include_read=" + includeRead
                        + "&search=" + URLEncoder.encode(emailSearch, "UTF-8")
        ), data -> {
            emailList.removeAllViews();
            JSONArray emails = data.optJSONArray("emails");
            emailList.addView(inboxSummaryCard(data, emails, includeRead));
            addMeetingSuggestions(emailList, data.optJSONArray("meeting_suggestions"));
            if (emails == null || emails.length() == 0) {
                addMuted(emailList, emailSearch.isEmpty()
                        ? tr("Không có email hoặc chưa đăng nhập Gmail.", "No email found or Gmail is not connected.")
                        : tr("Không tìm thấy email cho từ khóa: ", "No email found for: ") + emailSearch);
                return;
            }
            TextView count = label(tr("HỘP THƯ", "INBOX"), 12, Typeface.BOLD, MUTED);
            count.setLetterSpacing(0.08f);
            count.setPadding(0, 0, 0, dp(10));
            emailList.addView(count);
            for (int i = 0; i < emails.length(); i++) {
                JSONObject email = emails.optJSONObject(i);
                if (email != null) emailList.addView(emailCard(email));
            }
        });
    }

    private View emailCard(JSONObject email) {
        LinearLayout card = card();
        if (email.optBoolean("is_unread", false)) {
            card.setBackground(round(Color.rgb(27, 25, 39), PRIMARY_DARK));
        } else {
            card.setBackground(round(Color.rgb(17, 45, 42), SUCCESS));
        }

        LinearLayout senderRow = new LinearLayout(this);
        senderRow.setOrientation(LinearLayout.HORIZONTAL);
        TextView sender = label(email.optString("sender", email.optString("from", tr("Người gửi", "Sender"))), 13, Typeface.BOLD, TEXT);
        sender.setSingleLine(true);
        sender.setEllipsize(TextUtils.TruncateAt.END);
        senderRow.addView(sender, new LinearLayout.LayoutParams(0, -2, 1));
        TextView date = label(shortDate(email.optString("date", "")), 11, Typeface.NORMAL, TEXT_DIM);
        senderRow.addView(date);
        card.addView(senderRow);

        TextView subject = label(email.optString("subject", tr("(Không tiêu đề)", "(No subject)")), 15, Typeface.BOLD, TEXT);
        subject.setPadding(0, dp(5), 0, dp(3));
        card.addView(subject);
        TextView preview = label(email.optString("summary", email.optString("snippet", "")), 14, Typeface.NORMAL, MUTED);
        preview.setMaxLines(3);
        preview.setEllipsize(TextUtils.TruncateAt.END);
        card.addView(preview);

        LinearLayout tags = rowWrap();
        String tag = email.optString("tag", "other");
        tags.addView(chip(friendlyTag(tag), tagColor(tag)));
        if (isUrgentEmail(email)) tags.addView(chip(tr("Cần xử lý", "Needs action"), DANGER));
        if (!email.optBoolean("is_unread", false)) tags.addView(chip(tr("Đã đọc", "Read"), SUCCESS));
        card.addView(tags);

        card.setClickable(true);
        card.setContentDescription(tr("Mở tùy chọn xem email ", "Open email options for ") + email.optString("subject", ""));
        card.setOnClickListener(v -> showEmailOptions(email));

        LinearLayout actions = rowWrap();
        Button full = secondaryButton(tr("Xem đầy đủ", "View full email"));
        full.setOnClickListener(v -> openFullEmail(email));
        Button summary = primaryButton(tr("Tóm tắt AI", "AI summary"));
        summary.setOnClickListener(v -> openEmailSummary(email));
        Button read = secondaryButton(email.optBoolean("is_unread", false)
                ? tr("Đánh dấu đã đọc", "Mark as read")
                : tr("Đánh dấu chưa đọc", "Mark as unread"));
        read.setOnClickListener(v -> runApi(() -> {
            boolean isUnread = email.optBoolean("is_unread", false);
            return api.post("/email/" + (isUnread ? "mark-as-read/" : "mark-as-unread/") + email.optString("id"), new JSONObject());
        }, data -> {
            boolean nowUnread = !email.optBoolean("is_unread", false);
            try {
                email.put("is_unread", nowUnread);
            } catch (Exception ignored) {
            }
            card.setBackground(nowUnread
                    ? round(Color.rgb(27, 25, 39), PRIMARY_DARK)
                    : round(Color.rgb(17, 45, 42), SUCCESS));
            read.setText(nowUnread ? "Danh dau da doc" : "Danh dau chua doc");
            toast(nowUnread ? tr("Đã đánh dấu chưa đọc", "Marked as unread") : tr("Đã đánh dấu đã đọc", "Marked as read"));
        }));
        actions.addView(full);
        actions.addView(summary);
        actions.addView(read);
        card.addView(horizontal(actions));
        return card;
    }

    private View inboxSummaryCard(JSONObject data, JSONArray emails, boolean includeRead) {
        int matched = data.optInt("matched_count", emails == null ? 0 : emails.length());
        int scanned = data.optInt("total_filtered", matched);
        int urgent = 0;
        int meetings = 0;
        if (emails != null) {
            for (int i = 0; i < emails.length(); i++) {
                JSONObject email = emails.optJSONObject(i);
                if (email == null) continue;
                if (isUrgentEmail(email)) urgent++;
                if ("meeting".equals(email.optString("tag"))) meetings++;
            }
        }

        LinearLayout summary = card();
        summary.setBackground(round(Color.rgb(31, 27, 48), PRIMARY_DARK));
        TextView title = label("✦ AI SUMMARY · TODAY", 11, Typeface.BOLD, ACCENT);
        title.setLetterSpacing(0.08f);
        summary.addView(title);
        String message = "Scanned " + scanned + " messages. " + matched + " match the current filter";
        if (urgent > 0) message += ", and " + urgent + " may need action";
        message += ".";
        TextView detail = label(message, 14, Typeface.NORMAL, MUTED);
        detail.setPadding(0, dp(7), 0, dp(8));
        summary.addView(detail);

        LinearLayout stats = rowWrap();
        stats.addView(statPill(String.valueOf(scanned), "scanned"));
        stats.addView(statPill(String.valueOf(matched), "important"));
        stats.addView(statPill(String.valueOf(urgent), "urgent"));
        if (meetings > 0) stats.addView(statPill(String.valueOf(meetings), "meetings"));
        summary.addView(horizontal(stats));
        return summary;
    }

    private void addMeetingSuggestions(LinearLayout parent, JSONArray suggestions) {
        if (suggestions == null || suggestions.length() == 0) return;

        TextView heading = label(
                tr("GỢI Ý ĐẶT LỊCH TỪ EMAIL", "CALENDAR SUGGESTIONS FROM EMAIL"),
                12,
                Typeface.BOLD,
                WARNING
        );
        heading.setLetterSpacing(0.08f);
        heading.setPadding(0, dp(14), 0, dp(10));
        parent.addView(heading);

        for (int i = 0; i < suggestions.length(); i++) {
            JSONObject suggestion = suggestions.optJSONObject(i);
            if (suggestion == null) continue;

            LinearLayout card = card();
            card.setBackground(round(Color.rgb(43, 34, 20), Color.rgb(122, 86, 26)));
            card.addView(label(
                    suggestion.optString("title", suggestion.optString("subject", tr("Lịch hẹn từ email", "Appointment from email"))),
                    16,
                    Typeface.BOLD,
                    TEXT
            ));
            card.addView(label(
                    tr("Từ: ", "From: ") + suggestion.optString("sender", tr("Không xác định", "Unknown")),
                    12,
                    Typeface.NORMAL,
                    MUTED
            ));
            String start = suggestion.optString("start_time", "").trim();
            card.addView(label(
                    start.isEmpty()
                            ? tr("Chưa xác định thời gian", "Time not detected")
                            : tr("Thời gian: ", "Time: ") + start,
                    13,
                    Typeface.BOLD,
                    start.isEmpty() ? WARNING : SUCCESS
            ));
            String snippet = suggestion.optString("snippet", "").trim();
            if (!snippet.isEmpty()) {
                TextView preview = label(snippet, 13, Typeface.NORMAL, MUTED);
                preview.setMaxLines(3);
                preview.setEllipsize(TextUtils.TruncateAt.END);
                preview.setPadding(0, dp(6), 0, 0);
                card.addView(preview);
            }

            LinearLayout actions = rowWrap();
            Button create = primaryButton(tr("Tạo lịch", "Create event"));
            create.setOnClickListener(v -> showScheduleCreate(suggestion));
            Button dismiss = secondaryButton(tr("Bỏ qua", "Dismiss"));
            dismiss.setOnClickListener(v -> runApi(() -> {
                JSONObject payload = new JSONObject();
                payload.put("status", "dismissed");
                return api.patch(
                        "/email/meeting-suggestions/" + suggestion.optInt("id") + "/status",
                        payload
                );
            }, data -> {
                toast(tr("Đã bỏ qua gợi ý", "Suggestion dismissed"));
                loadEmails(emailIncludeRead);
            }));
            actions.addView(create);
            actions.addView(dismiss);
            card.addView(horizontal(actions));
            parent.addView(card);
        }
    }

    private boolean isUrgentEmail(JSONObject email) {
        String value = (
                email.optString("subject", "") + " " +
                email.optString("summary", "") + " " +
                email.optString("snippet", "")
        ).toLowerCase(Locale.US);
        return value.contains("urgent")
                || value.contains("deadline")
                || value.contains("action required")
                || value.contains("due today")
                || value.contains("eod");
    }

    private String friendlyTag(String tag) {
        if ("education".equals(tag)) return "Education";
        if ("work".equals(tag)) return "Work";
        if ("finance".equals(tag)) return "Finance";
        if ("meeting".equals(tag)) return "Meeting";
        if ("promotion".equals(tag)) return "Promotion";
        if ("personal".equals(tag)) return "Personal";
        return "Other";
    }

    private int tagColor(String tag) {
        if ("meeting".equals(tag)) return ACCENT;
        if ("finance".equals(tag)) return WARNING;
        if ("education".equals(tag)) return SUCCESS;
        if ("work".equals(tag)) return INFO;
        if ("promotion".equals(tag)) return DANGER;
        return MUTED;
    }

    private String shortDate(String raw) {
        if (raw == null || raw.isEmpty()) return "";
        return raw.length() > 16 ? raw.substring(0, 16) : raw;
    }

    private void showEmailOptions(JSONObject email) {
        String[] options = {
                tr("Xem đầy đủ", "View full email"),
                tr("Tóm tắt bằng AI", "Summarize with AI")
        };
        new AlertDialog.Builder(this)
                .setTitle(email.optString("subject", "Email"))
                .setItems(options, (dialog, which) -> {
                    if (which == 0) {
                        openFullEmail(email);
                    } else {
                        openEmailSummary(email);
                    }
                })
                .setNegativeButton(tr("Đóng", "Close"), null)
                .show();
    }

    private void openFullEmail(JSONObject email) {
        runApi(() -> api.get("/email/get-email-body/" + email.optString("id")), data -> {
            String body = data.optString("body", email.optString("snippet", ""));
            JSONObject fullEmail = data.optJSONObject("email");
            JSONArray attachments = fullEmail == null ? null : fullEmail.optJSONArray("attachments");

            LinearLayout detail = new LinearLayout(this);
            detail.setOrientation(LinearLayout.VERTICAL);
            detail.setPadding(dp(20), dp(4), dp(20), dp(8));
            TextView bodyView = label(body, 14, Typeface.NORMAL, TEXT);
            bodyView.setTextIsSelectable(true);
            bodyView.setLineSpacing(dp(2), 1.05f);
            detail.addView(bodyView);

            if (attachments != null && attachments.length() > 0) {
                TextView attachmentHeading = label(
                        tr("FILE ĐÍNH KÈM", "ATTACHMENTS") + " · " + attachments.length(),
                        12,
                        Typeface.BOLD,
                        ACCENT
                );
                attachmentHeading.setLetterSpacing(0.08f);
                attachmentHeading.setPadding(0, dp(18), 0, dp(8));
                detail.addView(attachmentHeading);
                for (int i = 0; i < attachments.length(); i++) {
                    JSONObject attachment = attachments.optJSONObject(i);
                    if (attachment == null) continue;
                    Button fileButton = secondaryButton(
                            attachment.optString("filename", tr("File đính kèm", "Attachment"))
                                    + " · " + formatFileSize(attachment.optLong("size", 0))
                    );
                    fileButton.setAllCaps(false);
                    fileButton.setOnClickListener(v -> downloadAndOpenAttachment(
                            email.optString("id"),
                            attachment
                    ));
                    detail.addView(fileButton);
                }
            }

            ScrollView scroll = new ScrollView(this);
            scroll.addView(detail);
            AlertDialog dialog = new AlertDialog.Builder(this)
                    .setTitle(email.optString("subject", "Email"))
                    .setView(scroll)
                    .setNegativeButton(tr("Đóng", "Close"), null)
                    .setPositiveButton(tr("Tóm tắt AI", "AI summary"), null)
                    .create();
            dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                dialog.dismiss();
                openEmailSummary(email);
            }));
            dialog.show();
        });
    }

    private void downloadAndOpenAttachment(String emailId, JSONObject attachment) {
        String attachmentId = attachment.optString("id", "");
        if (emailId.isEmpty() || attachmentId.isEmpty()) return;
        String filename = safeFilename(attachment.optString("filename", "attachment"));
        String mimeType = attachment.optString("mime_type", "application/octet-stream");
        toast(tr("Đang tải file...", "Downloading file..."));

        new Thread(() -> {
            try {
                File directory = new File(getCacheDir(), "attachments");
                File destination = new File(directory, filename);
                ApiClient.DownloadResult result = api.download(
                        "/email/attachment/" + Uri.encode(emailId) + "/" + Uri.encode(attachmentId),
                        destination
                );
                runOnUiThread(() -> openDownloadedAttachment(
                        result.file,
                        mimeType.isEmpty() ? result.mimeType : mimeType
                ));
            } catch (Exception error) {
                runOnUiThread(() -> alert(
                        tr("Không tải được file", "Unable to download attachment"),
                        error.getMessage()
                ));
            }
        }).start();
    }

    private void openDownloadedAttachment(File file, String mimeType) {
        Uri uri = FileProvider.getUriForFile(
                this,
                BuildConfig.APPLICATION_ID + ".fileprovider",
                file
        );
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, mimeType == null || mimeType.isEmpty()
                ? "application/octet-stream"
                : mimeType);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException error) {
            alert(
                    tr("Không có ứng dụng mở file", "No app can open this file"),
                    tr("File đã được tải nhưng thiết bị chưa có ứng dụng phù hợp.", "The file was downloaded, but no compatible app is installed.")
            );
        }
    }

    private String safeFilename(String value) {
        String safe = value == null ? "attachment" : value.trim();
        safe = safe.replaceAll("[\\\\/:*?\"<>|\\r\\n]+", "_");
        return safe.isEmpty() ? "attachment" : safe;
    }

    private String formatFileSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        double size = bytes / 1024.0;
        if (size < 1024) return String.format(Locale.US, size >= 10 ? "%.0f KB" : "%.1f KB", size);
        size /= 1024.0;
        return String.format(Locale.US, size >= 10 ? "%.0f MB" : "%.1f MB", size);
    }

    private void openEmailSummary(JSONObject email) {
        toast(tr("AI đang tóm tắt email...", "AI is summarizing the email..."));
        runApi(
                () -> api.get("/email/summary/" + email.optString("id")),
                data -> alert(
                        tr("Tóm tắt AI", "AI summary"),
                        data.optString("summary", tr("Không tạo được bản tóm tắt.", "Unable to create a summary."))
                )
        );
    }

    private void showEmailCompose() {
        setActiveTab("email");
        content.removeAllViews();
        content.addView(titleRow(tr("Viết thư", "Compose")));
        content.addView(emailNav());
        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);
        LinearLayout form = card();
        EditText to = input(tr("Người nhận", "Recipient"), false);
        EditText subject = input(tr("Tiêu đề", "Subject"), false);
        EditText message = input(tr("Nội dung", "Content"), true);
        form.addView(fieldLabel(tr("Người nhận", "Recipient")));
        form.addView(to);
        form.addView(fieldLabel(tr("Tiêu đề", "Subject")));
        form.addView(subject);
        form.addView(fieldLabel(tr("Nội dung", "Content")));
        form.addView(message, new LinearLayout.LayoutParams(-1, dp(150)));
        Button send = primaryButton(tr("Gửi email", "Send email"));
        send.setOnClickListener(v -> runApi(() -> {
            JSONObject payload = new JSONObject();
            payload.put("to", to.getText().toString().trim());
            payload.put("subject", subject.getText().toString().trim());
            payload.put("body", message.getText().toString().trim());
            return api.post("/email/send-reply", payload);
        }, data -> {
            to.setText("");
            subject.setText("");
            message.setText("");
            toast(tr("Đã gửi email", "Email sent"));
        }));
        form.addView(send);
        body.addView(form);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    }

    private void showEmailReport() {
        setActiveTab("email");
        content.removeAllViews();
        content.addView(titleRow(tr("Báo cáo email", "Email report")));
        content.addView(emailNav());
        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);
        LinearLayout form = card();
        EditText date = input("DD/MM/YYYY", false);
        date.setText(new java.text.SimpleDateFormat("dd/MM/yyyy", java.util.Locale.US)
                .format(new java.util.Date()));
        form.addView(fieldLabel(tr("Ngày báo cáo", "Report date")));
        form.addView(date);
        Button generate = primaryButton(tr("Tạo báo cáo", "Generate report"));
        form.addView(generate);
        LinearLayout result = new LinearLayout(this);
        result.setOrientation(LinearLayout.VERTICAL);
        form.addView(result);
        generate.setOnClickListener(v -> runApi(() -> {
            JSONObject payload = new JSONObject();
            payload.put("date", date.getText().toString().trim());
            payload.put("max_results", 50);
            return api.post("/email/summarize-by-date", payload);
        }, data -> renderReport(result, data, date.getText().toString().trim())));
        body.addView(form);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    }

    private void renderReport(LinearLayout result, JSONObject data, String reportDate) {
        result.removeAllViews();
        result.addView(label(tr("Tổng ", "Total ") + data.optInt("total_emails", 0) + " email", 15, Typeface.BOLD, TEXT));
        JSONArray rows = data.optJSONArray("rows");
        if (rows == null || rows.length() == 0) {
            addMuted(result, tr("Không có email trong ngày này.", "No email found for this date."));
            return;
        }
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row == null) continue;
            LinearLayout item = card();
            item.addView(label((i + 1) + ". " + row.optString("subject", "Email"), 14, Typeface.BOLD, TEXT));
            item.addView(label(row.optString("summary", ""), 14, Typeface.NORMAL, MUTED));
            if (row.optBoolean("is_meeting", false)) {
                Button create = secondaryButton(tr("Tạo lịch", "Create event"));
                create.setOnClickListener(v -> createScheduleFromReport(row, reportDate));
                item.addView(create);
            }
            result.addView(item);
        }
    }

    private void createScheduleFromReport(JSONObject row, String reportDate) {
        runApi(() -> {
            JSONObject payload = new JSONObject();
            payload.put("title", row.optString("schedule_title", row.optString("subject", tr("Lịch hẹn từ email", "Appointment from email"))));
            payload.put("description", row.optString("suggested_description", row.optString("summary", "")));
            payload.put("start_time", row.optString("suggested_start_time", reportDateToStart(reportDate)));
            payload.put("end_time", row.optString("suggested_end_time", ""));
            payload.put("attendees", new JSONArray());
            return api.post("/schedule/create", payload);
        }, data -> toast(tr("Đã tạo lịch", "Event created")));
    }

    private void showScheduleList() {
        setAppChromeVisible(true);
        setActiveTab("schedule");
        content.removeAllViews();
        content.addView(titleRow(tr("Lịch", "Calendar")));
        content.addView(scheduleNav());
        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);
        addMuted(body, tr("Đang đồng bộ sự kiện...", "Syncing events..."));
        FrameLayout container = new FrameLayout(this);
        container.addView(scroll, new FrameLayout.LayoutParams(-1, -1));
        container.addView(fab(this::showScheduleCreate), fabParams());
        content.addView(container, new LinearLayout.LayoutParams(-1, 0, 1));
        runApi(() -> api.get("/schedule/unified?max_results=50"), data -> {
            JSONArray schedules = data.optJSONArray("items");
            renderScheduleDashboard(
                    body,
                    schedules == null ? new JSONArray() : schedules,
                    data.optBoolean("calendar_connected")
            );
        });
    }

    private void renderScheduleDashboard(LinearLayout body, JSONArray schedules, boolean calendarConnected) {
        body.removeAllViews();

        LinearLayout hero = card();
        hero.setBackground(round(Color.rgb(27, 24, 48), Color.rgb(78, 67, 139)));
        hero.addView(label(tr("LỊCH CỦA BẠN", "YOUR CALENDAR"), 11, Typeface.BOLD, ACCENT));
        hero.addView(label(tr("Lên kế hoạch ít hơn. Nắm rõ ngày của bạn.", "Plan less. See the day clearly."), 22, Typeface.BOLD, TEXT));
        hero.addView(label(
                calendarConnected
                        ? tr("Sự kiện FlowMate và Google Calendar đã được đồng bộ.", "FlowMate and Google Calendar events are synced.")
                        : tr("Sự kiện đang được quản lý trên FlowMate.", "Events are managed in FlowMate."),
                13,
                Typeface.NORMAL,
                MUTED
        ));
        LinearLayout heroStats = rowWrap();
        heroStats.addView(statPill(String.valueOf(schedules.length()), tr("sự kiện", "events")));
        heroStats.addView(statPill(String.valueOf(countEventDays(schedules)), tr("ngày có lịch", "active days")));
        hero.addView(horizontal(heroStats));
        body.addView(hero);

        addMiniCalendar(body, schedules, dateKey -> {
            selectedScheduleDate = dateKey.equals(selectedScheduleDate) ? "" : dateKey;
            renderScheduleDashboard(body, schedules, calendarConnected);
        });

        JSONArray visibleSchedules = schedulesForDate(schedules, selectedScheduleDate);
        body.addView(scheduleOverview(visibleSchedules, selectedScheduleDate));

        TextView section = label(
                selectedScheduleDate.isEmpty() ? tr("TỔNG HỢP SỰ KIỆN", "EVENT OVERVIEW") : tr("SỰ KIỆN TRONG NGÀY", "EVENTS FOR THE DAY"),
                11,
                Typeface.BOLD,
                selectedScheduleDate.isEmpty() ? MUTED : ACCENT
        );
        section.setLetterSpacing(0.08f);
        section.setPadding(0, dp(2), 0, dp(10));
        body.addView(section);

        if (visibleSchedules.length() == 0) {
            LinearLayout empty = card();
            empty.setGravity(Gravity.CENTER);
            empty.addView(label(
                    selectedScheduleDate.isEmpty()
                            ? tr("Chưa có sự kiện sắp tới", "No upcoming events")
                            : tr("Ngày này chưa có sự kiện", "No events for this date"),
                    17,
                    Typeface.BOLD,
                    TEXT
            ));
            TextView hint = label(tr("Chạm vào ngày có dấu chấm để xem chi tiết.", "Tap a dotted date to view details."), 13, Typeface.NORMAL, MUTED);
            hint.setGravity(Gravity.CENTER);
            hint.setPadding(0, dp(6), 0, 0);
            empty.addView(hint);
            body.addView(empty);
            return;
        }

        for (int i = 0; i < visibleSchedules.length(); i++) {
            JSONObject schedule = visibleSchedules.optJSONObject(i);
            if (schedule != null) body.addView(scheduleCard(schedule));
        }
    }

    private View scheduleCard(JSONObject schedule) {
        LinearLayout shell = new LinearLayout(this);
        shell.setOrientation(LinearLayout.HORIZONTAL);
        shell.setBackground(round(PANEL, BORDER));
        LinearLayout.LayoutParams shellParams = new LinearLayout.LayoutParams(-1, -2);
        shellParams.setMargins(0, 0, 0, dp(12));
        shell.setLayoutParams(shellParams);

        View accent = new View(this);
        accent.setBackgroundColor(eventAccent(schedule));
        shell.addView(accent, new LinearLayout.LayoutParams(dp(4), -1));

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(14), dp(13), dp(14), dp(12));
        String source = schedule.optString("source", "local");
        String sourceLabel = "synced".equals(source) ? tr("Đã đồng bộ", "Synced") : ("google".equals(source) ? "Google" : "FlowMate");
        LinearLayout heading = rowWrap();
        TextView title = label(schedule.optString("title", tr("Lịch hẹn", "Appointment")), 17, Typeface.BOLD, TEXT);
        heading.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        heading.addView(modeBadge(sourceLabel, "synced".equals(source) ? SUCCESS : ACCENT));
        card.addView(heading);
        card.addView(label(formatEventTime(schedule), 14, Typeface.BOLD, eventAccent(schedule)));
        String location = schedule.optString("location", "").trim();
        if (!location.isEmpty()) {
            TextView locationView = label(tr("Địa điểm: ", "Location: ") + location, 13, Typeface.NORMAL, MUTED);
            locationView.setPadding(0, dp(5), 0, 0);
            card.addView(locationView);
        }
        String formattedDescription = formatCalendarDescription(schedule.optString("description", ""));
        if (!formattedDescription.isEmpty()) {
            TextView description = label(formattedDescription, 13, Typeface.NORMAL, MUTED);
            description.setPadding(0, dp(7), 0, 0);
            description.setLineSpacing(dp(2), 1.05f);
            description.setMaxLines(6);
            description.setEllipsize(TextUtils.TruncateAt.END);
            card.addView(description);
        }
        LinearLayout actions = rowWrap();
        if (schedule.isNull("local_id")) {
            Button deleteGoogle = dangerButton(tr("Xóa khỏi Google", "Delete from Google"));
            deleteGoogle.setOnClickListener(v -> runApi(
                    () -> api.delete("/calendar/delete/" + schedule.optString("google_event_id")),
                    data -> {
                        toast(tr("Đã xóa sự kiện", "Event deleted"));
                        showScheduleList();
                    }));
            actions.addView(deleteGoogle);
            card.addView(horizontal(actions));
            shell.addView(card, new LinearLayout.LayoutParams(0, -2, 1));
            return shell;
        }
        int localId = schedule.optInt("local_id");
        Button done = secondaryButton(tr("Hoàn tất", "Complete"));
        done.setOnClickListener(v -> updateScheduleStatus(localId, "completed"));
        Button cancel = secondaryButton(tr("Hủy", "Cancel"));
        cancel.setOnClickListener(v -> updateScheduleStatus(localId, "cancelled"));
        Button delete = dangerButton(tr("Xóa", "Delete"));
        delete.setOnClickListener(v -> runApi(() -> api.delete("/schedule/" + localId), data -> {
            toast(tr("Đã xóa lịch", "Appointment deleted"));
            showScheduleList();
        }));
        actions.addView(done);
        actions.addView(cancel);
        actions.addView(delete);
        card.addView(horizontal(actions));
        shell.addView(card, new LinearLayout.LayoutParams(0, -2, 1));
        return shell;
    }

    private void updateScheduleStatus(int id, String status) {
        runApi(() -> {
            JSONObject payload = new JSONObject();
            payload.put("status", status);
            return api.post("/schedule/" + id + "/update-status", payload);
        }, data -> {
            toast(tr("Đã cập nhật lịch", "Appointment updated"));
            showScheduleList();
        });
    }

    private void showScheduleCreate() {
        showScheduleCreate(null);
    }

    private void showScheduleCreate(JSONObject meetingSuggestion) {
        setActiveTab("schedule");
        content.removeAllViews();
        content.addView(titleRow(tr("Tạo lịch", "Create event")));
        content.addView(scheduleNav());
        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);
        LinearLayout form = card();
        EditText title = input(tr("Họp phụ huynh", "Parent meeting"), false);
        EditText desc = input(tr("Mô tả", "Description"), true);
        EditText start = input("2026-06-05T09:00:00", false);
        EditText end = input("2026-06-05T10:00:00", false);
        EditText duration = input("60", false);
        duration.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        EditText location = input(tr("Địa điểm", "Location"), false);
        EditText attendees = input("email1@example.com, email2@example.com", false);
        if (meetingSuggestion != null) {
            title.setText(meetingSuggestion.optString(
                    "title",
                    meetingSuggestion.optString("subject", tr("Lịch hẹn từ email", "Appointment from email"))
            ));
            desc.setText(meetingSuggestion.optString(
                    "description",
                    meetingSuggestion.optString("snippet", "")
            ));
            start.setText(meetingSuggestion.optString("start_time", ""));
            end.setText(meetingSuggestion.optString("end_time", ""));
            location.setText(meetingSuggestion.optString("location", ""));
            attendees.setText(meetingSuggestion.optString("attendees", ""));
        }
        form.addView(fieldLabel(tr("Tiêu đề", "Title")));
        form.addView(title);
        form.addView(fieldLabel(tr("Mô tả", "Description")));
        form.addView(desc, new LinearLayout.LayoutParams(-1, dp(100)));
        form.addView(fieldLabel(tr("Bắt đầu", "Start")));
        form.addView(start);
        form.addView(fieldLabel(tr("Kết thúc", "End")));
        form.addView(end);
        form.addView(fieldLabel(tr("Thời lượng (phút)", "Duration (minutes)")));
        form.addView(duration);
        form.addView(fieldLabel(tr("Địa điểm", "Location")));
        form.addView(location);
        form.addView(fieldLabel(tr("Người tham dự", "Attendees")));
        form.addView(attendees);
        Button create = primaryButton(tr("Tạo lịch hẹn", "Create appointment"));
        create.setOnClickListener(v -> runApi(() -> {
            JSONObject payload = new JSONObject();
            payload.put("title", title.getText().toString().trim());
            payload.put("description", desc.getText().toString().trim());
            payload.put("start_time", start.getText().toString().trim());
            payload.put("end_time", end.getText().toString().trim());
            payload.put("duration_minutes", parseInt(duration.getText().toString(), 60));
            payload.put("location", location.getText().toString().trim());
            payload.put("attendees", attendeesArray(attendees.getText().toString()));
            return api.post("/schedule/create", payload);
        }, data -> {
            if (meetingSuggestion == null) {
                toast(tr("Đã tạo lịch", "Event created"));
                showScheduleList();
                return;
            }
            runApi(() -> {
                JSONObject status = new JSONObject();
                status.put("status", "created");
                status.put("schedule_id", data.optInt("schedule_id"));
                return api.patch(
                        "/email/meeting-suggestions/" + meetingSuggestion.optInt("id") + "/status",
                        status
                );
            }, ignored -> {
                toast(tr("Đã tạo lịch từ email", "Event created from email"));
                showScheduleList();
            });
        }));
        form.addView(create);
        body.addView(form);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    }

    private void showCalendarEvents() {
        showScheduleList();
    }

    private void showHistory() {
        setActiveTab("history");
        content.removeAllViews();
        LinearLayout top = titleRow(tr("Nhật ký", "Activity"));
        Button clear = secondaryButton(tr("Xóa hết", "Clear all"));
        clear.setOnClickListener(v -> runApi(() -> api.post("/chat/clear-all", new JSONObject()), data -> showHistory()));
        top.addView(clear);
        content.addView(top);
        ScrollView scroll = scrollWithBody();
        LinearLayout body = (LinearLayout) scroll.getChildAt(0);
        addMuted(body, tr("Đang tải lịch sử...", "Loading activity..."));
        content.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        runApi(() -> api.get("/chat/history?limit=50"), data -> {
            body.removeAllViews();
            JSONArray history = data.optJSONArray("history");
            if (history == null || history.length() == 0) {
                addMuted(body, tr("Chưa có hoạt động.", "No activity yet."));
                return;
            }
            body.addView(activitySummary(history));
            TextView heading = label(tr("HOẠT ĐỘNG GẦN ĐÂY", "RECENT ACTIVITY"), 12, Typeface.BOLD, MUTED);
            heading.setLetterSpacing(0.08f);
            heading.setPadding(0, dp(4), 0, dp(10));
            body.addView(heading);
            for (int i = 0; i < history.length(); i++) {
                JSONObject item = history.optJSONObject(i);
                if (item == null) continue;
                body.addView(activityTimelineItem(item));
            }
        });
    }

    private View scheduleOverview(JSONArray items, String selectedDate) {
        int count = items == null ? 0 : items.length();
        LinearLayout summary = card();
        summary.setBackground(round(Color.rgb(25, 32, 39), Color.rgb(38, 88, 78)));
        summary.addView(label(
                selectedDate.isEmpty() ? tr("TỔNG HỢP SỰ KIỆN", "EVENT OVERVIEW") : formatSelectedDate(selectedDate),
                11,
                Typeface.BOLD,
                SUCCESS
        ));
        summary.addView(label(
                count + tr(" sự kiện trong chế độ xem này", " events in this view"),
                21,
                Typeface.BOLD,
                TEXT
        ));
        summary.addView(label(
                selectedDate.isEmpty()
                        ? tr("Chọn một ngày trên lịch để xem lịch trình chi tiết.", "Select a date to view its detailed schedule.")
                        : tr("Chạm lại ngày đang chọn để quay về tổng hợp.", "Tap the selected date again to return to the overview."),
                13,
                Typeface.NORMAL,
                MUTED
        ));
        return summary;
    }

    private void addMiniCalendar(LinearLayout parent, JSONArray schedules, DateSelectionListener listener) {
        Calendar now = Calendar.getInstance();
        int year = now.get(Calendar.YEAR);
        int month = now.get(Calendar.MONTH);
        int today = now.get(Calendar.DAY_OF_MONTH);
        Set<String> eventDates = eventDates(schedules);

        LinearLayout card = card();
        card.setPadding(dp(12), dp(14), dp(12), dp(14));
        String monthName = now.getDisplayName(Calendar.MONTH, Calendar.LONG, Locale.US);
        LinearLayout calendarHeader = rowWrap();
        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        titleBlock.addView(label(monthName + " " + year, 19, Typeface.BOLD, TEXT));
        titleBlock.addView(label(tr("Chạm vào một ngày để lọc sự kiện", "Tap a date to filter events"), 12, Typeface.NORMAL, MUTED));
        calendarHeader.addView(titleBlock, new LinearLayout.LayoutParams(0, -2, 1));
        calendarHeader.addView(chip(tr("Có sự kiện", "Has events"), SUCCESS));
        card.addView(calendarHeader);

        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(7);
        String[] weekdays = {"S", "M", "T", "W", "T", "F", "S"};
        for (String weekday : weekdays) {
            TextView label = label(weekday, 10, Typeface.BOLD, TEXT_DIM);
            label.setGravity(Gravity.CENTER);
            grid.addView(label, calendarCellParams());
        }

        Calendar first = Calendar.getInstance();
        first.set(year, month, 1);
        int leading = first.get(Calendar.DAY_OF_WEEK) - 1;
        int days = first.getActualMaximum(Calendar.DAY_OF_MONTH);
        for (int i = 0; i < leading; i++) {
            TextView empty = label("", 12, Typeface.NORMAL, TEXT_DIM);
            grid.addView(empty, calendarCellParams());
        }
        for (int day = 1; day <= days; day++) {
            boolean isToday = day == today;
            String dateKey = String.format(Locale.US, "%04d-%02d-%02d", year, month + 1, day);
            boolean hasEvent = eventDates.contains(dateKey);
            boolean isSelected = dateKey.equals(selectedScheduleDate);

            LinearLayout cell = new LinearLayout(this);
            cell.setOrientation(LinearLayout.VERTICAL);
            cell.setGravity(Gravity.CENTER);
            cell.setClickable(true);
            cell.setContentDescription(dateKey + (hasEvent ? tr(", có sự kiện", ", has events") : ""));
            if (isSelected) {
                cell.setBackground(round(PRIMARY, PRIMARY));
            } else if (isToday) {
                cell.setBackground(round(withAlpha(PRIMARY, 35), PRIMARY));
            }

            View dot = new View(this);
            GradientDrawable dotShape = new GradientDrawable();
            dotShape.setShape(GradientDrawable.OVAL);
            dotShape.setColor(hasEvent ? (isSelected ? Color.WHITE : SUCCESS) : Color.TRANSPARENT);
            dot.setBackground(dotShape);
            LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(dp(5), dp(5));
            dotParams.setMargins(0, dp(3), 0, dp(2));
            cell.addView(dot, dotParams);

            TextView dayLabel = label(
                    String.valueOf(day),
                    12,
                    isToday || isSelected ? Typeface.BOLD : Typeface.NORMAL,
                    isSelected ? Color.WHITE : (isToday ? PRIMARY : MUTED)
            );
            dayLabel.setGravity(Gravity.CENTER);
            cell.addView(dayLabel, new LinearLayout.LayoutParams(-1, dp(27)));
            cell.setOnClickListener(v -> listener.onDateSelected(dateKey));
            grid.addView(cell, calendarCellParams());
        }
        card.addView(grid);
        parent.addView(card);
    }

    private GridLayout.LayoutParams calendarCellParams() {
        GridLayout.LayoutParams params = new GridLayout.LayoutParams();
        params.width = 0;
        params.height = dp(46);
        params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
        params.setMargins(dp(1), dp(1), dp(1), dp(1));
        return params;
    }

    private Set<String> eventDates(JSONArray schedules) {
        Set<String> dates = new HashSet<>();
        if (schedules == null) return dates;
        for (int i = 0; i < schedules.length(); i++) {
            JSONObject schedule = schedules.optJSONObject(i);
            if (schedule == null) continue;
            String dateKey = eventDateKey(schedule.optString("start_time", ""));
            if (!dateKey.isEmpty()) dates.add(dateKey);
        }
        return dates;
    }

    private int countEventDays(JSONArray schedules) {
        return eventDates(schedules).size();
    }

    private JSONArray schedulesForDate(JSONArray schedules, String dateKey) {
        if (dateKey == null || dateKey.isEmpty()) return schedules;
        JSONArray filtered = new JSONArray();
        for (int i = 0; i < schedules.length(); i++) {
            JSONObject schedule = schedules.optJSONObject(i);
            if (schedule != null && dateKey.equals(eventDateKey(schedule.optString("start_time", "")))) {
                filtered.put(schedule);
            }
        }
        return filtered;
    }

    private String eventDateKey(String value) {
        String text = value == null ? "" : value.trim();
        if (text.length() >= 10
                && Character.isDigit(text.charAt(0))
                && Character.isDigit(text.charAt(1))
                && Character.isDigit(text.charAt(2))
                && Character.isDigit(text.charAt(3))
                && text.charAt(4) == '-'
                && text.charAt(7) == '-') {
            return text.substring(0, 10);
        }
        return "";
    }

    private String formatEventTime(JSONObject schedule) {
        String start = schedule.optString("start_time", "");
        String end = schedule.optString("end_time", "");
        String date = eventDateKey(start);
        String startTime = isoTime(start);
        String endTime = isoTime(end);
        if (date.isEmpty()) return tr("Chưa có thời gian", "Time not specified");
        String dateLabel = formatSelectedDate(date);
        if (startTime.isEmpty()) return dateLabel + "  |  " + tr("Cả ngày", "All day");
        if (endTime.isEmpty()) return dateLabel + "  |  " + startTime;
        return dateLabel + "  |  " + startTime + " - " + endTime;
    }

    private String formatCalendarDescription(String raw) {
        if (raw == null || raw.trim().isEmpty()) return "";

        String decoded = raw.trim();
        for (int i = 0; i < 2; i++) {
            CharSequence parsed = Build.VERSION.SDK_INT >= Build.VERSION_CODES.N
                    ? Html.fromHtml(decoded, Html.FROM_HTML_MODE_LEGACY)
                    : Html.fromHtml(decoded);
            String next = parsed.toString();
            if (next.equals(decoded)) break;
            decoded = next;
        }

        decoded = decoded
                .replace('\u00a0', ' ')
                .replaceAll("[ \\t]+\\n", "\n")
                .replaceAll("\\n[ \\t]+", "\n")
                .replaceAll("[ \\t]{2,}", " ")
                .replaceAll("\\n{3,}", "\n\n")
                .trim();

        return decoded;
    }

    private String isoTime(String value) {
        String text = value == null ? "" : value.trim();
        int separator = text.indexOf('T');
        if (separator < 0 || text.length() < separator + 6) return "";
        return text.substring(separator + 1, separator + 6);
    }

    private String formatSelectedDate(String dateKey) {
        String[] parts = dateKey == null ? new String[0] : dateKey.split("-");
        if (parts.length != 3) return dateKey == null ? "" : dateKey;
        return tr("Ngày ", "") + parts[2] + "/" + parts[1] + "/" + parts[0];
    }

    private int eventAccent(JSONObject schedule) {
        String source = schedule.optString("source", "local");
        if ("google".equals(source)) return INFO;
        if ("synced".equals(source)) return SUCCESS;
        return ACCENT;
    }

    private interface DateSelectionListener {
        void onDateSelected(String dateKey);
    }

    private View activitySummary(JSONArray history) {
        int email = 0;
        int calendar = 0;
        int ai = 0;
        for (int i = 0; i < history.length(); i++) {
            JSONObject item = history.optJSONObject(i);
            if (item == null) continue;
            String type = item.optString("action_type", "").toLowerCase(Locale.US);
            if (type.contains("email")) email++;
            else if (type.contains("schedule") || type.contains("calendar")) calendar++;
            else ai++;
        }

        LinearLayout summary = card();
        summary.setBackground(round(Color.rgb(23, 37, 36), Color.rgb(38, 88, 78)));
        summary.addView(label(tr("NHẬT KÝ HOẠT ĐỘNG AI", "AI ACTIVITY LOG"), 11, Typeface.BOLD, SUCCESS));
        summary.addView(label(history.length() + tr(" hoạt động đã ghi nhận", " actions recorded"), 23, Typeface.BOLD, TEXT));
        LinearLayout stats = rowWrap();
        stats.addView(statPill(String.valueOf(email), "email"));
        stats.addView(statPill(String.valueOf(calendar), "calendar"));
        stats.addView(statPill(String.valueOf(ai), "assistant"));
        summary.addView(horizontal(stats));
        return summary;
    }

    private View activityTimelineItem(JSONObject item) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.TOP);
        row.setPadding(0, 0, 0, dp(10));

        String type = item.optString("action_type", "activity");
        int color = type.contains("email") ? INFO
                : (type.contains("calendar") || type.contains("schedule")) ? SUCCESS
                : ACCENT;
        TextView dot = label(type.substring(0, Math.min(1, type.length())).toUpperCase(Locale.US), 11, Typeface.BOLD, color);
        dot.setGravity(Gravity.CENTER);
        dot.setBackground(round(PANEL_RAISED, color));
        row.addView(dot, new LinearLayout.LayoutParams(dp(34), dp(34)));

        LinearLayout detail = new LinearLayout(this);
        detail.setOrientation(LinearLayout.VERTICAL);
        detail.setPadding(dp(12), 0, 0, 0);
        detail.addView(label(friendlyAction(type), 15, Typeface.BOLD, TEXT));
        String message = item.optString("user_message", item.optString("assistant_response", ""));
        TextView description = label(message, 13, Typeface.NORMAL, MUTED);
        description.setMaxLines(4);
        description.setEllipsize(TextUtils.TruncateAt.END);
        detail.addView(description);
        detail.addView(label(item.optString("created_at", ""), 11, Typeface.NORMAL, TEXT_DIM));
        row.addView(detail, new LinearLayout.LayoutParams(0, -2, 1));
        return row;
    }

    private String friendlyAction(String type) {
        return type.replace('_', ' ').trim();
    }

    private LinearLayout emailNav() {
        LinearLayout nav = navRow();
        nav.addView(navButton(tr("Hộp thư", "Inbox"), this::showEmailInbox));
        nav.addView(navButton(tr("Báo cáo", "Report"), this::showEmailReport));
        nav.addView(navButton(tr("Viết thư", "Compose"), this::showEmailCompose));
        return nav;
    }

    private LinearLayout scheduleNav() {
        LinearLayout nav = navRow();
        nav.addView(navButton(tr("Lịch tổng hợp", "Calendar overview"), this::showScheduleList));
        nav.addView(navButton(tr("Tạo lịch", "Create event"), this::showScheduleCreate));
        return nav;
    }

    private LinearLayout navRow() {
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        LinearLayout row = rowWrap();
        row.setPadding(dp(12), dp(2), dp(12), dp(8));
        scroll.addView(row);
        LinearLayout wrapper = new LinearLayout(this);
        wrapper.addView(scroll);
        return wrapper;
    }

    private HorizontalScrollView horizontal(View child) {
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(child);
        return scroll;
    }

    private Button navButton(String text, Runnable action) {
        Button button = secondaryButton(text);
        button.setOnClickListener(v -> action.run());
        return button;
    }

    private LinearLayout titleRow(String title) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(dp(18), dp(13), dp(14), dp(13));

        GradientDrawable heroBackground = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{Color.rgb(47, 40, 88), Color.rgb(25, 24, 40)}
        );
        heroBackground.setCornerRadius(dp(18));
        heroBackground.setStroke(dp(1), Color.rgb(83, 72, 146));
        row.setBackground(heroBackground);
        row.setElevation(dp(5));

        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        TextView eyebrow = label("FLOWMATE", 10, Typeface.BOLD, ACCENT);
        eyebrow.setLetterSpacing(0.12f);
        TextView titleView = label(title, 22, Typeface.BOLD, Color.WHITE);
        titleView.setPadding(0, dp(2), 0, 0);
        titleBlock.addView(eyebrow);
        titleBlock.addView(titleView);
        row.addView(titleBlock, new LinearLayout.LayoutParams(0, -2, 1));

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(dp(14), dp(12), dp(14), dp(4));
        row.setLayoutParams(params);
        return row;
    }

    private ScrollView scrollWithBody() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(16), dp(10), dp(16), dp(20));
        scroll.addView(body);
        return scroll;
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(15), dp(16), dp(15));
        card.setBackground(round(PANEL, BORDER));
        card.setElevation(dp(2));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(0, 0, 0, dp(14));
        card.setLayoutParams(params);
        return card;
    }

    private TextView modeBadge(String text, int color) {
        TextView badge = chip(text, color);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(32));
        params.setMargins(0, 0, 0, dp(12));
        badge.setLayoutParams(params);
        return badge;
    }

    private TextView chip(String text, int color) {
        TextView chip = label(text, 11, Typeface.BOLD, color);
        chip.setGravity(Gravity.CENTER);
        chip.setSingleLine(true);
        chip.setPadding(dp(10), 0, dp(10), 0);
        chip.setBackground(round(withAlpha(color, 34), withAlpha(color, 110)));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(28));
        params.setMargins(0, 0, dp(7), 0);
        chip.setLayoutParams(params);
        return chip;
    }

    private TextView statPill(String value, String label) {
        TextView stat = label(value + "  " + label, 11, Typeface.BOLD, TEXT);
        stat.setGravity(Gravity.CENTER);
        stat.setSingleLine(true);
        stat.setPadding(dp(10), 0, dp(10), 0);
        stat.setBackground(round(PANEL_RAISED, BORDER));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(32));
        params.setMargins(0, 0, dp(7), 0);
        stat.setLayoutParams(params);
        return stat;
    }

    private int withAlpha(int color, int alpha) {
        return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
    }

    private TextView label(String text, int sp, int style, int color) {
        TextView view = new TextView(this);
        view.setText(text == null ? "" : text);
        view.setTextSize(sp);
        view.setTypeface(Typeface.DEFAULT, style);
        view.setTextColor(color);
        view.setLineSpacing(dp(2), 1.0f);
        return view;
    }

    private TextView fieldLabel(String text) {
        TextView view = label(text, 13, Typeface.BOLD, MUTED);
        view.setPadding(0, dp(10), 0, dp(5));
        return view;
    }

    private EditText input(String hint, boolean multiline) {
        EditText editText = new EditText(this);
        editText.setHint(hint);
        editText.setTextColor(TEXT);
        editText.setHintTextColor(Color.rgb(154, 168, 188));
        editText.setTextSize(15);
        editText.setSingleLine(!multiline);
        editText.setMinLines(multiline ? 3 : 1);
        editText.setMinHeight(multiline ? dp(104) : dp(52));
        editText.setImeOptions(multiline ? EditorInfo.IME_FLAG_NO_EXTRACT_UI : EditorInfo.IME_ACTION_DONE);
        editText.setPadding(dp(14), multiline ? dp(10) : 0, dp(14), multiline ? dp(10) : 0);
        editText.setBackground(round(PANEL_RAISED, BORDER));
        return editText;
    }

    private Button primaryButton(String text) {
        return styledButton(text, PRIMARY, Color.WHITE);
    }

    private Button secondaryButton(String text) {
        return styledButton(text, PANEL_RAISED, TEXT);
    }

    private Button dangerButton(String text) {
        return styledButton(text, DANGER, Color.WHITE);
    }

    private Button styledButton(String text, int background, int color) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(color);
        button.setTextSize(13);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setAllCaps(false);
        button.setMinHeight(dp(46));
        button.setMinWidth(dp(48));
        button.setPadding(dp(14), 0, dp(14), 0);
        int stroke = background == PANEL_RAISED ? BORDER : background;
        button.setBackground(round(background, stroke));
        button.setElevation(background == PRIMARY || background == DANGER ? dp(3) : 0);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(46));
        params.setMargins(0, 0, dp(8), 0);
        button.setLayoutParams(params);
        return button;
    }

    private LinearLayout rowWrap() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, dp(8), 0, dp(8));
        return row;
    }

    private LinearLayout.LayoutParams weightParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        params.setMargins(dp(3), 0, dp(3), 0);
        return params;
    }

    private View fab(Runnable action) {
        TextView fab = label("+", 26, Typeface.BOLD, Color.WHITE);
        fab.setGravity(Gravity.CENTER);
        GradientDrawable circle = new GradientDrawable();
        circle.setShape(GradientDrawable.OVAL);
        circle.setColor(PRIMARY);
        fab.setBackground(circle);
        fab.setElevation(dp(6));
        fab.setClickable(true);
        fab.setContentDescription(tr("Tạo lịch mới", "Create new event"));
        fab.setOnClickListener(v -> action.run());
        return fab;
    }

    private FrameLayout.LayoutParams fabParams() {
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(dp(56), dp(56));
        params.gravity = Gravity.BOTTOM | Gravity.END;
        params.setMargins(0, 0, dp(20), dp(20));
        return params;
    }

    private GradientDrawable round(int fill, int stroke) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(14));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private void addMuted(LinearLayout parent, String text) {
        TextView view = label(text, 14, Typeface.NORMAL, MUTED);
        view.setGravity(Gravity.CENTER);
        view.setPadding(dp(14), dp(20), dp(14), dp(20));
        parent.addView(view, new LinearLayout.LayoutParams(-1, -2));
    }

    private void runApi(ApiTask task, ApiSuccess success) {
        new Thread(() -> {
            try {
                JSONObject data = task.run();
                runOnUiThread(() -> success.onSuccess(data));
            } catch (Exception error) {
                runOnUiThread(() -> {
                    String message = error.getMessage() == null ? "" : error.getMessage();
                    if ("not_authenticated".equalsIgnoreCase(message)) {
                        showGoogleReconnectDialog();
                    } else {
                        alert(tr("Lỗi", "Error"), message);
                    }
                });
            }
        }).start();
    }

    private void showGoogleReconnectDialog() {
        new AlertDialog.Builder(this)
                .setTitle("Google connection required")
                .setMessage("Your Google session has expired or was disconnected. Reconnect to use Gmail and Google Calendar.")
                .setNegativeButton("Later", null)
                .setPositiveButton("Reconnect", (dialog, which) -> {
                    clearLocalSession();
                    showLoginScreen();
                })
                .show();
    }

    private JSONArray attendeesArray(String raw) {
        JSONArray array = new JSONArray();
        if (raw == null || raw.trim().isEmpty()) return array;
        String[] pieces = raw.split(",");
        for (String piece : pieces) {
            String value = piece.trim();
            if (!value.isEmpty()) array.put(value);
        }
        return array;
    }

    private String reportDateToStart(String reportDate) {
        String[] parts = reportDate == null ? new String[0] : reportDate.split("/");
        if (parts.length != 3) {
            return new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
                    .format(new java.util.Date()) + "T09:00:00";
        }
        return parts[2] + "-" + parts[1] + "-" + parts[0] + "T09:00:00";
    }

    private int parseInt(String value, int fallback) {
        try {
            return Integer.parseInt(value.trim());
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private void alert(String title, String message) {
        new AlertDialog.Builder(this)
                .setTitle(title)
                .setMessage(message == null || message.isEmpty()
                        ? tr("Không có thông tin chi tiết.", "No details available.")
                        : message)
                .setPositiveButton("OK", null)
                .show();
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    @Override
    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == RC_SIGN_IN) {
            Task<GoogleSignInAccount> task = GoogleSignIn.getSignedInAccountFromIntent(data);
            handleSignInResult(task);
        }
    }

    private void handleSignInResult(Task<GoogleSignInAccount> completedTask) {
        try {
            GoogleSignInAccount account = completedTask.getResult(ApiException.class);
            String authCode = account.getServerAuthCode();
            String email = account.getEmail();

            if (authCode == null || authCode.trim().isEmpty() || email == null || email.trim().isEmpty()) {
                alert("Sign in failed", "Google did not return the account information required by FlowMate AI.");
                return;
            }
            runApi(() -> {
                JSONObject payload = new JSONObject();
                payload.put("server_auth_code", authCode);
                payload.put("email", email);
                return api.post("/email/google-auth", payload);
            }, data -> {
                String signedInEmail = data.optString("email", email).trim();
                String accessToken = data.optString("access_token", "").trim();
                if (accessToken.isEmpty()) {
                    throw new IllegalStateException("Backend did not return a mobile access token");
                }
                api.setAccessToken(accessToken);
                selectedRole = "";
                prefs.edit()
                        .putString("userId", signedInEmail)
                        .putString("accessToken", accessToken)
                        .putBoolean("googleAuthenticated", true)
                        .remove("role")
                        .apply();
                updateSubtitle();
                toast("Google account connected");
                showRoleSelection();
            });
        } catch (ApiException e) {
            if (e.getStatusCode() == 10) {
                alert(
                        "Google login is not configured",
                        "Verify this Android OAuth client in Google Cloud:\n" +
                        getString(R.string.google_android_client_id) + "\n\n" +
                        "Package name:\ncom.exe101.teacherbot\n\n" +
                        "Debug SHA-1:\n69:8C:F1:A4:A6:5D:38:A9:D6:54:4C:39:DE:8B:AE:87:B0:8E:93:20\n\n" +
                        "Then wait a few minutes, uninstall FlowMate AI, and run it again from Android Studio."
                );
            } else {
                alert("Sign in failed", "Google error code: " + e.getStatusCode());
            }
        }
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private interface ApiTask {
        JSONObject run() throws Exception;
    }

    private interface ApiSuccess {
        void onSuccess(JSONObject data);
    }
}
