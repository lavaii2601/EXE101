# Thiết kế Worker Mode và Business Subscription

> Trạng thái: Bản thiết kế để review, chưa triển khai code hoặc migration.
> Phạm vi: FlowMate web, Expo/React Native, Flutter và Flask/PostgreSQL dùng chung.
> Cập nhật: 2026-08-27.

## 1. Mục tiêu và phạm vi

Tài liệu này thiết kế hai phần có liên quan chặt chẽ:

1. Worker Mode dành cho nhân viên văn phòng, gồm trải nghiệm cá nhân và các tính năng cộng tác trong doanh nghiệp.
2. Subscription theo ba cấp: Free cá nhân, Premium cá nhân và Business workspace.

Mục tiêu chính:

- Mỗi người luôn có không gian cá nhân và có thể tham gia nhiều workspace doanh nghiệp giống Slack hoặc Discord.
- Doanh nghiệp mời thành viên bằng email; người được mời phải đăng nhập bằng email đã xác minh và chủ động chấp nhận.
- Quyền hiệu lực được tính từ vai trò, workspace đang hoạt động và subscription sở hữu workspace đó.
- Dữ liệu email/lịch cá nhân mặc định riêng tư. Doanh nghiệp chỉ thấy dữ liệu người dùng chủ động chia sẻ.
- Gói Business gồm 10 chỗ; muốn có thành viên hoạt động thứ 11 phải mua thêm chỗ.
- Workspace hết hạn có 7 ngày gia hạn đầy đủ chức năng, sau đó chuyển sang chỉ đọc để bảo toàn dữ liệu.
- Thiết kế phải mở đường cho tích hợp thanh toán và email nhắc gia hạn trong tương lai mà không thay đổi cơ chế phân quyền cốt lõi.
- Web, Expo/React Native và Flutter là ba client chính thức, dùng chung API và cùng một mô hình quyền.

### 1.1 Ngoài phạm vi phiên bản đầu

- Không cho doanh nghiệp đọc toàn bộ Gmail hoặc lịch cá nhân của nhân viên.
- Không tự động chấm điểm, xếp hạng hoặc giám sát năng suất cá nhân.
- Không tự động thu phí chỗ bổ sung khi owner chưa xác nhận mua.
- Không xây trình soạn thảo tài liệu hoàn chỉnh hoặc hệ thống quản lý file thay thế Google Drive/Dropbox.
- Chưa chốt giá Premium, Business và giá mỗi chỗ bổ sung.
- Chưa tích hợp email nhắc gia hạn; phiên bản đầu dùng thông báo trong ứng dụng.

## 2. Hiện trạng ứng dụng

### 2.1 Thành phần có thể tái sử dụng

- Backend Flask và PostgreSQL dùng chung cho web và Expo/React Native.
- Repository đã có Flutter client; client này được đưa vào phạm vi chính thức cùng web và Expo/React Native.
- Các chức năng nền: Chat với Bob, Gmail, lịch, checklist, Overview, History, Settings và đồng bộ đa client.
- `worker` đã là một `user_mode` hợp lệ.
- Worker corpus đã hướng Bob ưu tiên email công việc, meeting, báo cáo, follow-up, blocker, planning và status update.
- Subscription hiện có bảng `subscriptions`, `payment_transactions`, API entitlement và thao tác admin cấp/gia hạn/thu hồi Premium thủ công.
- Entitlement Free/Premium hiện kiểm soát quota tóm tắt email, workflow nhiều bước, thời gian lưu chat và phân tích tuần.
- Student Mode đã có tính năng riêng theo mode và tier; có thể dùng cách tổ chức này làm mẫu cho Worker Mode.

### 2.2 Khoảng trống cần giải quyết

- “Workspace” hiện thực chất là vùng dữ liệu cá nhân theo `user_id`, chưa có workspace nhiều thành viên.
- Subscription chỉ thuộc về `user_id`, chưa thể thuộc về doanh nghiệp.
- Chưa có organization/workspace, membership, invitation, role, seat capacity hoặc cơ chế chuyển workspace.
- Phần lớn dữ liệu nghiệp vụ chỉ có `user_id`; chưa có `workspace_id`, người tạo, visibility hoặc ACL chia sẻ.
- Worker Mode hiện chủ yếu thay đổi prompt/ngữ cảnh, chưa có UI và dữ liệu nghiệp vụ riêng.
- Thanh toán hiện mới là yêu cầu xử lý thủ công; VNPay/MoMo chưa tạo giao dịch thực tế.

## 3. Persona và vai trò

### 3.1 Personal user

- Có đúng một personal workspace mặc định.
- Có thể dùng Free hoặc mua Premium cá nhân.
- Có thể tham gia nhiều Business workspace.
- Dữ liệu cá nhân không tự động chuyển sang workspace doanh nghiệp.

### 3.2 Business owner

- Tạo và sở hữu Business workspace.
- Quản lý subscription, chỗ đã mua và yêu cầu mua thêm chỗ.
- Mời, thu hồi lời mời, đổi vai trò và loại thành viên.
- Xem dashboard và audit log của dữ liệu doanh nghiệp.
- Không được đọc nguồn email/lịch cá nhân chưa được chia sẻ.

### 3.3 Business admin

- Quản lý thành viên, dự án, task và cấu hình vận hành.
- Có thể mời hoặc thu hồi lời mời trong giới hạn chỗ được owner mua.
- Không quản lý thanh toán, đổi owner hoặc xóa workspace trừ khi được bổ sung quyền riêng sau này.
- Chỉ xem dữ liệu doanh nghiệp và dữ liệu cá nhân đã được chia sẻ.

### 3.4 Worker

- Thực hiện task, cập nhật tiến độ, tham gia dự án và tạo báo cáo công việc.
- Chủ động chia sẻ email, lịch, bản tóm tắt hoặc tài liệu vào workspace.
- Xem dữ liệu chung theo dự án/quyền truy cập.
- Không quản lý subscription hoặc thành viên.

### 3.5 Ma trận quyền cấp cao

