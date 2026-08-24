import 'package:flutter/material.dart';

/// Central registry of every icon the app uses, keyed by what it *means*
/// rather than which screen uses it. When custom-designed icons are ready,
/// swap the [IconData] value on the matching field here -- nothing in the
/// screens needs to change, since they all reference `AppIcons.xxx` instead
/// of raw `Icons.xxx`.
///
/// Grouped by feature area; add new fields to the matching group (or a new
/// one) rather than inlining `Icons.*` in a screen file.
class AppIcons {
  AppIcons._();

  // Email
  static const IconData emailCompose = Icons.edit_outlined;
  static const IconData emailSearch = Icons.search;
  static const IconData emailSearchClear = Icons.close;
  static const IconData emailFilter = Icons.tune_outlined;
  static const IconData emailConnect = Icons.link;
  static const IconData emailInbox = Icons.inbox_outlined;
  static const IconData emailLocked = Icons.mail_lock_outlined;
  static const IconData emailMeeting = Icons.event_outlined;
  static const IconData emailSend = Icons.send_outlined;

  // Overview
  static const IconData overviewDeadline = Icons.flag_outlined;
  static const IconData overviewChecklist = Icons.check;
  static const IconData overviewMail = Icons.mail_outline;

  // Schedule
  static const IconData scheduleEmpty = Icons.event_busy_outlined;

  // History
  static const IconData historyAudit = Icons.shield_outlined;
  static const IconData historyDefault = Icons.circle_outlined;

  // Settings
  static const IconData settingsAccount = Icons.person_outline;
  static const IconData settingsThemeDark = Icons.dark_mode;
  static const IconData settingsThemeLight = Icons.light_mode;
  static const IconData settingsGmail = Icons.mail_outline;
  static const IconData settingsAbout = Icons.info_outline;

  // Navigation / shell
  static const IconData navOverview = Icons.dashboard_outlined;
  static const IconData navChat = Icons.chat_bubble_outline;
  static const IconData navEmail = Icons.mail_outline;
  static const IconData navSchedule = Icons.calendar_today_outlined;
  static const IconData navHistory = Icons.history;
  static const IconData navSettings = Icons.settings_outlined;
}
