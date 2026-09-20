import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'web' / 'backend'))

from services.extractive_summary import (  # noqa: E402
    clean_email_text,
    summarize_one_line,
    summarize_short,
    summarize_structured,
    summarize_structured_result,
)


QUALITY_CASES = [
    {
        'subject': 'Duyệt ngân sách Q4',
        'body': 'Ngân sách Q4 đã tăng lên 250 triệu đồng. Vui lòng xác nhận trước 17:00 ngày 25/09/2026.',
        'must': ('250 triệu đồng', '25/09/2026'),
    },
    {
        'subject': 'Product review',
        'body': 'The product review starts at 10:30 tomorrow. Please confirm attendance by 5 PM today.',
        'must': ('10:30', '5 PM today'),
    },
    {
        'subject': 'Nộp bài cuối kỳ',
        'body': 'Bản PDF cuối cùng cần được nộp trước thứ Sáu. Hãy đặt tên file theo mã sinh viên.',
        'must': ('trước thứ Sáu', 'mã sinh viên'),
    },
    {
        'subject': 'Mã xác thực',
        'body': 'Mã OTP của bạn là 482901 và có hiệu lực trong 10 phút. Không chia sẻ mã này.',
        'must': ('482901', '10 phút'),
    },
    {
        'subject': 'Invoice INV-2048',
        'body': 'Invoice INV-2048 has a total of $1,250. Payment is due on 30/09/2026.',
        'must': ('INV-2048', '$1,250', '30/09/2026'),
    },
    {
        'subject': 'Ứng viên Backend',
        'body': 'Ứng viên Nguyễn An đã vượt qua vòng kỹ thuật. Vui lòng gửi offer trước ngày 28/09.',
        'must': ('Nguyễn An', '28/09'),
    },
    {
        'subject': 'Sự cố thanh toán',
        'body': 'Thanh toán đơn DH-778 bị thất bại hai lần. Cần liên hệ khách hàng trong hôm nay.',
        'must': ('DH-778', 'trong hôm nay'),
    },
    {
        'subject': 'RSVP workshop',
        'body': 'The workshop is on Friday at 14:00. Kindly RSVP before Wednesday.',
        'must': ('Friday', '14:00', 'Wednesday'),
    },
    {
        'subject': 'Quyết định phương án',
        'body': 'Nhóm đã chọn phương án B vì chi phí thấp hơn 18%. Hãy cập nhật kế hoạch triển khai.',
        'must': ('phương án B', '18%'),
    },
    {
        'subject': 'Gia hạn hợp đồng',
        'body': 'Hợp đồng HD-09 sẽ hết hạn ngày 01/10/2026. Đề nghị bộ phận pháp chế rà soát phụ lục.',
        'must': ('HD-09', '01/10/2026'),
    },
    {
        'subject': 'Lịch phỏng vấn',
        'body': 'Phỏng vấn diễn ra lúc 9h30 ngày mai tại phòng A2. Vui lòng đến sớm 10 phút.',
        'must': ('9h30', 'phòng A2'),
    },
    {
        'subject': 'Course enrollment',
        'body': 'Your enrollment in Data Science 101 is confirmed. Classes begin on Monday.',
        'must': ('Data Science 101', 'Monday'),
    },
    {
        'subject': 'Giao hàng',
        'body': 'Đơn hàng FM-2026 đã được bàn giao cho đơn vị vận chuyển. Dự kiến giao ngày 23/09.',
        'must': ('FM-2026', '23/09'),
    },
    {
        'subject': 'Access request',
        'body': 'Mai needs read-only access to the analytics dashboard. Please approve request AR-55.',
        'must': ('Mai', 'AR-55'),
    },
    {
        'subject': 'Khiếu nại khách hàng',
        'body': 'Khách hàng báo sản phẩm bị thiếu phụ kiện. Cần phản hồi mã ticket CS-310 trong 4 giờ.',
        'must': ('CS-310', '4 giờ'),
    },
    {
        'subject': 'Release 2.4',
        'body': 'Release 2.4 is approved for production. The deployment window is 22:00 tonight.',
        'must': ('Release 2.4', '22:00'),
    },
    {
        'subject': 'Biên bản họp',
        'body': 'Cuộc họp thống nhất Lan phụ trách thiết kế. Minh sẽ gửi prototype vào thứ Ba.',
        'must': ('Lan', 'thứ Ba'),
    },
    {
        'subject': 'Security alert',
        'body': 'A new login was detected from Singapore at 08:15. Reset your password if this was not you.',
        'must': ('Singapore', '08:15'),
    },
    {
        'subject': 'Xác nhận nghỉ phép',
        'body': 'Đơn nghỉ phép của bạn từ 02/10 đến 04/10 đã được duyệt. Hãy bàn giao công việc cho Huy.',
        'must': ('02/10', '04/10', 'Huy'),
    },
    {
        'subject': 'Re: Kế hoạch cũ',
        'body': (
            'Mình đồng ý với phương án mới C. Hãy gửi bản cuối trước thứ Năm.\n'
            'On Monday Alex wrote:\n'
            'Phương án cũ A có deadline 01/01/2020.'
        ),
        'must': ('phương án mới C', 'thứ Năm'),
        'must_not': ('phương án cũ A', '01/01/2020'),
    },
]


