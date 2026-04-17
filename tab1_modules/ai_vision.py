import os
import base64
import requests
import tkinter as tk
import time

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

    def _build_prompt(self, context):
        # Thiết quân luật: Ép AI nói kỹ về hành động nhưng vẫn ngắn gọn
        base_rule = "QUY TẮC TỐI THƯỢNG: Trả về MÔ TẢ CHI TIẾT hành động trong 1-2 CÂU TIẾNG VIỆT. BẮT BUỘC kể chi tiết: sản phẩm là cái gì, hành động chính là gì, cách thức thực hiện ra sao. TUYỆT ĐỐI KHÔNG gạch đầu dòng, KHÔNG đánh số, KHÔNG trả lời có/không.\n\n"
        
        if context:
            return base_rule + f"BỐI CẢNH DỰ ÁN: {context}\n\nNhiệm vụ: Quan sát dải 5 khung hình video dưới. BUỘC nêu chi tiết:\n- SẢN PHẨM: Hàng/loại sản phẩm\n- HÀNH ĐỘNG: Cụ thể làm cái gì (vd: chuẩn bị, đóng nắp, xoay, rơi...)\n- CHI TIẾT: Cách thức, tốc độ, kết quả hành động"
        else:
            return base_rule + "Nhiệm vụ: Quan sát dải 5 khung hình video. BUỘC nêu chi tiết:\n- SẢN PHẨM: Hàng/loại sản phẩm\n- HÀNH ĐỘNG: Cụ thể làm cái gì (vd: chuẩn bị, đóng nắp, xoay, rơi...)\n- CHI TIẾT: Cách thức, tốc độ, kết quả hành động"

    def _build_payload(self, prompt, base64_target, ref1="", ref2=""):
        """ Hàm trộn gói dữ liệu: Ghép ảnh mẫu + ảnh video vào 1 mảng """
        content_array = []
        
        # Nếu có ảnh mẫu, nhét ảnh mẫu vào não nó trước
        if (ref1 and os.path.exists(ref1)) or (ref2 and os.path.exists(ref2)):
            content_array.append({"type": "text", "text": "HÃY HỌC THUỘC CÁC ẢNH MẪU SẢN PHẨM SAU ĐỂ ĐỐI CHIẾU:"})
            
            if ref1 and os.path.exists(ref1):
                with open(ref1, "rb") as f: b64_1 = base64.b64encode(f.read()).decode('utf-8')
                content_array.append({"type": "text", "text": "Ảnh Mẫu SP 1:"})
                content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_1}"}})
                
            if ref2 and os.path.exists(ref2):
                with open(ref2, "rb") as f: b64_2 = base64.b64encode(f.read()).decode('utf-8')
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
    def process_auto_tag(self, kie_key, context="", ref1="", ref2=""):
        try:
            folder = os.path.join(self.ui.main_app.get_proj_dir(self.ui.current_project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")
            url_kie = "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions"

            videos_to_tag = [(v, t) for v, t in self.ui.desc_entries.items() if not t.get("1.0", tk.END).strip()]
            prompt = self._build_prompt(context)

            for vid_name, txt_widget in videos_to_tag:
                thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
                if not os.path.exists(thumb_path): continue
                    
                self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "⏳ AI đang soi ảnh (kèm mẫu)...")))
                
                try:
                    with open(thumb_path, "rb") as img_file: 
                        base64_img = base64.b64encode(img_file.read()).decode('utf-8')
                        
                    payload = self._build_payload(prompt, base64_img, ref1, ref2)
                    headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
                    res = self._send_request_with_retry(url_kie, headers, payload, max_retries=3, timeout=60)
                    
                    if res and res.status_code == 200:
                        desc = self._extract_response(res.json())
                        if desc:
                            self.ui.main_app.root.after(0, lambda w=txt_widget, d=desc: (w.delete("1.0", tk.END), w.insert("1.0", d)))
                        else:
                            self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "❌ API trả về dữ liệu lỗi")))
                    elif res:
                        self.ui.main_app.root.after(0, lambda w=txt_widget, s=res.status_code: (w.delete("1.0", tk.END), w.insert("1.0", f"❌ Lỗi API: {s}")))
                    else:
                        self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "❌ Không thể kết nối")))
                        
                except Exception as inner_e:
                    print(f"❌ Lỗi xử lý video {vid_name}: {inner_e}")
                    self.ui.main_app.root.after(0, lambda w=txt_widget, e=str(inner_e)[:30]: (w.delete("1.0", tk.END), w.insert("1.0", f"❌ {e}")))
                    continue

            self.ui.main_app.root.after(0, self.ui.save_all_descriptions)
            
        except Exception as e: 
            print(f"❌ Lỗi Auto Tag: {e}")
        finally: 
            self.ui.main_app.root.after(0, lambda: self.ui.btn_auto_tag.config(state="normal", text="🧠 AI SOI (ALL)", bg="#d35400"))

    # =========================================================
    def process_single_tag(self, kie_key, vid_name, context="", ref1="", ref2=""):
        try:
            folder = os.path.join(self.ui.main_app.get_proj_dir(self.ui.current_project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")
            url_kie = "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions"

            if vid_name not in self.ui.desc_entries: return
            txt_widget = self.ui.desc_entries[vid_name]

            thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
            if not os.path.exists(thumb_path): 
                self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "❌ Không tìm thấy ảnh bìa!")))
                return

            prompt = self._build_prompt(context)
            self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "⏳ AI đang soi... Chút xíu nhé!")))

            with open(thumb_path, "rb") as img_file: 
                base64_img = base64.b64encode(img_file.read()).decode('utf-8')
                
            payload = self._build_payload(prompt, base64_img, ref1, ref2)
            headers = {"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"}
            
            # Retry logic: thử 3 lần với timeout 60s
            res = self._send_request_with_retry(url_kie, headers, payload, max_retries=3, timeout=60)
            
            if res and res.status_code == 200:
                desc = self._extract_response(res.json())
                if desc:
                    self.ui.main_app.root.after(0, lambda w=txt_widget, d=desc: (w.delete("1.0", tk.END), w.insert("1.0", d)))
                    self.ui.main_app.root.after(0, self.ui.save_all_descriptions)
                else:
                    self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "❌ API trả về dữ liệu lỗi")))
            elif res:
                self.ui.main_app.root.after(0, lambda w=txt_widget, s=res.status_code: (w.delete("1.0", tk.END), w.insert("1.0", f"❌ Lỗi: {s}")))
            else:
                self.ui.main_app.root.after(0, lambda w=txt_widget: (w.delete("1.0", tk.END), w.insert("1.0", "❌ Mất kết nối")))

        except requests.exceptions.Timeout:
            print(f"❌ AI Timeout: {vid_name}")
            if vid_name in self.ui.desc_entries:
                self.ui.main_app.root.after(0, lambda w=self.ui.desc_entries[vid_name]: (w.delete("1.0", tk.END), w.insert("1.0", "❌ Timeout - Mạng chậm")))
        except Exception as e: 
            print(f"❌ Lỗi AI: {e}")
            if vid_name in self.ui.desc_entries:
                self.ui.main_app.root.after(0, lambda w=self.ui.desc_entries[vid_name], err=str(e)[:20]: (w.delete("1.0", tk.END), w.insert("1.0", f"❌ {err}")))