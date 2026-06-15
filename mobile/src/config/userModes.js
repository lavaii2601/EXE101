export const USER_MODES = [
  {
    value: 'student',
    icon: 'ST',
    label: 'Sinh vien',
    shortLabel: 'Hoc tap',
    description: 'Bai tap, deadline, email lop va lich hoc.',
    prompts: ['Tom tat email lop hom nay', 'Lap ke hoach hoc trong tuan'],
  },
  {
    value: 'worker',
    icon: 'VP',
    label: 'Nhan vien van phong',
    shortLabel: 'Cong viec',
    description: 'Hop, bao cao, email cong viec va viec can theo doi.',
    prompts: ['Email nao can phan hoi?', 'Tom tat cong viec hom nay'],
  },
  {
    value: 'freelancer',
    icon: 'FR',
    label: 'Freelancer',
    shortLabel: 'Du an',
    description: 'Khach hang, du an, hoa don va lich ban giao.',
    prompts: ['Du an nao sap den han?', 'Soan phan hoi cho khach hang'],
  },
  {
    value: 'mentor',
    icon: 'MT',
    label: 'Mentor / Giao vien',
    shortLabel: 'Giang day',
    description: 'Hoc vien, lich huong dan va han phan hoi.',
    prompts: ['Tom tat email hoc vien', 'Lich huong dan tiep theo'],
  },
  {
    value: 'business',
    icon: 'KD',
    label: 'Kinh doanh',
    shortLabel: 'Van hanh',
    description: 'Van hanh, quyet dinh, doi nhom va rui ro.',
    prompts: ['Van de nao can quyet dinh?', 'Tom tat email quan trong'],
  },
  {
    value: 'creator',
    icon: 'CR',
    label: 'Nha sang tao',
    shortLabel: 'Noi dung',
    description: 'Thuong hieu, chien dich va lich noi dung.',
    prompts: ['Lap lich noi dung tuan nay', 'Email hop tac nao quan trong?'],
  },
];

export function getUserMode(value) {
  return USER_MODES.find((item) => item.value === value) || USER_MODES[1];
}
