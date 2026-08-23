export const USER_MODES = [
  {
    value: 'student',
    icon: 'school-outline',
    label: 'Sinh viên',
    shortLabel: 'Học tập',
    description: 'Môn học, bài tập, deadline, email lớp, lịch thi và kế hoạch ôn tập.',
    prompts: ['Tóm tắt deadline học tập hôm nay', 'Lập kế hoạch ôn tập trong tuần'],
  },
  {
    value: 'worker',
    icon: 'briefcase-outline',
    label: 'Nhân viên văn phòng',
    shortLabel: 'Công việc',
    description: 'Họp, báo cáo, email công việc và việc cần theo dõi.',
    prompts: ['Email nào cần phản hồi?', 'Tóm tắt công việc hôm nay'],
  },
  {
    value: 'freelancer',
    icon: 'laptop-outline',
    label: 'Freelancer',
    shortLabel: 'Dự án',
    description: 'Khách hàng, dự án, hóa đơn và lịch bàn giao.',
    prompts: ['Dự án nào sắp đến hạn?', 'Soạn phản hồi cho khách hàng'],
  },
  {
    value: 'mentor',
    icon: 'people-outline',
    label: 'Mentor',
    shortLabel: 'Giảng dạy',
    description: 'Học viên, lịch hướng dẫn, phản hồi và theo dõi tiến độ.',
    prompts: ['Tóm tắt email học viên', 'Lịch hướng dẫn tiếp theo'],
  },
  {
    value: 'teacher',
    icon: 'easel-outline',
    label: 'Giáo viên',
    shortLabel: 'Lớp học',
    description: 'Lớp học, giáo án, học sinh, chấm bài và lịch giảng dạy.',
    prompts: ['Tóm tắt email lớp học', 'Deadline chấm bài nào gần nhất?'],
  },
  {
    value: 'business',
    icon: 'trending-up-outline',
    label: 'Kinh doanh',
    shortLabel: 'Vận hành',
    description: 'Vận hành, quyết định, đội nhóm và rủi ro.',
    prompts: ['Vấn đề nào cần quyết định?', 'Tóm tắt email quan trọng'],
  },
  {
    value: 'creator',
    icon: 'color-palette-outline',
    label: 'Nhà sáng tạo',
    shortLabel: 'Nội dung',
    description: 'Thương hiệu, chiến dịch và lịch nội dung.',
    prompts: ['Lập lịch nội dung tuần này', 'Email hợp tác nào quan trọng?'],
  },
];

export function getUserMode(value) {
  return USER_MODES.find((item) => item.value === value) || USER_MODES[1];
}
