"""
Script test OpenAI Vision API
Dùng để kiểm tra API key và kết nối trước khi dùng trong app chính
"""
import requests
import base64
import json
import os

# ===== CẤU HÌNH =====
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = "gpt-4o-mini"  # hoặc "gpt-4o", "gpt-4-turbo"
IMAGE_PATH = None  # Để None để test với ảnh mẫu từ OpenAI

def test_openai_vision():
    """Test kết nối với OpenAI Vision API"""
    if not API_KEY:
        print("❌ Chưa cấu hình OPENAI_API_KEY trong biến môi trường")
        return False
    
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    # Sử dụng ảnh test từ OpenAI docs
    if IMAGE_PATH:
        with open(IMAGE_PATH, "rb") as img_file:
            base64_image = base64.b64encode(img_file.read()).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_image}"
    else:
        # Dùng ảnh mẫu từ internet
        image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
    
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Mô tả chi tiết bức ảnh này bằng tiếng Việt trong 1-2 câu."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300,
        "temperature": 0.2
    }
    
    print("=" * 60)
    print("🧪 TESTING OPENAI VISION API")
    print("=" * 60)
    print(f"📍 URL: {url}")
    print(f"🤖 Model: {MODEL}")
    print("🔑 API Key: Đã đọc từ biến môi trường OPENAI_API_KEY")
    print(f"🖼️  Image: {'Local file' if IMAGE_PATH else 'Sample URL'}")
    print("=" * 60)
    print("\n⏳ Đang gửi request...\n")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}\n")
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            print("✅ THÀNH CÔNG!")
            print("=" * 60)
            print("📝 Response:")
            print(content)
            print("=" * 60)
            
            # Hiển thị usage info
            if "usage" in data:
                usage = data["usage"]
                print(f"\n💰 Token Usage:")
                print(f"   - Prompt tokens: {usage.get('prompt_tokens', 0)}")
                print(f"   - Completion tokens: {usage.get('completion_tokens', 0)}")
                print(f"   - Total tokens: {usage.get('total_tokens', 0)}")
                
                # Ước tính chi phí (giá tham khảo)
                if MODEL == "gpt-4o":
                    cost_input = usage.get('prompt_tokens', 0) * 0.005 / 1000
                    cost_output = usage.get('completion_tokens', 0) * 0.015 / 1000
                elif MODEL == "gpt-4o-mini":
                    cost_input = usage.get('prompt_tokens', 0) * 0.00015 / 1000
                    cost_output = usage.get('completion_tokens', 0) * 0.0006 / 1000
                else:
                    cost_input = cost_output = 0
                
                total_cost = cost_input + cost_output
                print(f"   - Ước tính chi phí: ${total_cost:.6f} (~{total_cost * 24000:.2f} VNĐ)")
            
            return True
            
        else:
            print("❌ LỖI!")
            print("=" * 60)
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {})
                print(f"📛 Error Type: {error_msg.get('type', 'Unknown')}")
                print(f"📛 Error Message: {error_msg.get('message', response.text)}")
                print(f"📛 Error Code: {error_msg.get('code', 'N/A')}")
            except:
                print(f"📛 Raw Response: {response.text}")
            print("=" * 60)
            
            # Gợi ý khắc phục
            print("\n💡 GỢI Ý KHẮC PHỤC:")
            if response.status_code == 401:
                print("   - API Key không hợp lệ hoặc đã hết hạn")
                print("   - Kiểm tra lại key tại: https://platform.openai.com/api-keys")
            elif response.status_code == 429:
                print("   - Vượt quá giới hạn tốc độ (rate limit)")
                print("   - Đợi 1 phút rồi thử lại")
                print("   - Hoặc nâng cấp plan: https://platform.openai.com/account/billing")
            elif response.status_code == 400:
                print("   - Request format sai")
                print("   - Kiểm tra model có hỗ trợ vision không")
            elif response.status_code == 403:
                print("   - Tài khoản chưa nạp tiền hoặc hết quota")
                print("   - Nạp tiền tại: https://platform.openai.com/account/billing")
            
            return False
            
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT - Request quá lâu (>60s)")
        print("   - Kiểm tra kết nối mạng")
        print("   - Thử lại sau ít phút")
        return False
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ LỖI KẾT NỐI: {str(e)[:100]}")
        print("   - Kiểm tra internet")
        print("   - Kiểm tra firewall/proxy")
        return False
        
    except Exception as e:
        print(f"❌ LỖI KHÔNG XÁC ĐỊNH: {str(e)}")
        return False

if __name__ == "__main__":
    # Đọc model từ config nếu có; API key luôn lấy từ biến môi trường.
    try:
        import json
        with open("config_dao_dien.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            MODEL = config.get("openai_model", MODEL)
    except:
        pass
    
    success = test_openai_vision()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 API KEY HOẠT ĐỘNG BÌNH THƯỜNG!")
        print("   → Bạn có thể sử dụng OpenAI trong app")
    else:
        print("⚠️  CÓ VẤN ĐỀ VỚI API KEY")
        print("   → Xem gợi ý khắc phục ở trên")
    print("=" * 60)