| Khả năng | Owner | Admin | Worker |
|---|---:|---:|---:|
| Xem dữ liệu chung được cấp quyền | Có | Có | Có |
| Tạo/cập nhật task, báo cáo | Có | Có | Có |
| Quản lý dự án | Có | Có | Theo quyền dự án |
| Mời và loại thành viên | Có | Có | Không |
| Đổi vai trò thành viên | Có | Có, không đổi owner | Không |
| Quản lý subscription/chỗ | Có | Chỉ xem | Không |
| Xem audit log | Có | Có | Chỉ hoạt động liên quan mình |
| Đọc Gmail/lịch cá nhân chưa chia sẻ | Không | Không | Chỉ chủ tài khoản |

## 4. Mô hình workspace

### 4.1 Personal workspace

- Được tạo tự động cho mỗi tài khoản.
- Không có membership nhiều người.
- Chủ sở hữu là người dùng duy nhất.
- Subscription hiệu lực là Free hoặc Premium cá nhân của người đó.

### 4.2 Business workspace

- Có một owner và nhiều admin/worker.
- Người dùng có thể là thành viên của nhiều Business workspace.
- Client luôn gửi `workspace_id` cho API nghiệp vụ sau khi kiến trúc mới được bật.
- Backend không tin `workspace_id` từ client; mọi request phải kiểm tra membership và trạng thái workspace.

### 4.3 Chuyển workspace

- Header/sidebar hiển thị workspace đang hoạt động.
- Chuyển workspace không đổi `user_mode` cá nhân vĩnh viễn.
- Trong personal workspace, trải nghiệm dựa trên mode cá nhân hiện tại.
- Trong Business workspace, Worker Mode là trải nghiệm mặc định cho worker; owner/admin có thêm màn hình quản trị.
- Client lưu workspace gần nhất để tiện sử dụng, nhưng backend vẫn xác thực lại quyền trên mỗi request.

### 4.4 Trạng thái workspace đề xuất

- `active`: hoạt động bình thường.
- `grace`: subscription vừa hết hạn, còn trong 7 ngày gia hạn và vẫn đủ chức năng.
- `read_only`: hết 7 ngày, chỉ đọc dữ liệu doanh nghiệp.
- `suspended`: khóa bởi quản trị hệ thống vì an toàn hoặc vi phạm; không giống hết hạn.
- `archived`: doanh nghiệp chủ động lưu trữ workspace.

## 5. Quyền riêng tư và quy tắc chia sẻ

### 5.1 Nguyên tắc mặc định

- Dữ liệu cá nhân là private-by-default.
- Tham gia Business workspace không cấp quyền Gmail, Calendar hoặc lịch sử cá nhân cho doanh nghiệp.
- OAuth token luôn thuộc người dùng, không thuộc workspace và không được lộ cho owner/admin.
- Mọi nội dung xuất hiện trong workspace phải có hành động chia sẻ rõ ràng hoặc được tạo trực tiếp trong workspace.

### 5.2 Dữ liệu doanh nghiệp có thể xem

- Project và task chung.
- Người phụ trách, deadline, trạng thái và blocker.
- Báo cáo `Done / Doing / Blocked / Next` đã gửi vào workspace.
- Meeting/work event được tạo trực tiếp trong workspace.
- Email, sự kiện lịch, bản tóm tắt hoặc tài liệu mà người dùng chủ động chia sẻ.
- Dashboard tổng hợp từ dữ liệu chung; không suy luận từ dữ liệu cá nhân chưa chia sẻ.

### 5.3 Chia sẻ email

Phiên bản đầu không cấp cho doanh nghiệp quyền truy vấn mailbox gốc. Khi người dùng chia sẻ email, hệ thống tạo một shared artifact gồm dữ liệu đã chọn, ví dụ:

- Tiêu đề hoặc tiêu đề đã che bớt.
- Người gửi/người nhận nếu người dùng cho phép.
- Bản tóm tắt, action items, deadline và nguồn tham chiếu.
- Trích đoạn nội dung do người dùng chủ động chọn.
- Dấu thời gian và người chia sẻ.

Artifact không chứa OAuth token và không cho phép owner mở những email khác trong mailbox.

### 5.4 Chia sẻ lịch

- Mặc định doanh nghiệp chỉ thấy availability `free/busy` nếu người dùng bật chia sẻ availability.
- Tiêu đề, khách mời, mô tả và vị trí sự kiện vẫn riêng tư.
- Người dùng có thể chia sẻ một sự kiện cụ thể hoặc tạo bản sao sự kiện công việc trong workspace.

### 5.5 Trung tâm chia sẻ

Mỗi người có màn hình “Đang chia sẻ” để:

- Xem artifact nào đang được chia sẻ, cho workspace nào và với ai.
- Thu hồi quyền truy cập nếu policy cho phép.
- Nhận cảnh báo trước khi chia sẻ nội dung nhạy cảm.
- Xem lịch sử ai đã tạo, sửa, xem hoặc thu hồi artifact.

### 5.6 Khi thành viên rời doanh nghiệp

- Membership bị vô hiệu hóa và mất quyền truy cập workspace ngay.
- Dữ liệu cá nhân, personal workspace và Premium cá nhân vẫn giữ nguyên.
- Task/báo cáo/artifact đã tạo trực tiếp cho doanh nghiệp tiếp tục thuộc doanh nghiệp.
- Nguồn email/lịch cá nhân vẫn thuộc người dùng; shared artifact đã công bố có thể được giữ theo retention policy của doanh nghiệp.
- Việc xóa vĩnh viễn artifact cần tuân theo policy được chốt sau.

## 6. Subscription và quản lý chỗ

### 6.1 Các cấp gói

1. `personal_free`: miễn phí cho personal workspace.
2. `personal_premium_monthly` hoặc `personal_premium_yearly`: Premium cho personal workspace.
3. `business_monthly` hoặc `business_yearly`: Business cho một workspace doanh nghiệp.

Giá của các gói và giá chỗ bổ sung là `TBD`.

### 6.2 Phạm vi entitlement

- Personal subscription chỉ có hiệu lực trong personal workspace của chủ tài khoản.
- Business subscription chỉ có hiệu lực trong Business workspace sở hữu subscription đó.
- Premium cá nhân không cộng thêm quyền hoặc chỗ cho Business workspace.
- Thành viên rời doanh nghiệp quay về quyền Free/Premium cá nhân vốn có.

### 6.3 Sức chứa Business