class EmailSummaryQualityTests(unittest.TestCase):
    def test_benchmark_meets_ninety_percent_fact_coverage(self):
        passed = 0
        failures = []
        for case in QUALITY_CASES:
            summary = summarize_structured(case['subject'], case['body'])
            normalized = summary.casefold()
            includes = all(value.casefold() in normalized for value in case['must'])
            excludes = all(
                value.casefold() not in normalized
                for value in case.get('must_not', ())
            )
            concise = len(summary) <= 620
            if includes and excludes and concise:
                passed += 1
            else:
                failures.append((case['subject'], summary))

        accuracy = passed / len(QUALITY_CASES)
        self.assertGreaterEqual(accuracy, 0.90, failures)

    def test_every_selected_fact_is_source_backed(self):
        for case in QUALITY_CASES:
            result = summarize_structured_result(case['subject'], case['body'])
            source = re.sub(
                r'\s+',
                ' ',
                f"{case['subject']} {clean_email_text(case['body'])}",
            ).casefold()
            for evidence in result['evidence']:
                evidence_without_ellipsis = evidence.rstrip('…').casefold()
                self.assertIn(evidence_without_ellipsis, source, case['subject'])
            self.assertGreaterEqual(result['support_ratio'], 0.90)

    def test_output_is_layered_and_the_overview_stays_short(self):
        for case in QUALITY_CASES:
            summary = summarize_structured(case['subject'], case['body'])
            result = summarize_structured_result(case['subject'], case['body'])
            self.assertLessEqual(len(result['overview']), 260, case['subject'])
            self.assertLessEqual(len(summary), 1400, case['subject'])
            section_count = sum(
                heading in summary
                for heading in ('TÓM TẮT', 'ĐIỂM CHÍNH', 'CẦN LÀM', 'THỜI HẠN', 'TÀI LIỆU')
            )
            self.assertLessEqual(section_count, 5)

    def test_html_footer_and_signature_are_removed(self):
        body = (
            '<p>Dự án Atlas đã được duyệt.</p><p>Vui lòng triển khai ngày mai.</p>'
            '<br>Trân trọng,<br>Lan<br>Unsubscribe from this newsletter'
        )
        summary = summarize_structured('Dự án Atlas', body)
        self.assertIn('Atlas', summary)
        self.assertNotIn('Unsubscribe', summary)
        self.assertNotIn('Trân trọng', summary)

    def test_short_summaries_keep_critical_automated_email_values(self):
        otp = summarize_short(
            'Mã OTP',
            'Mã xác thực của bạn là 482901 và hết hạn sau 10 phút.',
        )
        invoice = summarize_one_line(
            'Invoice INV-2048',
            'Total due is $1,250 on 30/09/2026.',
            '',
        )
        self.assertIn('482901', otp)
        self.assertIn('10 phút', otp)
        self.assertIn('$1,250', invoice)
        self.assertIn('30/09/2026', invoice)

    def test_detailed_summary_keeps_distinct_ideas_files_and_links(self):
        body = (
            'Dự án Orion đã được duyệt để triển khai. '
            'Ngân sách chính thức là 300 triệu đồng. '
            'Lan là người phụ trách và Minh duyệt thiết kế. '
            'Rủi ro hiện tại là chậm bàn giao dữ liệu. '
            'Vui lòng gửi kế hoạch xử lý trước 16:00 ngày 30/09/2026. '
            'Tài liệu tham chiếu: https://docs.example.com/orion/spec-v3'
        )
        attachments = [
            {'filename': 'Orion-SOW-v3.pdf', 'mime_type': 'application/pdf'},
            {'filename': 'Budget-Q4.xlsx', 'mime_type': 'application/vnd.ms-excel'},
        ]
        summary = summarize_structured(
            'Khởi động dự án Orion',
            body,
            attachments=attachments,
        )

        for expected in (
            'Orion',
            '300 triệu đồng',
            'Lan',
            'Minh',
            'chậm bàn giao dữ liệu',
            '16:00',
            '30/09/2026',
            'Orion-SOW-v3.pdf',
            'Budget-Q4.xlsx',
            'https://docs.example.com/orion/spec-v3',
        ):
            self.assertIn(expected, summary)
        self.assertIn('ĐIỂM CHÍNH', summary)
        self.assertIn('TÀI LIỆU', summary)


if __name__ == '__main__':
    unittest.main()
