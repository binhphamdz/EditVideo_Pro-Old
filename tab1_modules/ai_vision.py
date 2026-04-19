import os
import base64
from io import BytesIO
import requests
import tkinter as tk
import time
from PIL import Image

class AIVisionHandler:
    def __init__(self, ui_tab):
        self.ui = ui_tab

    def _send_request_with_retry(self, url, headers, data, max_retries=3, timeout=60):
        """Gửi request với retry logic cho timeout"""
        for attempt in range(max_retries):
            try:
                res = requests.post(url, headers=headers, json=data, timeout=timeout)
                return res
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s exponential backoff
                    print(f"⏳ Timeout. Thử lại sau {wait_time}s (lần {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    raise
        return None

    def _extract_response(self, response_data):
        """Trích xuất content từ response một cách an toàn"""
        try:
            if not response_data:
                return None
            
            # Kiểm tra 'choices' key tồn tại
            if "choices" not in response_data:
                print(f"⚠️ Response không có 'choices' key: {response_data}")
                return None
            
            choices = response_data.get("choices", [])
            if not choices or len(choices) == 0:
                print(f"⚠️ 'choices' array rỗng")
                return None
            
            # Lấy message content an toàn
            message = choices[0].get("message", {})
            content = message.get("content", "").strip()
            
            if not content:
                print(f"⚠️ Response content rỗng")
                return None
            
            return content
        except (KeyError, IndexError, TypeError) as e:
            print(f"⚠️ Lỗi parse response: {e}")
            return None

    def _build_prompt(self, context, hint_text=""):
        # Thiết quân luật: Ép AI nói kỹ về hành động nhưng vẫn ngắn gọn
        base_rule = "QUY TẮC TỐI THƯỢNG: Trả về MÔ TẢ CHI TIẾT hành động trong 1-2 CÂU TIẾNG VIỆT. BẮT BUỘC kể chi tiết: sản phẩm là cái gì, hành động chính là gì, cách thức thực hiện ra sao. TUYỆT ĐỐI KHÔNG gạch đầu dòng, KHÔNG đánh số, KHÔNG trả lời có/không.\n\n"

        prompt_parts = []
        if context:
            prompt_parts.append(f"BỐI CẢNH DỰ ÁN: {context}")
        if hint_text:
            prompt_parts.append(
                f"GỢI Ý TỪ Ô MÔ TẢ NGƯỜI DÙNG VỪA NHẬP: {hint_text}\n"
                "Hãy dùng gợi ý này để tham khảo và ưu tiên bám sát nếu nó phù hợp với ảnh/video."
            )

        prompt_parts.append(
            "Nhiệm vụ: Quan sát dải 5 khung hình video dưới. BUỘC nêu chi tiết:\n"
            "- SẢN PHẨM: Hàng/loại sản phẩm\n"
            "- HÀNH ĐỘNG: Cụ thể làm cái gì (vd: chuẩn bị, đóng nắp, xoay, rơi...)\n"
            "- CHI TIẾT: Cách thức, tốc độ, kết quả hành động"
        )

        return base_rule + "\n\n".join(prompt_parts)

    def _encode_image_to_base64(self, image_path):
        """Chuẩn hóa ảnh tham chiếu sang JPEG base64 để hỗ trợ cả WEBP."""
        try:
            with Image.open(image_path) as img:
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    rgba = img.convert("RGBA")
                    background = Image.new("RGB", rgba.size, (255, 255, 255))
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    img = background
                else:
                    img = img.convert("RGB")

                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=95)
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

    def _build_payload(self, prompt, base64_target, ref1="", ref2=""):
        """ Hàm trộn gói dữ liệu: Ghép ảnh mẫu + ảnh video vào 1 mảng """
        content_array = []
        
        # Nếu có ảnh mẫu, nhét ảnh mẫu vào não nó trước
        if (ref1 and os.path.exists(ref1)) or (ref2 and os.path.exists(ref2)):
            content_array.append({"type": "text", "text": "HÃY HỌC THUỘC CÁC ẢNH MẪU SẢN PHẨM SAU ĐỂ ĐỐI CHIẾU:"})
            
            if ref1 and os.path.exists(ref1):
                b64_1 = self._encode_image_to_base64(ref1)
                content_array.append({"type": "text", "text": "Ảnh Mẫu SP 1:"})
                content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_1}"}})
                
            if ref2 and os.path.exists(ref2):
                b64_2 = self._encode_image_to_base64(ref2)
                content_array.append({"type": "text", "text": "Ảnh Mẫu SP 2:"})
                content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_2}"}})
                
        # Cuối cùng mới nhét lệnh và ảnh Video vào để nó xử lý
        content_array.append({"type": "text", "text": prompt + "\n\nĐÂY LÀ DẢI ẢNH TỪ VIDEO CẦN MÔ TẢ:"})
        content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_target}"}})
        
        return {
            "model": "gemini-2.5-flash", 
            "messages": [{"role": "user", "content": content_array}], 
            "temperature": 0.2 # Nhiệt độ thấp để nhận diện cực chính xác
        }

    # =========================================================
    def process_auto_tag(self, project_id, videos_to_tag, kie_key, context="", ref1="", ref2=""):
        try:
            folder = os.path.join(self.ui.main_app.get_proj_dir(project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")
            url_kie = "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions"

            prompt = self._build_prompt(context)

            for vid_name, task_token in videos_to_tag:
                thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
                if not os.path.exists(thumb_path):
                    self.ui.main_app.root.after(
                        0,
                        lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không tìm thấy ảnh bìa!"),
                    )
                    continue
                
                try:
                    with open(thumb_path, "rb") as img_file: 
                        base64_img = base64.b64encode(img_file.read()).decode('utf-8')
                        
                    payload = self._build_payload(prompt, base64_img, ref1, ref2)
                    headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
                    res = self._send_request_with_retry(url_kie, headers, payload, max_retries=3, timeout=60)
                    
                    if res and res.status_code == 200:
                        desc = self._extract_response(res.json())
                        if desc:
                            self.ui.main_app.root.after(
                                0,
                                lambda pid=project_id, v=vid_name, token=task_token, d=desc: self.ui._complete_ai_task(pid, v, token, d),
                            )
                        else:
                            self.ui.main_app.root.after(
                                0,
                                lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ API trả về dữ liệu lỗi"),
                            )
                    elif res:
                        self.ui.main_app.root.after(
                            0,
                            lambda pid=project_id, v=vid_name, token=task_token, s=res.status_code: self.ui._set_ai_task_error(pid, v, token, f"❌ Lỗi API: {s}"),
                        )
                    else:
                        self.ui.main_app.root.after(
                            0,
                            lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không thể kết nối"),
                        )
                        
                except Exception as inner_e:
                    print(f"❌ Lỗi xử lý video {vid_name}: {inner_e}")
                    self.ui.main_app.root.after(
                        0,
                        lambda pid=project_id, v=vid_name, token=task_token, e=str(inner_e)[:30]: self.ui._set_ai_task_error(pid, v, token, f"❌ {e}"),
                    )
                    continue
            
        except Exception as e: 
            print(f"❌ Lỗi Auto Tag: {e}")
        finally: 
            self.ui.main_app.root.after(0, lambda: self.ui.btn_auto_tag.config(state="normal", text="🧠 AI TỰ NHÌN & ĐIỀN", bg="#d35400"))

    # =========================================================
    def process_single_tag(self, project_id, task_token, kie_key, vid_name, context="", ref1="", ref2="", hint_text=""):
        try:
            folder = os.path.join(self.ui.main_app.get_proj_dir(project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")
            url_kie = "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions"

            thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
            if not os.path.exists(thumb_path): 
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không tìm thấy ảnh bìa!"),
                )
                return

            prompt = self._build_prompt(context, hint_text)

            with open(thumb_path, "rb") as img_file: 
                base64_img = base64.b64encode(img_file.read()).decode('utf-8')
                
            payload = self._build_payload(prompt, base64_img, ref1, ref2)
            headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
            
            # Retry logic: thử 3 lần với timeout 60s
            res = self._send_request_with_retry(url_kie, headers, payload, max_retries=3, timeout=60)
            
            if res and res.status_code == 200:
                desc = self._extract_response(res.json())
                if desc:
                    self.ui.main_app.root.after(
                        0,
                        lambda pid=project_id, v=vid_name, token=task_token, d=desc: self.ui._complete_ai_task(pid, v, token, d),
                    )
                else:
                    self.ui.main_app.root.after(
                        0,
                        lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ API trả về dữ liệu lỗi"),
                    )
            elif res:
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token, s=res.status_code: self.ui._set_ai_task_error(pid, v, token, f"❌ Lỗi: {s}"),
                )
            else:
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Mất kết nối"),
                )

        except requests.exceptions.Timeout:
            print(f"❌ AI Timeout: {vid_name}")
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Timeout - Mạng chậm"),
            )
        except Exception as e: 
            print(f"❌ Lỗi AI: {e}")
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token, err=str(e)[:20]: self.ui._set_ai_task_error(pid, v, token, f"❌ {err}"),
            )