- Business cơ bản bao gồm 10 active seats.
- `seat_capacity = 10 + purchased_extra_seats`.
- Chỉ membership ở trạng thái `active` chiếm chỗ.
- Invitation `pending`, `declined`, `revoked`, `expired` hoặc `capacity_blocked` không chiếm chỗ.
- Owner và admin cũng chiếm chỗ vì là thành viên hoạt động.
- Người bị vô hiệu hóa/loại khỏi workspace giải phóng chỗ ngay sau transaction thành công.

### 6.4 Thành viên thứ 11

Luồng đã thống nhất:

1. Admin/owner gửi lời mời; invitation ở trạng thái `pending` và chưa chiếm chỗ.
2. Người được mời đăng nhập bằng email đã xác minh và bấm chấp nhận.
3. Backend khóa transaction theo workspace/subscription và đếm active memberships.
4. Nếu còn chỗ, tạo membership `active` và đánh dấu invitation `accepted`.
5. Nếu đã đủ 10 chỗ hoặc đủ capacity hiện tại, không kích hoạt membership.
6. Invitation chuyển thành `capacity_blocked`; hệ thống ghi nhận seat request và khoản phí dự kiến.
7. Owner nhận thông báo trong ứng dụng và phải xác nhận mua thêm chỗ.
8. Chỉ sau khi payment/admin grant thành công, capacity tăng và invitation mới có thể được chấp nhận/kích hoạt.

Không tự động thu tiền khi owner chưa xác nhận.

### 6.5 Tránh race condition khi nhận lời mời

- Việc kiểm tra capacity và kích hoạt membership phải nằm trong cùng một database transaction.
- Khóa row của workspace subscription hoặc seat allocation bằng `SELECT ... FOR UPDATE`.
- Hai người cùng nhận chỗ cuối không thể làm số active seats vượt capacity.
- API phải idempotent: bấm chấp nhận nhiều lần không tạo nhiều membership hoặc nhiều seat request.

### 6.6 Trạng thái subscription Business

- `trialing`: đầy đủ quyền theo thời gian trial nếu có.
- `active`: đầy đủ quyền.
- `past_due_grace`: thanh toán quá hạn nhưng còn trong 7 ngày; đầy đủ quyền và có cảnh báo.
- `read_only`: hết 7 ngày; chỉ đọc dữ liệu Business.
- `canceled`: không tự gia hạn; quyền còn tới cuối kỳ, sau đó vào grace/read-only.
- `suspended`: khóa thủ công vì lý do an toàn/vi phạm, không áp dụng grace mặc định.

Có thể giữ các status billing hiện tại trong bảng `subscriptions` và tính `workspace_access_state` riêng, thay vì làm status thanh toán kiêm luôn status truy cập.

### 6.7 Grace period 7 ngày

- Bắt đầu tại `current_period_end` nếu chưa gia hạn thành công.
- Trong 7 ngày, toàn bộ thành viên vẫn đọc/ghi bình thường.
- Owner/admin thấy banner cố định, số ngày còn lại và CTA gia hạn.
- Worker thấy cảnh báo thông tin nhẹ hơn để biết rủi ro gián đoạn.
- Phiên bản đầu dùng notification trong ứng dụng.
- Email nhắc owner/admin là tính năng tương lai.
- Gia hạn thành công trong grace khôi phục `active` mà không mất dữ liệu.

Việc xác định quyền truy cập không được phụ thuộc hoàn toàn vào background job. Mỗi request nhạy cảm phải tính trạng thái hiệu lực từ `current_period_end` và `grace_period_ends_at`; scheduled job phục vụ cảnh báo, materialized state, thống kê và tác vụ chủ động.

### 6.8 Read-only sau grace

Được phép:

- Đọc project, task, báo cáo, shared artifacts và audit history theo quyền hiện có.
- Tìm kiếm và xem dashboard từ snapshot/dữ liệu đã lưu.
- Chuyển về personal workspace để tiếp tục công việc cá nhân.
- Owner xem billing và thực hiện gia hạn.

Không được phép trong Business workspace:

- Tạo/sửa/xóa task, project, báo cáo, comment hoặc artifact.
- Mời/kích hoạt thành viên mới.
- Chạy workflow AI có tác dụng ghi dữ liệu doanh nghiệp.
- Đồng bộ thêm dữ liệu cá nhân vào workspace.

Sau khi gia hạn thành công, workspace trở lại `active` và quyền ghi được khôi phục. Thời gian read-only mặc định không tự xóa dữ liệu; retention lâu dài là `TBD`.

### 6.9 Scheduled expiry/grace job

- Chạy tối thiểu mỗi giờ; tần suất production có thể cấu hình.
- Tìm subscription sắp hết hạn, vừa hết hạn, sắp hết grace hoặc đã hết grace.
- Tạo notification trong ứng dụng theo mốc cấu hình, tránh tạo trùng bằng idempotency key.
- Cập nhật materialized access state nếu hệ thống dùng cột trạng thái lưu sẵn.
- Ghi audit event và số liệu job: thời điểm chạy, số record xử lý, lỗi và lần retry.
- Retry an toàn; một subscription không được nhận nhiều notification giống nhau trong cùng mốc.
- Khi user mở app trước lần chạy job kế tiếp, request-time calculation vẫn phải trả đúng trạng thái và banner.
- Email reminder sẽ dùng cùng lifecycle event ở giai đoạn sau, không viết một bộ logic hết hạn riêng.

## 7. Ma trận tính năng

| Tính năng | Free cá nhân | Premium cá nhân | Business workspace |
|---|---|---|---|
| Chat với Bob | Cơ bản | Nâng cao | Nâng cao theo ngữ cảnh doanh nghiệp |
| Email và lịch cá nhân | Có | Có | Vẫn riêng tư; chỉ chia sẻ có chủ đích |
| Tóm tắt email AI | 10 lượt/ngày hiện tại | Không giới hạn theo policy | Quota chung workspace + fair-use mỗi thành viên |
| Workflow AI nhiều bước | Không | Có | Có, kèm quyền workspace và audit |
| Lưu lịch sử chat | 30 ngày | 365 ngày | Retention doanh nghiệp `TBD` |
| Daily Brief cá nhân | Cơ bản | Nâng cao | Brief cá nhân + dữ liệu chung được phép |
| Email triage/follow-up | Cơ bản | Nâng cao | Nâng cao; chỉ chia sẻ kết quả được chọn |
| Meeting prep/follow-up | Giới hạn | Có | Có, tạo action items chung |
| Báo cáo Done/Doing/Blocked/Next | Cá nhân | Cá nhân nâng cao | Báo cáo nhóm/workspace |
| Phân tích tuần | Khóa | Cá nhân | Nhóm, chỉ từ dữ liệu chung |
| Project/task chung | Không | Không | Có |
| Mention và thông báo nhóm | Không | Không | Có |
| Kho tri thức doanh nghiệp | Không | Không | Có |
| Dashboard owner/admin | Không | Không | Có |
| Audit log doanh nghiệp | Không | Không | Có |
| Trung tâm chia sẻ | Có cho dữ liệu cá nhân | Có | Có, hiển thị đích chia sẻ |

