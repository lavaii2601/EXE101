export const USER_MODES = [
  {
    value: 'student',
    icon: 'ST',
    label: 'Sinh viên',
    shortLabel: 'Học tập',
    description: 'Bài tập, deadline, email lớp và lịch học.',
    prompts: ['Tóm tắt email lớp hôm nay', 'Lập kế hoạch học trong tuần'],
  },
  {
    value: 'worker',
    icon: 'VP',
    label: 'Nhân viên văn phòng',
    shortLabel: 'Công việc',
    description: 'Họp, báo cáo, email công việc và việc cần theo dõi.',
    prompts: ['Email nào cần phản hồi?', 'Tóm tắt công việc hôm nay'],
  },
  {
    value: 'freelancer',
    icon: 'FR',
    label: 'Freelancer',
    shortLabel: 'Dự án',
    description: 'Khách hàng, dự án, hóa đơn và lịch bàn giao.',
    prompts: ['Dự án nào sắp đến hạn?', 'Soạn phản hồi cho khách hàng'],
  },
  {
    value: 'mentor',
    icon: 'MT',
    label: 'Mentor / Giáo viên',
    shortLabel: 'Giảng dạy',
    description: 'Học viên, lịch hướng dẫn và hạn phản hồi.',
    prompts: ['Tóm tắt email học viên', 'Lịch hướng dẫn tiếp theo'],
  },
  {
    value: 'business',
    icon: 'KD',
    label: 'Kinh doanh',
    shortLabel: 'Vận hành',
    description: 'Vận hành, quyết định, đội nhóm và rủi ro.',
    prompts: ['Vấn đề nào cần quyết định?', 'Tóm tắt email quan trọng'],
  },
  {
    value: 'creator',
    icon: 'CR',
    label: 'Nhà sáng tạo',
    shortLabel: 'Nội dung',
    description: 'Thương hiệu, chiến dịch và lịch nội dung.',
    prompts: ['Lập lịch nội dung tuần này', 'Email hợp tác nào quan trọng?'],
  },
];

export function getUserMode(value) {
  return USER_MODES.find((item) => item.value === value) || USER_MODES[1];
}
