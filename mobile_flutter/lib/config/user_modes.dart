import 'package:flutter/material.dart';

class UserMode {
  final String value;
  final IconData icon;
  final String label;
  final String shortLabel;
  final String description;
  final List<String> prompts;

  const UserMode({
    required this.value,
    required this.icon,
    required this.label,
    required this.shortLabel,
    required this.description,
    required this.prompts,
  });
}

const List<UserMode> kUserModes = [
  UserMode(
    value: 'student',
    icon: Icons.school_outlined,
    label: 'Sinh viên',
    shortLabel: 'Học tập',
    description: 'Môn học, bài tập, deadline, email lớp, lịch thi và kế hoạch ôn tập.',
    prompts: ['Tóm tắt deadline học tập hôm nay', 'Lập kế hoạch ôn tập trong tuần'],
  ),
  UserMode(
    value: 'worker',
    icon: Icons.work_outline,
    label: 'Nhân viên văn phòng',
    shortLabel: 'Công việc',
    description: 'Họp, báo cáo, email công việc và việc cần theo dõi.',
    prompts: ['Email nào cần phản hồi?', 'Tóm tắt công việc hôm nay'],
  ),
  UserMode(
    value: 'freelancer',
    icon: Icons.laptop_mac_outlined,
    label: 'Freelancer',
    shortLabel: 'Dự án',
    description: 'Khách hàng, dự án, hóa đơn và lịch bàn giao.',
    prompts: ['Dự án nào sắp đến hạn?', 'Soạn phản hồi cho khách hàng'],
  ),
  UserMode(
    value: 'mentor',
    icon: Icons.people_outline,
    label: 'Mentor',
    shortLabel: 'Giảng dạy',
    description: 'Học viên, lịch hướng dẫn, phản hồi và theo dõi tiến độ.',
    prompts: ['Tóm tắt email học viên', 'Lịch hướng dẫn tiếp theo'],
  ),
  UserMode(
    value: 'teacher',
    icon: Icons.menu_book_outlined,
    label: 'Giáo viên',
    shortLabel: 'Lớp học',
    description: 'Lớp học, giáo án, học sinh, chấm bài và lịch giảng dạy.',
    prompts: ['Tóm tắt email lớp học', 'Deadline chấm bài nào gần nhất?'],
  ),
  UserMode(
    value: 'business',
    icon: Icons.trending_up_outlined,
    label: 'Kinh doanh',
    shortLabel: 'Vận hành',
    description: 'Vận hành, quyết định, đội nhóm và rủi ro.',
    prompts: ['Vấn đề nào cần quyết định?', 'Tóm tắt email quan trọng'],
  ),
  UserMode(
    value: 'creator',
    icon: Icons.palette_outlined,
    label: 'Nhà sáng tạo',
    shortLabel: 'Nội dung',
    description: 'Thương hiệu, chiến dịch và lịch nội dung.',
    prompts: ['Lập lịch nội dung tuần này', 'Email hợp tác nào quan trọng?'],
  ),
];

UserMode getUserMode(String? value) {
  return kUserModes.firstWhere((m) => m.value == value, orElse: () => kUserModes[1]);
}