### 7.1 Nguyên tắc AI quota Business

- Mỗi gói Business có quota AI chung theo workspace và chu kỳ billing.
- Mỗi thành viên có fair-use limit trong cùng chu kỳ để một người không tiêu thụ toàn bộ quota.
- Một request chỉ được phép khi cả workspace quota và member fair-use đều còn khả dụng.
- Owner/admin xem được mức sử dụng tổng hợp và theo thành viên, nhưng không xem prompt/nội dung riêng tư nếu dữ liệu đó chưa được chia sẻ.
- Hệ thống cảnh báo ở các ngưỡng cấu hình, ví dụ 70%, 90% và 100%; con số cuối cùng có thể cấu hình theo plan.
- Giá trị quota cụ thể vẫn là business configuration, không hardcode vào client.
- Counter phải atomic, idempotent theo AI request và dùng chung giữa nhiều backend worker.
- Refund usage hoặc không tính quota cho request thất bại theo policy thống nhất.

## 8. Trải nghiệm Worker Mode

### 8.1 Work Hub / Daily Brief

- Việc đến hạn và quá hạn.
- Meeting sắp tới và tài liệu được chia sẻ cần chuẩn bị.
- Email cần phản hồi dựa trên mailbox cá nhân, nhưng chỉ hiển thị cho chính người dùng.
- Blocker và next actions.
- 3–5 ưu tiên lớn trong ngày.
- Trong Business workspace, bổ sung task chung được giao và mention liên quan.

### 8.2 Smart Inbox

- Nhóm email thành `Action required`, `Waiting`, `FYI`, `Low priority`.
- Trích deadline, người liên quan và đề xuất phản hồi.
- Cho phép chuyển kết quả thành task cá nhân hoặc chia sẻ thành task/artifact doanh nghiệp.
- Luôn có màn hình xác nhận trước khi gửi email hoặc chia sẻ nội dung.

### 8.3 Meeting Assistant

- Trước họp: agenda, tài liệu cần đọc, câu hỏi và outcome mong muốn.
- Sau họp: decision, owner, deadline, follow-up và bản nháp thông báo.
- Chỉ dữ liệu được xác nhận mới ghi vào project/task chung.

### 8.4 Project và task chung

- Project có owner, thành viên, trạng thái và mốc thời gian.
- Task có assignee, due date, priority, blocker, nguồn và visibility.
- Hỗ trợ comment, mention và audit events.
- Worker chỉ thấy project/task theo membership hoặc quyền dự án.

### 8.5 Status Report

- Mẫu `Done / Doing / Blocked / Next / Risks`.
- Trong Phase 3, Bob chỉ tạo bản nháp từ task, project, comment, meeting và dữ liệu đã tồn tại hợp lệ trong workspace.
- Phase 3 không đọc hoặc kéo email, lịch, ghi chú hay dữ liệu personal workspace vào báo cáo.
- Từ Phase 4, Bob có thể đề xuất dùng dữ liệu cá nhân nhưng chỉ đưa vào bản nháp sau bước `confirm-before-sharing` rõ ràng.
- Người dùng phải review trước khi gửi vào workspace.
- Bản đã gửi là dữ liệu doanh nghiệp; bản nháp cá nhân vẫn riêng tư.

### 8.6 Dashboard nhóm

- Tiến độ task/project, deadline, blocker và workload từ dữ liệu chung.
- Không dùng số lần online, thời gian mở app, nội dung email riêng tư hoặc lịch cá nhân để đánh giá.
- Không tạo “điểm năng suất nhân viên” trong phiên bản này.

### 8.7 Knowledge doanh nghiệp

- Policy, template, quy trình, FAQ và tài liệu được doanh nghiệp tải/chia sẻ.
- RAG phải lọc tuyệt đối theo `workspace_id` và quyền tài liệu.
- Kết quả Bob phải chỉ rõ nguồn là cá nhân hay doanh nghiệp.
- Khi người dùng đổi workspace, cache/conversation context không được rò chéo tenant.

## 9. Mô hình dữ liệu đề xuất

Tên bảng/cột dưới đây là đề xuất kỹ thuật, chưa phải migration cuối cùng.

### 9.1 `workspaces`

- `id UUID PRIMARY KEY`
- `type TEXT CHECK IN ('personal', 'business')`
- `name`, `slug`, `avatar_url`
- `owner_user_id REFERENCES users(user_id)`
- `status TEXT`
- `settings JSONB`
- `created_at`, `updated_at`, `archived_at`

Ràng buộc: mỗi user có đúng một personal workspace; Business workspace có đúng một owner.

### 9.2 `workspace_memberships`

- `id UUID PRIMARY KEY`
- `workspace_id REFERENCES workspaces(id)`
- `user_id REFERENCES users(user_id)`
- `role TEXT CHECK IN ('owner', 'admin', 'worker')`
- `status TEXT CHECK IN ('active', 'disabled', 'removed')`
- `joined_at`, `disabled_at`, `removed_at`
- `created_at`, `updated_at`

Unique: `(workspace_id, user_id)`.

### 9.3 `workspace_invitations`

- `id UUID PRIMARY KEY`
- `workspace_id`
- `email_normalized`
- `role`
- `status CHECK IN ('pending', 'accepted', 'declined', 'revoked', 'expired', 'capacity_blocked')`
- `token_hash`, không lưu token mời dạng rõ.
- `invited_by_user_id`
- `expires_at`, `accepted_at`, `created_at`, `updated_at`

Invitation chỉ được chấp nhận khi email đăng nhập đã xác minh khớp `email_normalized` theo so sánh không phân biệt hoa thường.

### 9.4 Mở rộng `subscriptions`

Phương án khuyến nghị:

