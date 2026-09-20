# Thiết kế tóm tắt email ngắn và chính xác

## Mục tiêu sản phẩm

- Người dùng hiểu ý chính của email trong khoảng 5 giây.
- Dùng hai lớp: danh sách chỉ hiện `TÓM TẮT`; màn chi tiết giữ `ĐIỂM CHÍNH`, `CẦN LÀM`, `THỜI HẠN` và `TÀI LIỆU` khi có.
- Không thêm tên, số tiền, mã, ngày giờ hoặc quyết định không có trong email.
- Không bỏ tên file đính kèm hoặc liên kết tài liệu được nêu rõ trong email; file gốc vẫn tải được từ màn chi tiết.
- Độ phủ dữ kiện quan trọng trên bộ benchmark phải từ 90% trở lên.
- Lớp `TÓM TẮT` không quá 220 ký tự; các lớp chi tiết có thể dài hơn để không làm mất ý.

## Pipeline

1. Chuyển HTML thành văn bản và loại footer, chữ ký, liên kết huỷ đăng ký.
2. Tách phần trả lời mới khỏi lịch sử email được trích dẫn.
3. Chấm điểm câu dựa trên tiêu đề, vị trí, từ chỉ hành động, ngày giờ và số liệu.
4. Chọn tối đa hai câu cho ý chính; phân loại riêng hành động và thời hạn.
5. Giữ thêm tối đa bốn điểm khác biệt chưa xuất hiện ở các phần trên để tránh mất quyết định, số liệu hoặc rủi ro.
6. Liệt kê toàn bộ tên file đính kèm và URL tài liệu nguồn; không giả định nội dung file nếu chưa đọc file.
7. Chỉ rút ngắn tại biên từ hoặc mệnh đề; không diễn giải lại dữ kiện.
8. Hiển thị nhãn “Trích từ nội dung email” trên mobile để giải thích nguồn của tóm tắt.

## Định nghĩa “độ chính xác >90%”

Chỉ số được dùng là tỷ lệ ca kiểm thử đồng thời thỏa mãn:

- chứa toàn bộ dữ kiện bắt buộc đã gắn nhãn;
- không chứa dữ kiện cấm từ thread cũ, footer hoặc chữ ký;
- mọi evidence động là đoạn trích từ email nguồn;
- lớp ý chính nằm trong giới hạn độ dài và lớp chi tiết giữ đủ dữ kiện đã gắn nhãn.

Benchmark hiện có 20 tình huống Việt/Anh gồm lịch họp, OTP, hóa đơn, hợp đồng,
ticket hỗ trợ, quyết định dự án và chuỗi thư. Ngưỡng CI là 90%; kết quả hiện tại
là 20/20. Con số này là kết quả trên benchmark, không phải cam kết tuyệt đối cho
mọi email ngoài thực tế.

## Theo dõi sau phát hành

- Bổ sung email ẩn danh/giả lập vào benchmark khi phát hiện kiểu nội dung mới.
- Không lưu nội dung email thật vào bộ test hoặc telemetry.
- Theo dõi riêng ba lỗi: thiếu dữ kiện, lấy nhầm nội dung thread cũ và đầu ra quá dài.
- Không phát hành thay đổi thuật toán nếu benchmark dưới 90%.
