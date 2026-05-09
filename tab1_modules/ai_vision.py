import os
import base64
from io import BytesIO
import requests
import tkinter as tk
import time
import threading
from PIL import Image

class AIVisionHandler:
    def __init__(self, ui_tab):
        self.ui = ui_tab

    def _extract_gemini_text(self, response_data):
        try:
            candidates = response_data.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            return parts[0].get("text", "").strip() if parts else ""
        except (KeyError, IndexError, TypeError, AttributeError):
            return ""

    def _estimate_openai_cost(self, model, usage):
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        pricing = {
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03}
        }
        rates = pricing.get(model)
        if not rates:
            return None
        return (prompt_tokens / 1000.0) * rates["input"] + (completion_tokens / 1000.0) * rates["output"]

    def _log_openai_usage(self, model, usage):
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        est_cost = self._estimate_openai_cost(model, usage)
        cost_text = f" (~${est_cost:.6f})" if est_cost is not None else ""
        msg = f"OpenAI vision usage - prompt: {prompt_tokens}, completion: {completion_tokens}, total: {total_tokens}{cost_text}"
        try:
            if hasattr(self.ui, "add_log") and self.ui.main_app.root.winfo_exists():
                self.ui.main_app.root.after(0, lambda: self.ui.add_log(msg, provider="openai"))
            else:
                print(msg)
        except (RuntimeError, AttributeError, tk.TclError):
            print(msg)

    def _log_shopaikey_usage(self, api_key):
        try:
            url = "https://api.shopaikey.com/usage/histories"
            headers = {"x-api-key": api_key}
            payload = {"page": 1, "page_size": 1}
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if res.status_code != 200:
                return
            data = res.json() or {}
            items = (((data.get("data") or {}).get("items")) or [])
            if not items:
                return
            item = items[0]
            prompt_tokens = item.get("prompt_tokens", 0)
            completion_tokens = item.get("completion_tokens", 0)
            cost = item.get("cost", 0)
            model_name = item.get("model_name", "")
            msg = (
                f"ShopAIKey vision usage - prompt: {prompt_tokens}, "
                f"completion: {completion_tokens}, cost: ${cost}"
            )
            if model_name:
                msg += f", model: {model_name}"
            if hasattr(self.ui, "add_log") and self.ui.main_app.root.winfo_exists():
                self.ui.main_app.root.after(0, lambda: self.ui.add_log(msg, provider="shopaikey"))
            else:
                print(msg)
        except Exception:
            pass
    
    def _call_vision_api(self, payload, config, provider="kie", model="gpt-4o"):
        """
        Universal vision API caller - hỗ trợ Kie.ai, OpenAI và ShopAIKey Gemini
        """
        import requests
        import time
        
        if provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            api_key = config.get("openai_key", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            # Đảm bảo model hỗ trợ vision
            if model not in ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]:
                model = "gpt-4o"  # Fallback to gpt-4o if model doesn't support vision
            payload["model"] = model
        elif provider == "shopaikey":
            url = f"https://api.shopaikey.com/v1beta/models/{model}"
            api_key = config.get("shopaikey_key", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        else:  # kie.ai
            url = "https://api.kie.ai/gemini-3-flash/v1/chat/completions"
            api_key = config.get("kie_key", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload["model"] = model
        
        try:
            res = self._send_request_with_retry(url, headers, payload, max_retries=3, timeout=90)

            if provider == "openai" and res and res.status_code == 200:
                try:
                    usage = res.json().get("usage")
                    if usage:
                        self._log_openai_usage(payload.get("model", model), usage)
                except Exception:
                    pass

            if provider == "shopaikey" and res and res.status_code == 200:
                threading.Thread(target=self._log_shopaikey_usage, args=(api_key,), daemon=True).start()
            
            # Log chi tiết nếu có lỗi
            if res and res.status_code != 200:
                try:
                    error_data = res.json()
                    error_msg = error_data.get("error", {}).get("message", res.text[:200])
                    print(f"❌ {provider.upper()} API Error {res.status_code}: {error_msg}")
                except:
                    print(f"❌ {provider.upper()} API Error {res.status_code}: {res.text[:200]}")
            
            return res
        except Exception as e:
            print(f"❌ Exception khi gọi {provider.upper()} API: {str(e)}")
            return None

    def _send_request_with_retry(self, url, headers, data, max_retries=3, timeout=90):
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
                    print(f"❌ Timeout sau {max_retries} lần thử")
                    raise
            except requests.exceptions.ConnectionError as e:
                print(f"❌ Lỗi kết nối: {str(e)[:100]}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⏳ Thử lại sau {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                print(f"❌ Request error: {str(e)[:100]}")
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
        base_rule = (
            "QUY TẮC TỐI THƯỢNG: Trả về MÔ TẢ CHI TIẾT hành động trong 1-2 CÂU TIẾNG VIỆT. "
            "BẮT BUỘC kể chi tiết: sản phẩm là cái gì, hành động chính là gì, cách thức thực hiện ra sao. "
            "TUYỆT ĐỐI KHÔNG gạch đầu dòng, KHÔNG đánh số, KHÔNG trả lời có/không. "
            "CHỈ mô tả vật thể chính và hành động chính, KHÔNG đoán bừa. "
            "Nếu không chắc về sản phẩm hoặc hành động thì trả đúng một cụm: \"không rõ\". "
            "CHỈ xuất ra câu trả lời cuối cùng, KHÔNG giải thích, KHÔNG phân tích, KHÔNG nêu suy nghĩ.\n\n"
        )

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

    def _encode_image_to_base64(self, image_path, max_size=None, quality=95):
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

                if max_size:
                    img.thumbnail((max_size, max_size), Image.LANCZOS)

                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=quality)
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

    def _build_payload(self, prompt, base64_target, ref1="", ref2="", provider="kie"):
        """ Hàm trộn gói dữ liệu: Ghép ảnh mẫu + ảnh video vào 1 mảng """
        content_array = []
        
        # Nếu có ảnh mẫu, nhét ảnh mẫu vào não nó trước
        if (ref1 and os.path.exists(ref1)) or (ref2 and os.path.exists(ref2)):
            content_array.append({"type": "text", "text": "HÃY HỌC THUỘC CÁC ẢNH MẪU SẢN PHẨM SAU ĐỂ ĐỐI CHIẾU:"})
            
            if ref1 and os.path.exists(ref1):
                if provider == "openai":
                    b64_1 = self._encode_image_to_base64(ref1, max_size=768, quality=85)
                else:
                    b64_1 = self._encode_image_to_base64(ref1)
                content_array.append({"type": "text", "text": "Ảnh Mẫu SP 1:"})
                content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_1}"}})
                
            if ref2 and os.path.exists(ref2):
                if provider == "openai":
                    b64_2 = self._encode_image_to_base64(ref2, max_size=768, quality=85)
                else:
                    b64_2 = self._encode_image_to_base64(ref2)
                content_array.append({"type": "text", "text": "Ảnh Mẫu SP 2:"})
                content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_2}"}})
                
        # Cuối cùng mới nhét lệnh và ảnh Video vào để nó xử lý
        content_array.append({"type": "text", "text": prompt + "\n\nĐÂY LÀ DẢI ẢNH TỪ VIDEO CẦN MÔ TẢ:"})
        content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_target}"}})
        
        return {
            # Model sẽ được set bởi _call_vision_api dựa trên provider
            "messages": [{"role": "user", "content": content_array}], 
            "temperature": 0.2,  # Nhiệt độ thấp để nhận diện cực chính xác
            "max_tokens": 300  # Giới hạn output để tiết kiệm cost
        }

    def _build_gemini_payload(self, prompt, base64_target, ref1_b64="", ref2_b64=""):
        parts = []
        if ref1_b64:
            parts.append({"text": "Ảnh Mẫu SP 1:"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": ref1_b64}})
        if ref2_b64:
            parts.append({"text": "Ảnh Mẫu SP 2:"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": ref2_b64}})

        parts.append({"text": prompt + "\n\nĐÂY LÀ DẢI ẢNH TỪ VIDEO CẦN MÔ TẢ:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64_target}})

        return {
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
            "generationConfig": {
                "temperature": 0.2
            }
        }

    # =========================================================
    def process_auto_tag(self, project_id, videos_to_tag, config, context="", ref1="", ref2=""):
        try:
            # Lấy provider và model từ config
            provider = config.get("ai_provider", "kie")
            if provider == "shopaikey":
                model = config.get("gemini_model", "gemini-2.5-flash:generateContent")
            elif provider == "kie":
                model = config.get("kie_model", "gemini-3-flash")
            else:
                model = config.get("openai_model", "gpt-4o")
            
            folder = os.path.join(self.ui.main_app.get_proj_dir(project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")

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
                    if provider == "openai":
                        base64_img = self._encode_image_to_base64(thumb_path, max_size=768, quality=85)
                    else:
                        base64_img = self._encode_image_to_base64(thumb_path)

                    if provider == "shopaikey":
                        ref1_b64 = self._encode_image_to_base64(ref1, max_size=768, quality=85) if ref1 and os.path.exists(ref1) else ""
                        ref2_b64 = self._encode_image_to_base64(ref2, max_size=768, quality=85) if ref2 and os.path.exists(ref2) else ""
                        payload = self._build_gemini_payload(prompt, base64_img, ref1_b64, ref2_b64)
                    else:
                        payload = self._build_payload(prompt, base64_img, ref1, ref2, provider)
                    res = None
                    for attempt in range(3):
                        res = self._call_vision_api(payload, config, provider, model)
                        if res is not None:
                            break
                        if attempt < 2:
                            time.sleep(1)
                    
                    if res and res.status_code == 200:
                        if provider == "shopaikey":
                            desc = self._extract_gemini_text(res.json())
                        else:
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
                        # Lấy thông báo lỗi cụ thể từ API response
                        try:
                            error_data = res.json()
                            error_msg = error_data.get("error", {}).get("message", f"Lỗi {res.status_code}")
                            error_msg = error_msg[:50]  # Giới hạn độ dài
                        except:
                            error_msg = f"Lỗi API {res.status_code}"
                        
                        self.ui.main_app.root.after(
                            0,
                            lambda pid=project_id, v=vid_name, token=task_token, msg=error_msg: self.ui._set_ai_task_error(pid, v, token, f"❌ {msg}"),
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
            def _restore_buttons():
                if hasattr(self.ui, "btn_auto_tag"):
                    self.ui.btn_auto_tag.config(state="normal", text="🧠 AI TỰ NHÌN & ĐIỀN", bg="#d35400")
                if hasattr(self.ui, "btn_auto_tag_page"):
                    self.ui.btn_auto_tag_page.config(state="normal", text="📄 AI SOI TRANG", bg="#e67e22")
            self.ui.main_app.root.after(0, _restore_buttons)

    # =========================================================
    def process_single_tag(self, project_id, task_token, config, vid_name, context="", ref1="", ref2="", hint_text=""):
        try:
            # Lấy provider và model từ config
            provider = config.get("ai_provider", "kie")
            if provider == "shopaikey":
                model = config.get("gemini_model", "gemini-2.5-flash:generateContent")
            elif provider == "kie":
                model = config.get("kie_model", "gemini-3-flash")
            else:
                model = config.get("openai_model", "gpt-4o")
            
            folder = os.path.join(self.ui.main_app.get_proj_dir(project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")

            thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
            if not os.path.exists(thumb_path): 
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không tìm thấy ảnh bìa!"),
                )
                return

            prompt = self._build_prompt(context, hint_text)

            if provider == "openai":
                base64_img = self._encode_image_to_base64(thumb_path, max_size=768, quality=85)
            else:
                base64_img = self._encode_image_to_base64(thumb_path)

            if provider == "shopaikey":
                ref1_b64 = self._encode_image_to_base64(ref1, max_size=768, quality=85) if ref1 and os.path.exists(ref1) else ""
                ref2_b64 = self._encode_image_to_base64(ref2, max_size=768, quality=85) if ref2 and os.path.exists(ref2) else ""
                payload = self._build_gemini_payload(prompt, base64_img, ref1_b64, ref2_b64)
            else:
                payload = self._build_payload(prompt, base64_img, ref1, ref2, provider)
            
            res = None
            for attempt in range(3):
                res = self._call_vision_api(payload, config, provider, model)
                if res is not None:
                    break
                if attempt < 2:
                    time.sleep(1)
            
            if res and res.status_code == 200:
                if provider == "shopaikey":
                    desc = self._extract_gemini_text(res.json())
                else:
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
                # Lấy thông báo lỗi cụ thể từ API
                try:
                    error_data = res.json()
                    error_msg = error_data.get("error", {}).get("message", f"Lỗi {res.status_code}")
                    # Rút gọn thông báo lỗi
                    if "invalid_api_key" in error_msg.lower():
                        error_msg = "API Key không hợp lệ"
                    elif "quota" in error_msg.lower():
                        error_msg = "Hết quota API"
                    elif "rate_limit" in error_msg.lower():
                        error_msg = "Vượt giới hạn tốc độ"
                    else:
                        error_msg = error_msg[:60]  # Giới hạn 60 ký tự
                except:
                    error_msg = f"Lỗi API {res.status_code}"
                
                print(f"❌ Chi tiết lỗi: {error_msg}")
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token, msg=error_msg: self.ui._set_ai_task_error(pid, v, token, f"❌ {msg}"),
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