- Cho phép subscription thuộc một trong hai chủ thể: `user_id` hoặc `workspace_id`.
- Thêm constraint bảo đảm đúng một chủ thể được đặt.
- Thêm `included_seats`, `extra_seats`, `grace_period_ends_at` và metadata provider.
- Giữ tương thích ngược: subscription hiện tại tiếp tục là personal subscription theo `user_id`.

Nếu muốn foreign key rõ ràng hơn, có thể tách `personal_subscriptions` và `workspace_subscriptions`; quyết định cuối cùng sau khi review migration.

### 9.5 `workspace_seat_requests`

- `id UUID PRIMARY KEY`
- `workspace_id`, `invitation_id`
- `requested_seats`
- `quoted_unit_amount`, `currency`
- `status CHECK IN ('pending_owner', 'payment_pending', 'approved', 'rejected', 'expired')`
- `requested_by_user_id`, `approved_by_user_id`
- `created_at`, `updated_at`

### 9.6 Dữ liệu nghiệp vụ chung

Các bảng project/task/report/artifact mới cần tối thiểu:

- `workspace_id`
- `created_by_user_id`
- `updated_by_user_id`
- `visibility`
- `created_at`, `updated_at`, `deleted_at`

Không nên chỉ thêm `workspace_id` vào mọi bảng cũ một cách cơ học. Email/lịch cá nhân vẫn theo `user_id`; workspace chỉ lưu shared artifact đã được công bố.

### 9.7 `shared_artifacts`

- `id UUID PRIMARY KEY`
- `workspace_id`
- `source_type` như `email_summary`, `calendar_event`, `report`, `note`, `document_reference`
- `source_owner_user_id`
- `created_by_user_id`
- `content JSONB` đã lọc theo lựa chọn chia sẻ
- `visibility` và ACL nếu cần
- `revoked_at`, `retention_until`
- `created_at`, `updated_at`

### 9.8 `workspace_audit_events`

- `workspace_id`, `actor_user_id`
- `event_type`
- `target_type`, `target_id`
- `metadata JSONB` đã loại secret/nội dung nhạy cảm không cần thiết
- `created_at`

Audit là append-only đối với application role thông thường.

### 9.9 `notifications`

- `recipient_user_id`, `workspace_id`
- `type`, `severity`, `title`, `body`
- `action_url`, `read_at`, `expires_at`
- Dùng cho lời mời, thiếu chỗ, grace period, read-only, mention và subscription.

### 9.10 AI usage Business

Có thể mở rộng bảng usage hiện tại hoặc thêm ledger/counter theo hai chiều:

- `workspace_id`, `user_id`, `billing_period_start`
- `feature`, `request_id` idempotent
- `units_reserved`, `units_consumed`, `status`
- `created_at`, `updated_at`

Workspace counter và member counter phải được reserve/commit trong cùng transaction hoặc bằng cơ chế atomic tương đương. Không chỉ tính quota bằng cách cộng log tại request time vì dễ race khi có nhiều backend worker.

### 9.11 Lifecycle job runs

Lưu trạng thái scheduled job đủ để vận hành và retry:

- `job_name`, `scheduled_for`, `started_at`, `finished_at`
- `status`, `attempt`, `processed_count`, `error_summary`
- Unique/idempotency key theo job và time window.

## 10. API và cách tính quyền

### 10.1 API workspace đề xuất

- `GET /api/workspaces`
- `POST /api/workspaces` — tạo Business workspace.
- `GET /api/workspaces/<id>`
- `PATCH /api/workspaces/<id>`
- `GET /api/workspaces/<id>/members`
- `POST /api/workspaces/<id>/invitations`
- `POST /api/workspace-invitations/<token>/accept`
- `POST /api/workspace-invitations/<id>/decline`
- `POST /api/workspaces/<id>/members/<user_id>/disable`
- `PATCH /api/workspaces/<id>/members/<user_id>/role`

### 10.2 API subscription/chỗ đề xuất

- `GET /api/workspaces/<id>/subscription`
- `POST /api/workspaces/<id>/subscription/intent`
- `GET /api/workspaces/<id>/seats`
- `POST /api/workspaces/<id>/seat-requests`
- `POST /api/workspaces/<id>/seat-requests/<request_id>/confirm`

Các API payment provider/webhook sẽ bổ sung sau. Admin grant thủ công phải tạo cùng một dạng entitlement/seat allocation như payment thật.

### 10.3 API chia sẻ đề xuất

- `GET /api/workspaces/<id>/shared-artifacts`
- `POST /api/workspaces/<id>/shared-artifacts`
- `DELETE /api/workspaces/<id>/shared-artifacts/<artifact_id>` — revoke theo policy.
- `GET /api/user/sharing`

### 10.4 Entitlement resolver chuẩn

Mọi route/service dùng một resolver trung tâm thay vì gọi `is_premium(user_id)` trực tiếp:

```text
resolve_access(user_id, workspace_id, feature, action)
  -> membership + role
  -> workspace access state
  -> subscription owner/tier
  -> feature limit
  -> object-level visibility/ACL
  -> allow/deny + reason + effective limits
```

Các mã từ chối nên ổn định để web/mobile xử lý thống nhất:

- `membership_required`
- `insufficient_role`
- `feature_not_entitled`
- `workspace_grace_warning`
- `workspace_read_only`
- `seat_capacity_reached`
- `invitation_email_mismatch`
- `artifact_not_shared`

### 10.5 Quyền hiệu lực

```text
Personal workspace:
  personal role + personal subscription + personal feature limits

Business workspace:
  membership role + Business subscription + workspace state
  + project/object ACL + sharing visibility
```

Không fallback sang Premium cá nhân để vượt giới hạn hoặc mở tính năng Business trong workspace doanh nghiệp.

### 10.6 Rollout entitlement bằng shadow mode

Không cutover trực tiếp từ `is_premium(user_id)` sang resolver mới:

1. **Shadow:** logic cũ tiếp tục quyết định; resolver mới chạy song song và chỉ ghi kết quả đã khử dữ liệu nhạy cảm.
2. **Compare:** đo mismatch theo user, workspace, feature và reason code; cảnh báo các sai lệch có thể ảnh hưởng billing/quyền.
3. **Limited rollout:** bật resolver mới bằng feature flag cho internal workspace/canary cohort nhỏ.
4. **Progressive rollout:** tăng dần tỷ lệ khi mismatch và error rate đạt ngưỡng cho phép.
5. **Full cutover:** chỉ loại bỏ đường quyết định cũ sau thời gian ổn định được chốt.

