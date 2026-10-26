# Nhiệm vụ

Tạo đúng **một câu mới, tự nhiên và tương đối phức tạp**, pha trộn tiếng Việt với tiếng Anh, dùng làm dữ liệu chuẩn hóa văn bản thành lời nói. Mỗi lần thực hiện, chọn một tình huống và cách diễn đạt mới; không chép lại các ví dụ bên dưới.

Câu phải đáp ứng tất cả các điều kiện sau:

- Tiếng Việt chiếm đa số, viết đầy đủ dấu.
- Có ít nhất một từ hoặc cụm từ tiếng Anh được dùng tự nhiên trong câu.
- Có ít nhất một thực thể tên riêng thật sự: tên người, địa điểm, tổ chức hoặc thương hiệu. Có thể sáng tạo tên riêng hợp lý.
- Chọn tên riêng có thể đọc tự nhiên thành từ; không dùng tên viết tắt phải đánh vần từng chữ cái.

Đa dạng hóa chủ đề như công việc, gia đình, mua sắm, giao hàng, lịch hẹn, du lịch hoặc học tập. Luân phiên các biểu thức như giờ, ngày tháng, số lượng, giá tiền, phần trăm, số đo, địa chỉ hoặc mã đơn; không cần nhồi tất cả vào cùng một câu.

# Định dạng đầu ra

Chỉ trả về **một đối tượng JSON hợp lệ** với đúng ba trường:

- `written_text`: câu ở dạng viết thông thường, có thể chứa chữ số, ký hiệu và tên riêng.
- `normalized_text`: cùng câu đó ở dạng đọc. Chỉ chuyển các biểu thức cần đọc thành chữ; giữ nguyên mọi từ khác, tên riêng, từ tiếng Anh và dấu câu bên ngoài các biểu thức được chuyển đổi. 
- `named_entities`: một mảng các mảng con, theo thứ tự xuất hiện trong `written_text`.

Không trả về Markdown, hàng rào mã, chú thích, lời giải thích, danh sách nhiều mẫu hoặc bất kỳ trường nào khác. `written_text` và `normalized_text` phải là chuỗi; `named_entities` phải là mảng.


# Quy tắc cho `named_entities`

Trường này bao gồm **cả tên riêng và các biểu thức số hoặc ký hiệu đã được chuẩn hóa**:

- Tên riêng được giữ nguyên: ghi mảng con có đúng một chuỗi, ví dụ `["John Duy"]` hoặc `["Đà Nẵng"]`.
- Biểu thức được chuyển đổi: ghi mảng con có đúng hai chuỗi `[dạng viết, dạng đọc]`, ví dụ `["9:45", "chín giờ bốn lăm"]` hoặc `["230", "hai trăm ba mươi"]`.
- Chuỗi đầu tiên phải là một đoạn xuất hiện nguyên văn, đúng chữ hoa, dấu và ký tự trong `written_text`. Với mảng hai chuỗi, chuỗi thứ hai phải là đoạn thay thế tương ứng trong `normalized_text`. Với mảng một chuỗi, tên đó phải được giữ nguyên trong `normalized_text`.
- Liệt kê theo thứ tự xuất hiện; không liệt kê trùng một mục giống hệt nhau. Nếu tên được nhắc lại, chỉ ghi một mục cho tên đó.
- Bao phủ mọi tên riêng và mọi biểu thức số hoặc ký hiệu đã được chuyển đổi trong câu. 

# Ví dụ minh họa — không chép lại

```json
{
  "written_text": "John Duy sẽ về nhà lúc 9:45 sau khi hoàn tất meeting với Anna Trần, miễn là nhóm gửi đủ 230 ảnh trước giờ đó.",
  "normalized_text": "John Duy sẽ về nhà lúc chín giờ bốn lăm sau khi hoàn tất meeting với Anna Trần, miễn là nhóm gửi đủ hai trăm ba mươi ảnh trước giờ đó.",
  "named_entities": [
    ["John Duy"],
    ["9:45", "chín giờ bốn lăm"],
    ["Anna Trần"],
    ["230", "hai trăm ba mươi"]
  ]
}
```

```json
{
  "written_text": "Linh Nguyễn nhờ Green Studio gửi feedback về bộ ảnh trị giá 1.230.000đ trước 14:05 ngày mai để cả nhóm kịp sửa theo deadline đã thống nhất.",
  "normalized_text": "Linh Nguyễn nhờ Green Studio gửi feedback về bộ ảnh trị giá một triệu hai trăm ba mươi nghìn đồng trước mười bốn giờ không năm ngày mai để cả nhóm kịp sửa theo deadline đã thống nhất.",
  "named_entities": [
    ["Linh Nguyễn"],
    ["Green Studio"],
    ["1.230.000đ", "một triệu hai trăm ba mươi nghìn đồng"],
    ["14:05", "mười bốn giờ không năm"]
  ]
}
```

```json
{
  "written_text": "Emily Phạm đã nhờ Giao Hàng Nhanh giao kiện hàng nặng 2.5kg đến Đà Nẵng trong 3-5 ngày, nhưng chị vẫn muốn nhận update trước khi chốt mức giảm 25% cho khách.",
  "normalized_text": "Emily Phạm đã nhờ Giao Hàng Nhanh giao kiện hàng nặng hai phẩy năm ki lô gam đến Đà Nẵng trong ba đến năm ngày, nhưng chị vẫn muốn nhận update trước khi chốt mức giảm hai lăm phần trăm cho khách.",
  "named_entities": [
    ["Emily Phạm"],
    ["Giao Hàng Nhanh"],
    ["2.5kg", "hai phẩy năm ki lô gam"],
    ["Đà Nẵng"],
    ["3-5", "ba đến năm"],
    ["25%", "hai lăm phần trăm"]
  ]
}
```

Trước khi trả lời, tự kiểm tra các điều kiện trên, đặc biệt là đúng cấu trúc mảng con trong `named_entities`, giữ nguyên từ tiếng Anh, đa số tiếng Việt và không có từ “mươi” trong `normalized_text`. Sau đó chỉ xuất một đối tượng JSON mới.
