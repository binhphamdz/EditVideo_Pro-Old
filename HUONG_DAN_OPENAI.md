# 🤖 HƯỚNG DẪN SỬ DỤNG OPENAI API (CHATGPT)

## 📌 Giới thiệu
Tool đã được tích hợp OpenAI ChatGPT API làm phương án dự phòng khi Kie.ai gặp sự cố. Bạn có thể chọn giữa:
- **Kie.ai** - Miễn phí, sử dụng Gemini
- **OpenAI** - Trả phí, chất lượng cao, nhiều models lựa chọn

## 🔑 Cách lấy OpenAI API Key

### Bước 1: Tạo tài khoản OpenAI
1. Truy cập: https://platform.openai.com/signup
2. Đăng ký tài khoản mới hoặc đăng nhập

### Bước 2: Lấy API Key
1. Sau khi đăng nhập, truy cập: https://platform.openai.com/api-keys
2. Click nút **"Create new secret key"**
3. Đặt tên cho key (ví dụ: "EditVideo_Pro")
4. **LƯU Ý QUAN TRỌNG**: Copy ngay API key, vì bạn sẽ không thể xem lại!
5. Format key sẽ là: `sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Bước 3: Nạp tiền vào tài khoản
1. Truy cập: https://platform.openai.com/settings/organization/billing
2. Click **"Add payment method"**
3. Thêm thẻ tín dụng/ghi nợ
4. Nạp credit (tối thiểu $5)

## 💰 Giá cả các Models

### Models được hỗ trợ (từ rẻ → đắt):
1. **gpt-3.5-turbo** - $0.50 / 1M tokens (~$0.0005/request)
2. **gpt-3.5-turbo-16k** - $1.50 / 1M tokens  
3. **gpt-4o-mini** - $0.15-0.60 / 1M tokens (✅ Khuyến nghị)
4. **gpt-4o** - $2.50-10 / 1M tokens
5. **gpt-4-turbo** - $10-30 / 1M tokens
6. **gpt-4** - $30-60 / 1M tokens

### Ước tính chi phí:
- **1 lần bóc băng** (trích xuất info + keys): ~$0.001-0.005
- **1 lần xào kịch bản**: ~$0.002-0.01
- **100 kịch bản hoàn chỉnh**: ~$0.50-1.50 (dùng gpt-4o-mini)

## ⚙️ Cách sử dụng trong Tool

### 1. Mở Tab 7 (Script/Kịch bản)

### 2. Cấu hình AI Provider
- Chọn radio button **"OpenAI (ChatGPT)"**
- Nhập API Key vào ô **"OpenAI Key"**
- Chọn model trong dropdown **"Model"**:
  - `gpt-4o-mini` - Cân bằng giá/chất lượng ✅
  - `gpt-4o` - Chất lượng cao
  - `gpt-3.5-turbo` - Rẻ nhất

### 3. Sử dụng bình thường
- Click **"🔑 2. AI BÓC THÔNG TIN SP & 10 KEY"**
- Click **"✨ 3. XÀO KỊCH BẢN"**
- Tool sẽ tự động dùng OpenAI thay vì Kie.ai

## 🔒 Bảo mật API Key

### ⚠️ Lưu ý quan trọng:
- **KHÔNG** share API key cho người khác
- **KHÔNG** commit key lên GitHub
- **KHÔNG** để key trong code công khai
- Nếu key bị lộ → Xóa ngay tại: https://platform.openai.com/api-keys

### Giới hạn sử dụng:
- Đặt giới hạn chi tiêu tháng tại: https://platform.openai.com/settings/organization/limits
- Thiết lập alerts khi vượt ngưỡng

## 🆘 Xử lý lỗi thường gặp

### Lỗi: "OpenAI Error 401: Unauthorized"
- **Nguyên nhân**: API key sai hoặc đã bị xóa
- **Giải pháp**: Kiểm tra lại key, tạo key mới nếu cần

### Lỗi: "OpenAI Error 429: Rate limit exceeded"
- **Nguyên nhân**: Gọi API quá nhiều/quá nhanh
- **Giải pháp**: Chờ vài giây rồi thử lại

### Lỗi: "OpenAI Error 402: Payment required"
- **Nguyên nhân**: Hết credit hoặc chưa nạp tiền
- **Giải pháp**: Nạp thêm tiền vào tài khoản

### Lỗi: "OpenAI Error 500: Server error"
- **Nguyên nhân**: OpenAI đang gặp sự cố
- **Giải pháo**: Chuyển về dùng Kie.ai hoặc thử lại sau

## 💡 Mẹo tiết kiệm chi phí

1. **Dùng model phù hợp**: 
   - Bóc băng: `gpt-3.5-turbo` hoặc `gpt-4o-mini`
   - Xào kịch bản: `gpt-4o-mini`
   
2. **Tối ưu prompt**: 
   - Giữ prompt ngắn gọn
   - Không repeat thông tin không cần thiết

3. **Batch processing**: 
   - Xử lý nhiều item cùng lúc nếu có thể

4. **Mix & Match**:
   - Dùng Kie.ai (miễn phí) cho các tác vụ đơn giản
   - Dùng OpenAI cho các tác vụ quan trọng cần chất lượng cao

## 📊 Theo dõi sử dụng

Xem chi tiết usage tại: https://platform.openai.com/usage
- Số request
- Token usage
- Chi phí thực tế

---

**Cập nhật**: 02/05/2026
**Hỗ trợ**: Nếu gặp vấn đề, hãy check logs trong tool hoặc liên hệ admin