Bắt buộc có feature flag, dashboard/metrics mismatch, audit log và rollback nhanh về logic cũ. Log so sánh không chứa prompt, email hoặc nội dung tài liệu.

## 11. Luồng trạng thái và trường hợp lỗi

### 11.1 Invitation

```text
pending -> accepted
pending -> declined
pending -> revoked
pending -> expired
pending -> capacity_blocked -> accepted (sau khi mua chỗ)
```

### 11.2 Business access

```text
active -> grace (7 ngày, full access) -> read_only
grace -> active (gia hạn thành công)
read_only -> active (gia hạn thành công)
active/grace/read_only -> suspended (quản trị hệ thống)
```

### 11.3 Các trường hợp bắt buộc xử lý

- Hai người nhận chỗ cuối cùng đồng thời.
- Owner mua thêm chỗ trong lúc invitation đang `capacity_blocked`.
- Payment thành công nhưng webhook được gửi lặp.
- Thành viên đổi email sau khi nhận invitation.
- Một tài khoản là worker ở workspace A và admin ở workspace B.
- Workspace chuyển read-only khi người dùng đang mở form chỉnh sửa.
- Thành viên bị loại khi đang đăng nhập trên nhiều thiết bị.
- Bob đang giữ conversation context của workspace A rồi người dùng chuyển sang B.
- Artifact bị thu hồi nhưng vẫn còn trong cache/search index.
- Subscription cá nhân và Business cùng hết hạn ở các thời điểm khác nhau.

## 12. Bảo mật và audit

- Xác minh membership ở backend cho mọi request; không dựa vào UI ẩn/hiện nút.
- Mọi query Business bắt buộc có `workspace_id` và điều kiện tenant rõ ràng.
- Không đưa OAuth token, password hash hoặc invitation token rõ vào response/log/audit.
- Invitation token phải ngẫu nhiên đủ mạnh, lưu hash và có thời hạn.
- Email nhận lời mời phải là email đăng nhập đã xác minh.
- Role change, member removal, sharing, revoke, billing và seat change phải có audit event.
- Cache key, RAG index, chat context và background jobs phải bao gồm `workspace_id`.
- Thao tác gửi email, tạo/sửa/xóa dữ liệu và chia sẻ nội dung vẫn cần bước xác nhận phù hợp.
- Admin/owner không được nâng quyền để truy vấn OAuth token hoặc dữ liệu private của worker.
- Cần test chống IDOR và cross-tenant leakage cho từng API mới.

### 12.1 Runtime cross-workspace monitoring

- Mỗi request có correlation ID và ghi nhận actor, session workspace, requested workspace, resource workspace, route, decision và reason code.
- Nếu session/request/resource workspace không khớp, request phải bị chặn trước khi đọc nội dung và sinh security event.
- Theo dõi permission denied tăng bất thường, cross-workspace attempts, entitlement mismatch và Bob/tool dùng sai context.
- Alert theo rate/window để tránh spam; sự kiện mức nghiêm trọng cao có thể cảnh báo ngay.
- Security dashboard ban đầu có thể dùng log/metrics hiện có; không bắt buộc xây UI riêng ở Phase 1.
- Không ghi secret hoặc nội dung private vào monitoring payload.
- Khi đổi workspace, client hủy request cũ nếu có thể; backend vẫn phải tự bảo vệ nếu request cũ đến muộn.

## 13. Migration từ hệ thống hiện tại

### Giai đoạn migration 1: nền tảng workspace

- Tạo personal workspace cho mỗi user hiện có.
- Backfill liên kết personal workspace mà không đổi `user_id` hiện tại.
- Giữ API cũ hoạt động bằng cách tự resolve personal workspace khi client chưa gửi `workspace_id`.
- Đưa tenant isolation, workspace-scoped cache/context key và audit foundation vào ngay giai đoạn này.

### Giai đoạn migration 2: subscription owner

- Giữ mọi subscription hiện có là personal subscription.
- Thêm khả năng subscription thuộc Business workspace.
- Thay các lời gọi `is_premium(user_id)` bằng entitlement resolver theo từng route.
- Trước cutover, chạy resolver mới ở shadow mode, so sánh kết quả và bảo vệ bằng feature flag.

### Giai đoạn migration 3: membership và invitation

- Bật tạo Business workspace, mời email, chuyển workspace và role checks.
- Chưa cần bật project/task chung cho tới khi tenant isolation đã được kiểm thử.

### Giai đoạn migration 4: dữ liệu Worker Business

- Thêm project, task, status report, shared artifact, notification và audit.
- Tích hợp Work Hub, Meeting Assistant và Knowledge doanh nghiệp.

### Giai đoạn migration 5: billing

- Seat request và admin grant thủ công trước.
- Sau đó tích hợp payment provider/webhook idempotent.
- Email nhắc gia hạn triển khai sau notification trong ứng dụng.

### Tương thích client

- Backend đi trước và vẫn hỗ trợ client cũ trong thời gian rolling deployment.
- Web, Expo/React Native và Flutter là ba client chính thức cần cập nhật đồng bộ.
- Cả ba phải dùng cùng API contract, reason code, workspace switch, entitlement và notification state.
- Authentication/session-token strategy phải được kiểm chứng riêng trên web và hai mobile stack.
- API versioning/compatibility phải cho phép ba client rollout không cùng thời điểm.
- File upload/download, deep link invitation và notification navigation phải có contract dùng chung và kiểm thử theo từng client.

## 14. Kiểm thử và tiêu chí nghiệm thu

### 14.1 Workspace/membership

- Mỗi user mới có personal workspace.
- Một user tham gia được nhiều Business workspace với vai trò khác nhau.
- Email không khớp hoặc chưa xác minh không thể nhận lời mời.
- Worker không gọi được API owner/admin bằng request thủ công.

### 14.2 Seat capacity

- Business cơ bản kích hoạt tối đa 10 memberships.
- Invitation pending không chiếm chỗ.
- Thành viên thứ 11 bị `seat_capacity_reached/capacity_blocked`.
- Hệ thống tạo đúng một seat request dù client retry.
- Sau khi mua một chỗ, đúng một thành viên bị chặn có thể kích hoạt.
- Concurrent accept không làm active seats vượt capacity.

