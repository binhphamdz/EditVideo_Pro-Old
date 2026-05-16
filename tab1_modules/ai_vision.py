import os
import base64
from io import BytesIO
import requests
import tkinter as tk
import time
import threading
import subprocess
import tempfile
import shutil
import re
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

    def _format_learning_examples(self, learning_examples):
        if not learning_examples:
            return ""
        lines = []
        for idx, item in enumerate(learning_examples[:4], start=1):
            scene_type = str((item or {}).get("scene_type", "") or "").strip()
            description = str((item or {}).get("description", "") or "").strip()
            if not description:
                continue
            prefix = f"{idx}."
            if scene_type:
                prefix += f" [{scene_type}]"
            lines.append(f"{prefix} {description}")
        return "\n".join(lines)

    def _build_prompt(self, context, hint_text="", vision_mode="fast", product_name="", learning_examples=None):
        # Thiết quân luật: Ép AI nói kỹ về hành động nhưng vẫn ngắn gọn
        base_rule = (
            "QUY TẮC TỐI THƯỢNG: Trả về MÔ TẢ CHI TIẾT hành động trong 1-2 CÂU TIẾNG VIỆT và ĐỘ TIN CẬY. "
            "BẮT BUỘC kể chi tiết: sản phẩm là cái gì, hành động chính là gì, cách thức thực hiện ra sao. "
            "TUYỆT ĐỐI KHÔNG gạch đầu dòng, KHÔNG đánh số, KHÔNG trả lời có/không. "
            "CHỈ mô tả vật thể chính và hành động chính, KHÔNG đoán bừa. "
            "Nếu không chắc về sản phẩm hoặc hành động thì dòng MO_TA ghi đúng: không rõ. "
            "CHỈ xuất ra câu trả lời cuối cùng, KHÔNG giải thích, KHÔNG phân tích, KHÔNG nêu suy nghĩ. "
            "BẮT BUỘC đúng format 3 dòng:\n"
            "MO_TA: <mô tả hoặc không rõ>\n"
            "LOAI_CANH: <can san pham|demo su dung|dong goi|texture|before-after|khac|khong ro>\n"
            "DO_TIN_CAY: <số 0-100>\n\n"
        )

        prompt_parts = []
        if product_name:
            prompt_parts.append(
                f"TÊN SẢN PHẨM CHÍNH: {product_name}\n"
                "Khi ảnh/video có vật thể giống sản phẩm này hoặc giống ảnh mẫu, BẮT BUỘC ưu tiên gọi đúng tên sản phẩm chính này. "
                "Chỉ ghi 'không rõ' nếu thật sự không thấy sản phẩm hoặc hành động."
            )
        if context:
            prompt_parts.append(f"BỐI CẢNH DỰ ÁN: {context}")
        if hint_text:
            prompt_parts.append(
                f"GỢI Ý TỪ Ô MÔ TẢ NGƯỜI DÙNG VỪA NHẬP: {hint_text}\n"
                "Hãy dùng gợi ý này để tham khảo và ưu tiên bám sát nếu nó phù hợp với ảnh/video."
            )
        examples_text = self._format_learning_examples(learning_examples)
        if examples_text:
            prompt_parts.append(
                "VÍ DỤ MÔ TẢ ĐÚNG ĐÃ ĐƯỢC NGƯỜI DÙNG SỬA/LƯU TRONG PROJECT:\n"
                f"{examples_text}\n"
                "Hãy học cách gọi sản phẩm, mức chi tiết và văn phong từ các ví dụ này."
            )

        image_source = "5 ảnh rời theo thứ tự thời gian của cùng một video" if vision_mode == "deep" else "dải 5 khung hình video dưới"
        prompt_parts.append(
            f"Nhiệm vụ: Quan sát {image_source}. BUỘC nêu chi tiết:\n"
            "- SẢN PHẨM: Hàng/loại sản phẩm\n"
            "- HÀNH ĐỘNG: Cụ thể làm cái gì (vd: chuẩn bị, đóng nắp, xoay, rơi...)\n"
            "- CHI TIẾT: Cách thức, tốc độ, kết quả hành động"
        )

        return base_rule + "\n\n".join(prompt_parts)

    def _parse_ai_description_response(self, text):
        raw_text = str(text or "").strip()
        if not raw_text:
            return "", 0

        desc = ""
        scene_type = ""
        confidence = None
        for line in raw_text.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue

            desc_match = re.match(r"^(?:MO_TA|MÔ_TẢ|MO TA|MÔ TẢ|MOTA|DESCRIPTION)\s*[:：]\s*(.+)$", clean_line, re.IGNORECASE)
            if desc_match:
                desc = desc_match.group(1).strip()
                continue

            scene_match = re.match(r"^(?:LOAI_CANH|LOẠI_CẢNH|LOAI CANH|LOẠI CẢNH|SCENE_TYPE)\s*[:：]\s*(.+)$", clean_line, re.IGNORECASE)
            if scene_match:
                scene_type = scene_match.group(1).strip()
                continue

            conf_match = re.match(r"^(?:DO_TIN_CAY|ĐỘ_TIN_CẬY|DO TIN CAY|ĐỘ TIN CẬY|CONFIDENCE)\s*[:：]\s*([0-9]{1,3})", clean_line, re.IGNORECASE)
            if conf_match:
                confidence = max(0, min(100, int(conf_match.group(1))))

        if not desc:
            desc = raw_text
            desc = re.sub(r"(?im)^\s*(?:LOAI_CANH|LOẠI_CẢNH|LOAI CANH|LOẠI CẢNH|SCENE_TYPE)\s*[:：].*$", "", desc).strip()
            desc = re.sub(r"(?im)^\s*(?:DO_TIN_CAY|ĐỘ_TIN_CẬY|DO TIN CAY|ĐỘ TIN CẬY|CONFIDENCE)\s*[:：].*$", "", desc).strip()

        if confidence is None:
            fallback_match = re.search(r"(?:confidence|tin cậy|tin cay)\D+([0-9]{1,3})", raw_text, re.IGNORECASE)
            confidence = max(0, min(100, int(fallback_match.group(1)))) if fallback_match else 0

        return desc.strip(), confidence, self._normalize_scene_type(scene_type)

    def _normalize_scene_type(self, scene_type):
        text = str(scene_type or "").strip().lower()
        mapping = {
            "can san pham": "cận sản phẩm",
            "cận sản phẩm": "cận sản phẩm",
            "demo su dung": "demo sử dụng",
            "demo sử dụng": "demo sử dụng",
            "dong goi": "đóng gói",
            "đóng gói": "đóng gói",
            "texture": "texture",
            "before-after": "before-after",
            "before after": "before-after",
            "khac": "khác",
            "khác": "khác",
            "khong ro": "không rõ",
            "không rõ": "không rõ",
        }
        return mapping.get(text, scene_type.strip() if scene_type else "")

    def _accept_or_report_description(self, project_id, vid_name, task_token, raw_desc, config):
        desc, confidence, scene_type = self._parse_ai_description_response(raw_desc)
        threshold = int(config.get("ai_confidence_threshold", 70) or 70)
        threshold = max(0, min(100, threshold))
        is_unclear = desc.strip().lower() in ("không rõ", "khong ro", "không ro", "khong rõ")

        if desc and confidence >= threshold and not is_unclear:
            if scene_type:
                self.ui.save_ai_broll_metadata(project_id, vid_name, scene_type=scene_type)
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token, d=desc: self.ui._complete_ai_task(pid, v, token, d),
            )
            return

        reason = "không rõ" if is_unclear else f"độ tin cậy {confidence}% dưới ngưỡng {threshold}%"
        message = f"❌ AI chưa đủ chắc ({reason}). Cần soi lại hoặc nhập tay."
        self.ui.main_app.root.after(
            0,
            lambda pid=project_id, v=vid_name, token=task_token, msg=message: self.ui._set_ai_task_error(pid, v, token, msg),
        )

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
                
        target_images = base64_target if isinstance(base64_target, list) else [base64_target]
        content_array.append({"type": "text", "text": prompt + "\n\nĐÂY LÀ ẢNH TỪ VIDEO CẦN MÔ TẢ, THEO ĐÚNG THỨ TỰ THỜI GIAN:"})
        for idx, target_b64 in enumerate(target_images, start=1):
            content_array.append({"type": "text", "text": f"Frame video {idx}:"})
            content_array.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{target_b64}"}})
        
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

        target_images = base64_target if isinstance(base64_target, list) else [base64_target]
        parts.append({"text": prompt + "\n\nĐÂY LÀ ẢNH TỪ VIDEO CẦN MÔ TẢ, THEO ĐÚNG THỨ TỰ THỜI GIAN:"})
        for idx, target_b64 in enumerate(target_images, start=1):
            parts.append({"text": f"Frame video {idx}:"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": target_b64}})

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

    def _get_video_duration(self, video_path):
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            creation_flags = 0x08000000 if os.name == "nt" else 0
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, creationflags=creation_flags)
            return float(out.decode("utf-8").strip())
        except Exception:
            return 0.0

    def _extract_deep_frame_paths(self, video_path):
        duration = self._get_video_duration(video_path)
        if duration <= 0:
            return [], None

        temp_dir = tempfile.mkdtemp(prefix="tab1_ai_frames_")
        timepoints = [duration * ratio for ratio in (0.08, 0.28, 0.5, 0.72, 0.92)]
        frame_paths = []
        creation_flags = 0x08000000 if os.name == "nt" else 0

        for idx, seconds in enumerate(timepoints, start=1):
            out_path = os.path.join(temp_dir, f"frame_{idx}.jpg")
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{seconds:.2f}",
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-q:v",
                "2",
                out_path,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
            if os.path.exists(out_path):
                frame_paths.append(out_path)

        if not frame_paths:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return [], None

        return frame_paths, temp_dir

    def _build_target_images(self, provider, vision_mode, video_path, thumb_path):
        if vision_mode == "deep" and os.path.exists(video_path):
            frame_paths, temp_dir = self._extract_deep_frame_paths(video_path)
            if frame_paths:
                target_images = [self._encode_image_to_base64(path, max_size=768, quality=88) for path in frame_paths]
                return target_images, temp_dir

        if provider == "openai":
            return self._encode_image_to_base64(thumb_path, max_size=768, quality=85), None
        return self._encode_image_to_base64(thumb_path), None

    def _get_provider_model(self, config):
        provider = config.get("ai_provider", "kie")
        if provider == "shopaikey":
            return provider, config.get("gemini_model", "gemini-2.5-flash:generateContent")
        if provider == "kie":
            return provider, config.get("kie_model", "gemini-3-flash")
        return provider, config.get("openai_model", "gpt-4o")

    def _request_vision_text(self, prompt, base64_img, config, provider, model, ref1="", ref2=""):
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

        if not res:
            return "", "Không thể kết nối"
        if res.status_code != 200:
            try:
                error_data = res.json()
                error_msg = error_data.get("error", {}).get("message", f"Lỗi {res.status_code}")
                return "", error_msg[:60]
            except Exception:
                return "", f"Lỗi API {res.status_code}"

        if provider == "shopaikey":
            return self._extract_gemini_text(res.json()), ""
        return self._extract_response(res.json()), ""

    def _build_recognition_prompt(self, context, hint_text="", product_name="", learning_examples=None):
        prompt_parts = [
            "Bạn là bộ nhận diện cảnh video. Chỉ phân tích dữ kiện nhìn thấy, không viết mô tả quảng cáo.",
            "Trả lời ngắn theo đúng 4 dòng:",
            "SAN_PHAM: <tên sản phẩm/vật thể chính hoặc không rõ>",
            "VAT_THE: <các vật thể phụ quan trọng>",
            "HANH_DONG: <hành động đang diễn ra hoặc không rõ>",
            "BANG_CHUNG: <chi tiết hình ảnh làm căn cứ>",
        ]
        if product_name:
            prompt_parts.append(f"SẢN PHẨM CHÍNH CẦN ƯU TIÊN ĐỐI CHIẾU: {product_name}")
        if context:
            prompt_parts.append(f"BỐI CẢNH DỰ ÁN: {context}")
        if hint_text:
            prompt_parts.append(f"GỢI Ý NGƯỜI DÙNG: {hint_text}")
        examples_text = self._format_learning_examples(learning_examples)
        if examples_text:
            prompt_parts.append(f"VÍ DỤ MÔ TẢ ĐÚNG TRONG PROJECT:\n{examples_text}")
        prompt_parts.append("Quan sát 5 frame theo thứ tự thời gian để xác định sản phẩm và hành động chính.")
        return "\n".join(prompt_parts)

    def _build_final_description_prompt(self, recognition_text, context, hint_text="", product_name="", learning_examples=None):
        prompt_parts = [
            "Dựa trên kết quả nhận diện tầng 1 và bối cảnh, hãy viết mô tả cảnh cuối cùng.",
            "BẮT BUỘC đúng format 3 dòng:",
            "MO_TA: <1-2 câu tiếng Việt mô tả sản phẩm + hành động + chi tiết, hoặc không rõ>",
            "LOAI_CANH: <can san pham|demo su dung|dong goi|texture|before-after|khac|khong ro>",
            "DO_TIN_CAY: <số 0-100>",
            "Không giải thích, không gạch đầu dòng ngoài 3 dòng format trên.",
            f"KẾT QUẢ NHẬN DIỆN TẦNG 1:\n{recognition_text}",
        ]
        if product_name:
            prompt_parts.append(f"TÊN SẢN PHẨM CHÍNH: {product_name}")
        if context:
            prompt_parts.append(f"BỐI CẢNH DỰ ÁN: {context}")
        if hint_text:
            prompt_parts.append(f"GỢI Ý NGƯỜI DÙNG: {hint_text}")
        examples_text = self._format_learning_examples(learning_examples)
        if examples_text:
            prompt_parts.append(
                "VÍ DỤ MÔ TẢ ĐÚNG ĐÃ ĐƯỢC NGƯỜI DÙNG SỬA/LƯU TRONG PROJECT:\n"
                f"{examples_text}\n"
                "Hãy học cách gọi sản phẩm, mức chi tiết và văn phong từ các ví dụ này."
            )
        prompt_parts.append("Nếu tầng 1 không đủ chắc về sản phẩm hoặc hành động, MO_TA phải là: không rõ.")
        return "\n\n".join(prompt_parts)

    # =========================================================
    def process_auto_tag(self, project_id, videos_to_tag, config, context="", ref1="", ref2="", vision_mode="fast", product_name=""):
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

            vision_mode = vision_mode if vision_mode in ("fast", "deep") else "fast"

            for vid_name, task_token in videos_to_tag:
                learning_examples = self.ui.get_ai_learning_examples(project_id, exclude_vid_name=vid_name)
                prompt = self._build_prompt(context, vision_mode=vision_mode, product_name=product_name, learning_examples=learning_examples)
                thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
                if not os.path.exists(thumb_path):
                    self.ui.main_app.root.after(
                        0,
                        lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không tìm thấy ảnh bìa!"),
                    )
                    continue
                
                try:
                    video_path = os.path.join(folder, vid_name)
                    temp_dir = None
                    base64_img, temp_dir = self._build_target_images(provider, vision_mode, video_path, thumb_path)

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
                            self._accept_or_report_description(project_id, vid_name, task_token, desc, config)
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

                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
                except Exception as inner_e:
                    if 'temp_dir' in locals() and temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
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
    def process_single_tag(self, project_id, task_token, config, vid_name, context="", ref1="", ref2="", hint_text="", vision_mode="fast", product_name=""):
        try:
            # Lấy provider và model từ config
            provider, model = self._get_provider_model(config)
            
            folder = os.path.join(self.ui.main_app.get_proj_dir(project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")

            thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
            if not os.path.exists(thumb_path): 
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không tìm thấy ảnh bìa!"),
                )
                return

            vision_mode = vision_mode if vision_mode in ("fast", "deep") else "fast"
            learning_examples = self.ui.get_ai_learning_examples(project_id, exclude_vid_name=vid_name)
            prompt = self._build_prompt(context, hint_text, vision_mode, product_name, learning_examples)

            video_path = os.path.join(folder, vid_name)
            temp_dir = None
            base64_img, temp_dir = self._build_target_images(provider, vision_mode, video_path, thumb_path)

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
                    self._accept_or_report_description(project_id, vid_name, task_token, desc, config)
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

            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

        except requests.exceptions.Timeout:
            if 'temp_dir' in locals() and temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"❌ AI Timeout: {vid_name}")
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Timeout - Mạng chậm"),
            )
        except Exception as e: 
            if 'temp_dir' in locals() and temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"❌ Lỗi AI: {e}")
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token, err=str(e)[:20]: self.ui._set_ai_task_error(pid, v, token, f"❌ {err}"),
            )

    def process_single_deep_tag(self, project_id, task_token, config, vid_name, context="", ref1="", ref2="", hint_text="", product_name=""):
        temp_dir = None
        try:
            provider, model = self._get_provider_model(config)
            folder = os.path.join(self.ui.main_app.get_proj_dir(project_id), "Broll")
            thumb_dir = os.path.join(folder, ".thumbnails")
            thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
            video_path = os.path.join(folder, vid_name)

            if not os.path.exists(thumb_path):
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Không tìm thấy ảnh bìa!"),
                )
                return

            base64_img, temp_dir = self._build_target_images(provider, "deep", video_path, thumb_path)

            learning_examples = self.ui.get_ai_learning_examples(project_id, exclude_vid_name=vid_name)
            recognition_prompt = self._build_recognition_prompt(context, hint_text, product_name, learning_examples)
            recognition_text, error_msg = self._request_vision_text(recognition_prompt, base64_img, config, provider, model, ref1, ref2)
            if error_msg or not recognition_text:
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token, msg=(error_msg or "API trả về dữ liệu lỗi"): self.ui._set_ai_task_error(pid, v, token, f"❌ Tầng 1: {msg}"),
                )
                return

            self.ui.save_ai_broll_metadata(project_id, vid_name, recognition_log=recognition_text)

            final_prompt = self._build_final_description_prompt(recognition_text, context, hint_text, product_name, learning_examples)
            final_text, error_msg = self._request_vision_text(final_prompt, base64_img, config, provider, model, ref1, ref2)
            if error_msg or not final_text:
                self.ui.main_app.root.after(
                    0,
                    lambda pid=project_id, v=vid_name, token=task_token, msg=(error_msg or "API trả về dữ liệu lỗi"): self.ui._set_ai_task_error(pid, v, token, f"❌ Tầng 2: {msg}"),
                )
                return

            self._accept_or_report_description(project_id, vid_name, task_token, final_text, config)

        except requests.exceptions.Timeout:
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token: self.ui._set_ai_task_error(pid, v, token, "❌ Timeout - Mạng chậm"),
            )
        except Exception as e:
            print(f"❌ Lỗi AI soi kỹ 2 tầng: {e}")
            self.ui.main_app.root.after(
                0,
                lambda pid=project_id, v=vid_name, token=task_token, err=str(e)[:30]: self.ui._set_ai_task_error(pid, v, token, f"❌ {err}"),
            )
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