### 14.3 AI quota Business

- Request bị chặn khi workspace quota hết dù member còn fair-use.
- Request bị chặn khi member fair-use hết dù workspace còn quota.
- Hai request đồng thời không làm counter vượt giới hạn ngoài policy cho phép.
- Retry cùng `request_id` không bị tính quota hai lần.
- Owner xem được usage tổng hợp mà không thấy nội dung private.

### 14.4 Subscription lifecycle

- Hết kỳ chuyển sang grace và vẫn đọc/ghi trong đúng 7 ngày.
- Owner/admin nhận notification; worker nhận cảnh báo thông tin.
- Hết grace, mutation Business trả `workspace_read_only`.
- Các read API vẫn hoạt động trong read-only.
- Gia hạn từ grace/read-only khôi phục quyền ghi mà không mất dữ liệu.
- Scheduled job tạo notification đúng mốc và không tạo trùng khi retry.
- Request-time calculation vẫn đúng nếu scheduled job chậm hoặc tạm lỗi.

### 14.5 Privacy

- Owner không thể liệt kê Gmail/lịch private của worker.
- Chỉ artifact được chia sẻ xuất hiện trong Business workspace.
- Revoke loại artifact khỏi API, search, cache và RAG theo policy.
- Chuyển workspace không làm lẫn chat context, result cache hoặc knowledge.
- Thành viên bị loại mất quyền ngay trên web và mobile.

### 14.6 Worker features

- Daily Brief phân biệt rõ nguồn cá nhân và doanh nghiệp.
- Status report chỉ được công bố sau khi user xác nhận.
- Meeting/email workflow không tự chia sẻ nội dung private.
- Dashboard chỉ tổng hợp dữ liệu Business hợp lệ.
- Phase 3 Status Report không truy cập dữ liệu personal workspace.
- Phase 4 chỉ dùng dữ liệu cá nhân sau confirm-before-sharing.

### 14.7 Entitlement migration

- Shadow resolver không thay đổi quyền thật.
- Mismatch có metric, log và reason code đủ để điều tra.
- Limited rollout có thể dừng và rollback bằng feature flag.
- User trả phí không mất quyền ngoài policy trong quá trình migration.

### 14.8 Runtime security

- Request cross-workspace bị chặn trước khi serialize resource.
- Security event có correlation ID nhưng không chứa nội dung nhạy cảm.
- Bob/tool không dùng context của workspace trước sau khi chuyển workspace.
- Alert rate limit hoạt động và không tạo bão cảnh báo.

### 14.9 Tương thích client

- Web, Expo/React Native và Flutter cùng xử lý invitation, workspace switch, grace/read-only và entitlement reason code.
- Client cũ không gửi `workspace_id` vẫn được giới hạn an toàn vào personal workspace trong cửa sổ tương thích.
- Deep link invitation và authentication được kiểm thử trên cả hai mobile stack.

### 14.10 Không làm hỏng chức năng hiện tại

- Personal Free/Premium vẫn giữ quota và entitlement hiện có.
- Student Mode và các tính năng riêng vẫn hoạt động.
- Admin grant/renew/revoke cá nhân tiếp tục hoạt động.
- Web và Expo nhận cùng entitlement/result code.

## 15. Lộ trình triển khai và Definition of Done

### Phase 1 — Foundation

Phạm vi:

- Workspace model, personal workspace backfill, membership, invitation và role.
- Tenant-aware request context và workspace switcher.
- Web, Expo/React Native và Flutter dùng chung API/auth contract.
- Tenant/workspace isolation foundation cho database, cache, background job và Bob context key.
- Audit logging foundation, correlation ID và runtime detection cơ bản.

Definition of Done:

- Mỗi user hiện có và user mới có đúng một personal workspace.
- Một user tham gia được nhiều Business workspace với role khác nhau.
- API từ chối IDOR/cross-workspace trước khi đọc resource.
- Cache/context key chứa `workspace_id`; test leakage nền tảng pass.
- Invitation email verification và role checks pass.
- Workspace list/switch hoạt động trên web, Expo và Flutter.
- Migration/backfill có dry-run, rollback procedure và không làm mất dữ liệu.
- Audit event tồn tại cho create workspace, invite, accept, role change và removal.

### Phase 2 — Subscription, seat và entitlement foundation

Phạm vi:

- Subscription thuộc personal user hoặc Business workspace.
- Base 10 seats, extra seat request, transactional capacity lock và admin grant.
- AI quota chung workspace + member fair-use; giá trị quota cấu hình theo plan.
- Grace 7 ngày, read-only, scheduled expiry job và in-app notification.
- Entitlement resolver bản đầu chạy shadow/compare với logic cũ.
- Billing, seat và entitlement audit events.

Definition of Done:

- Seat limit/add/remove và thành viên thứ 11 hoạt động đúng kể cả concurrent accept.
- Workspace/member AI counters atomic, idempotent và enforcement đúng cả hai tầng.
- Grace/read-only đúng theo request time dù job chậm; scheduled notification không trùng.
- Owner/admin/worker permission đúng cho billing và seat.
- Shadow mismatch có metrics, log và alert; feature flag/rollback được diễn tập.
- API/UI trạng thái subscription nhất quán trên cả ba client.
- Test seat, quota, billing, lifecycle, audit và entitlement pass.

### Phase 3 — Bob core và Status Report

Phạm vi:

- Project/task chung, Work Hub và mention/notification cơ bản.
- Bob hoạt động theo workspace hiện tại.
- Memory, conversation và tool context scope theo `workspace_id`.
- Reset/reload đúng context khi chuyển workspace.
- Status Report `Done / Doing / Blocked / Next / Risks` chỉ dùng dữ liệu đã nằm trong workspace.

Definition of Done:

- Bob chỉ truy cập dữ liệu workspace hiện tại và object mà member được phép xem.
- Chuyển workspace không leak memory, conversation, tool result, cache hoặc RAG context.
- Status Report Phase 3 không đọc email/lịch/note/personal workspace.
- Người dùng review trước khi công bố báo cáo.
- Permission checks áp dụng cho project/task/report và Bob tools.
- Cross-workspace automated/security tests pass trên API và luồng Bob.
- Web, Expo và Flutter hiển thị Work Hub/Status Report nhất quán.

### Phase 4 — Personal data và privacy-first sharing

Phạm vi:

- Shared email/calendar artifacts và Trung tâm chia sẻ.
- `confirm-before-sharing` cho dữ liệu cá nhân.
- User chọn trường/nội dung được chia sẻ và đích workspace.
- Revoke, audit trail, privacy permission và sensitive-data handling.
- Meeting Assistant tạo action items chung sau xác nhận.

Definition of Done:

- Bob không tự đưa dữ liệu cá nhân vào workspace.
- Mỗi hành động chia sẻ có xác nhận rõ nội dung, đích và visibility.
- Owner/admin không truy vấn được mailbox/calendar nguồn.
- Revoke được thực thi trên API, cache, search và RAG theo policy.
- Có audit trail cho share/view/revoke mà không ghi secret.
- Privacy, accidental-sharing và cross-workspace tests pass.
- Confirm/share/revoke hoạt động trên cả ba client.

### Phase 5 — Advanced workspace và AI

Phạm vi:

- Knowledge/RAG doanh nghiệp có ACL và tenant isolation.
- Dashboard nhóm từ dữ liệu chung, workflow phức tạp và policy nâng cao.
- Context/memory nâng cao trong giới hạn workspace.
- Runtime security monitoring mở rộng và admin/security dashboard.
- Retention policy và export khi đã chốt.

Definition of Done:

- RAG chỉ trả nguồn hợp lệ trong workspace và quyền tài liệu hiện tại.
- Dashboard không suy luận từ dữ liệu cá nhân chưa chia sẻ.
- Workflow nhiều bước kiểm tra entitlement/permission ở từng tool action.
- Runtime monitoring phát hiện cross-workspace, permission anomaly và Bob context mismatch.
- Alert có correlation ID, rate limit và runbook xử lý.
- Load/performance test đạt ngưỡng được chốt cho workspace nhỏ-vừa.

### Phase 6 — Billing automation và production hardening

Phạm vi:

- Payment provider, renewal, failed payment và webhook idempotent.
- Subscription/seat automation, invoice và email nhắc gia hạn.
- Full entitlement cutover khi shadow/limited rollout ổn định.
- Monitoring, alerting, rollback và production hardening.

Definition of Done:

- Payment/webhook retry không tạo subscription, transaction hoặc seat trùng.
- Renewal, failed payment, grace và recovery được test end-to-end.
- Entitlement mismatch đạt ngưỡng cutover được phê duyệt trong thời gian quan sát đã chốt.
- Full cutover có rollback đã diễn tập và không làm mất quyền user trả phí.
- Notification trong app và email không gửi trùng.
- Dashboard vận hành, alert, backup/restore và incident runbook sẵn sàng.
- Web, Expo và Flutter pass regression/E2E cho billing lifecycle.

## 16. Các quyết định đã duyệt

- Mỗi người có personal workspace và có thể tham gia workspace doanh nghiệp.
- Doanh nghiệp mời theo email; nhân viên phải chủ động chấp nhận.
- Email đăng nhập đã xác minh phải khớp lời mời.
- Doanh nghiệp chỉ thấy dữ liệu được chia sẻ, không thấy toàn bộ Gmail/lịch cá nhân.
- Gói gồm Free cá nhân, Premium cá nhân và Business workspace.
- Business cơ bản gồm 10 chỗ; giá chưa chốt.
- Thành viên thứ 11 bị chặn cho tới khi owner mua thêm chỗ.
- Hệ thống ghi nhận yêu cầu/phí dự kiến nhưng không tự động thu tiền.
- Hết hạn có 7 ngày grace đầy đủ chức năng, sau đó read-only.
- Phiên bản đầu nhắc gia hạn trong ứng dụng; email để triển khai sau.
- Người rời doanh nghiệp giữ dữ liệu và subscription cá nhân nếu đã mua.
- Phân tầng tính năng Worker Free/Premium/Business trong tài liệu đã được duyệt làm hướng thiết kế.
- Web, Expo/React Native và Flutter đều nằm trong phạm vi client chính thức.
- AI quota Business dùng quota chung workspace kết hợp fair-use theo từng thành viên.
- Phase 3 Status Report chỉ dùng dữ liệu workspace; Phase 4 mới dùng dữ liệu cá nhân sau confirm-before-sharing.
- Entitlement mới phải rollout bằng shadow mode, compare, limited rollout và feature flag rollback.
- Workspace memory/context isolation phải hoàn thành chậm nhất trong Phase 3.

## 17. Các quyết định còn mở (TBD)

- Giá Premium tháng/năm.
- Giá Business tháng/năm.
- Giá mỗi chỗ bổ sung và cách tính prorate.
- Có trial Business hay không và thời lượng trial.
- Payment provider ưu tiên: VNPay, MoMo, Google Play Billing, RevenueCat hoặc nhà cung cấp khác.
- Retention của project, report, audit log và shared artifact.
- Người dùng có được thu hồi artifact đã trở thành hồ sơ công việc chính thức hay chỉ yêu cầu admin xử lý.
- Giá trị quota AI chung và fair-use theo từng plan/chu kỳ.
- Có cần custom role ngoài `owner/admin/worker` trong phiên bản sau hay không.
- Chính sách export/xóa workspace khi doanh nghiệp ngừng dịch vụ lâu dài.

## 18. Checklist bắt buộc trước khi bắt đầu code

- [x] Chốt client: web, Expo/React Native và Flutter.
- [x] Chốt mô hình AI quota: workspace pool + member fair-use.
- [x] Chốt Status Report Phase 3 chỉ dùng workspace data.
- [ ] Chốt tenant/workspace isolation model ở mức schema và request context.
- [ ] Thiết kế workspace-scoped Bob memory/conversation/tool context chi tiết.
- [ ] Thiết kế scheduled expiry/grace job và idempotent notification.
- [ ] Thiết kế entitlement shadow comparison, metrics, feature flag và rollback.
- [ ] Chốt API/auth/versioning contract dùng chung cho ba client.
- [ ] Chốt audit event taxonomy và dữ liệu tuyệt đối không được log.
- [ ] Thiết kế runtime cross-workspace monitoring, alert threshold và runbook.
- [ ] Viết migration/backfill/rollback plan chi tiết cho Phase 1.
- [ ] Chốt Definition of Done của phase hiện tại trước khi triển khai phase đó.
