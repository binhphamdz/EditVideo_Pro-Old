import requests
import threading
import tkinter as tk  # <--- CHÚ Ý: Bổ sung thư viện này để bắt lỗi giao diện

class KieAIHandler:
    def __init__(self, ui_tab):
        self.ui = ui_tab
        # Danh sách các models OpenAI có sẵn
        self.openai_models = [
            "gpt-4o",
            "gpt-4o-mini", 
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k"
        ]

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

    def _log_openai_usage(self, model, usage, task_type):
        try:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            est_cost = self._estimate_openai_cost(model, usage)
            cost_text = f" (~${est_cost:.6f})" if est_cost is not None else ""
            msg = f"OpenAI usage [{task_type}] - prompt: {prompt_tokens}, completion: {completion_tokens}, total: {total_tokens}{cost_text}"
            if self.ui.main_app.root.winfo_exists():
                self.ui.main_app.root.after(0, lambda: self.ui.add_log(msg, provider="openai"))
        except (RuntimeError, AttributeError, tk.TclError):
            pass

    def _log_shopaikey_usage(self, api_key, task_type):
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
                f"ShopAIKey usage [{task_type}] - prompt: {prompt_tokens}, "
                f"completion: {completion_tokens}, cost: ${cost}"
            )
            if model_name:
                msg += f", model: {model_name}"
            if self.ui.main_app.root.winfo_exists():
                self.ui.main_app.root.after(0, lambda: self.ui.add_log(msg, provider="shopaikey"))
        except Exception:
            pass

    def extract_info_and_keys(self, orig_text, api_key, provider="kie", model="gpt-4o"):
        """
        Trích xuất thông tin sản phẩm và keys
        provider: "kie" hoặc "openai"
        model: model name (chỉ dùng khi provider="openai")
        """
        threading.Thread(target=self._get_product_info, args=(api_key, orig_text, provider, model), daemon=True).start()
        threading.Thread(target=self._get_keys, args=(api_key, orig_text, provider, model), daemon=True).start()

    def _get_product_info(self, api_key, orig_text, provider="kie", model="gpt-4o"):
        prompt = f"""Phân tích voice và trích xuất THÔNG TIN SẢN PHẨM thô.
Yêu cầu:
- Chỉ liệt kê các thông số, tính năng, tên gọi cụ thể.
- Tuyệt đối KHÔNG viết câu dẫn (Dưới đây là...), KHÔNG chia nhóm, KHÔNG viết dài dòng.
- Mỗi thông tin là một dòng ngắn gọn (dưới 15 chữ).

Đoạn voice:
{orig_text}"""
        self._call_api(api_key, prompt, "prod_info", provider, model)

    def _get_keys(self, api_key, orig_text, provider="kie", model="gpt-4o"):
        prompt = f"""Phân tích voice và lấy ra 10 ý chính (key content) để làm video.
Yêu cầu:
- Chỉ lấy nội dung mô tả cốt lõi nhất của ý đó.
- Tuyệt đối KHÔNG ghi 'Tên key', KHÔNG ghi 'Hook', KHÔNG đánh số.
- Mỗi ý là một dòng duy nhất, ngắn gọn, súc tích. Trả về đúng 10 dòng.

Đây là đoạn voice:
{orig_text}"""
        self._call_api(api_key, prompt, "keys", provider, model)

    def spin_script_ai(self, orig_text, system_prompt, product_info, keys_text, selected_hook, api_key, provider="kie", model="gpt-4o"):
        """
        Xào nấu kịch bản với AI
        provider: "kie" hoặc "openai"
        model: model name (chỉ dùng khi provider="openai")
        """
        style_transfer = (
            "YÊU CẦU CHUYỂN HÓA PHONG CÁCH:\n"
            "- Phân tích phong cách của kịch bản gốc (đối thủ): nhịp câu, giọng điệu, cách mở/đóng.\n"
            "- Viết lại theo phong cách của mình trong Lệnh Xào Nấu, không sao chép câu chữ.\n"
            "- Giữ ý chính và độ dài tương đương, không nhắc đến đối thủ."
        )
        hook_instruction = ""
        if selected_hook:
            hook_instruction = f"\n\n--- 🔥 MỆNH LỆNH TỐI CAO: DÙNG Ý SAU LÀM HOOK MỞ ĐẦU (ĐẨY LÊN ĐẦU VIDEO) ---\n[{selected_hook}]\n(Hãy dùng ý này để giật tít, gây chú ý ngay giây đầu tiên, sau đó mới dẫn vào các phần khác)."

        user_content = f"--- THÔNG TIN SẢN PHẨM ---\n{product_info}\n\n--- CÁC Ý CHÍNH ---\n{keys_text}{hook_instruction}\n\n--- KỊCH BẢN GỐC ---\n{orig_text}"
        
        final_prompt = system_prompt + "\n\n" + style_transfer + "\n\n" + user_content

        # ĐÃ FIX: Cho lệnh gọi API vào chạy luồng ngầm để tool không bị đơ "Not Responding"
        threading.Thread(target=self._call_api, args=(api_key, final_prompt, "spun", provider, model), daemon=True).start()

    def _call_api(self, api_key, prompt, task_type, provider="kie", model="gpt-4o"):
        """
        Gọi API theo provider được chọn
        provider: "kie", "openai" hoặc "shopaikey"
        model: tên model (dùng cho OpenAI hoặc ShopAIKey)
        """
        if provider == "openai":
            self._call_openai_api(api_key, prompt, task_type, model)
        elif provider == "shopaikey":
            self._call_shopaikey_gemini_api(api_key, prompt, task_type, model)
        else:
            self._call_kie_api_direct(api_key, prompt, task_type, model)

    def _call_shopaikey_gemini_api(self, api_key, prompt, task_type, model="gemini-2.5-flash:generateContent"):
        """Gọi ShopAIKey Gemini Flash (proxy Gemini)"""
        url = f"https://api.shopaikey.com/v1beta/models/{model}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2 if task_type != "spun" else 0.7
            }
        }

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=120)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
                result_text = parts[0].get("text", "").strip() if parts else ""

                threading.Thread(target=self._log_shopaikey_usage, args=(api_key, task_type), daemon=True).start()

                if result_text:
                    try:
                        if self.ui.main_app.root.winfo_exists():
                            self.ui.main_app.root.after(0, lambda: self.ui._process_ai_result(result_text, task_type))
                    except (RuntimeError, AttributeError, tk.TclError):
                        pass
                else:
                    try:
                        if self.ui.main_app.root.winfo_exists():
                            self.ui.main_app.root.after(0, lambda: self.ui.add_log("❌ ShopAIKey: Response rỗng", provider="shopaikey"))
                    except (RuntimeError, AttributeError, tk.TclError):
                        pass
            else:
                error_msg = f"ShopAIKey Error {res.status_code}: {res.text}"
                try:
                    if self.ui.main_app.root.winfo_exists():
                        self.ui.main_app.root.after(0, lambda err=error_msg: self.ui.add_log(f"❌ {err}", provider="shopaikey"))
                except (RuntimeError, AttributeError, tk.TclError):
                    pass
        except Exception as e:
            try:
                if self.ui.main_app.root.winfo_exists():
                    self.ui.main_app.root.after(0, lambda err=str(e): self.ui.add_log(f"❌ Lỗi ShopAIKey: {err}", provider="shopaikey"))
            except (RuntimeError, AttributeError, tk.TclError):
                pass
    
    def _call_openai_api(self, api_key, prompt, task_type, model="gpt-4o"):
        """Gọi OpenAI API"""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2 if task_type != "spun" else 0.7
        }
        
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=120)
            if res.status_code == 200:
                data = res.json()
                result_text = data["choices"][0]["message"]["content"].strip()
                usage = data.get("usage")
                if usage:
                    self._log_openai_usage(model, usage, task_type)
                
                # --- LỚP GIÁP 1: BẢO VỆ KHI XỬ LÝ KẾT QUẢ THÀNH CÔNG ---
                try:
                    if self.ui.main_app.root.winfo_exists():
                        self.ui.main_app.root.after(0, lambda: self.ui._process_ai_result(result_text, task_type))
                except (RuntimeError, AttributeError, tk.TclError):
                    pass # App đã tắt thì bơ đi
            else:
                error_msg = f"OpenAI Error {res.status_code}: {res.text}"
                # --- LỚP GIÁP 2: BẢO VỆ KHI API BÁO LỖI ---
                try:
                    if self.ui.main_app.root.winfo_exists():
                        self.ui.main_app.root.after(0, lambda err=error_msg: self.ui.add_log(f"❌ {err}", provider="openai"))
                except (RuntimeError, AttributeError, tk.TclError):
                    pass
        except Exception as e:
            # --- LỚP GIÁP 3: BẢO VỆ KHI MẤT KẾT NỐI MẠNG ---
            try:
                if self.ui.main_app.root.winfo_exists():
                    self.ui.main_app.root.after(0, lambda err=str(e): self.ui.add_log(f"❌ Lỗi OpenAI: {err}", provider="openai"))
            except (RuntimeError, AttributeError, tk.TclError):
                pass

    def _call_kie_api_direct(self, api_key, prompt, task_type, model="gemini-3-flash"):
        url = "https://api.kie.ai/gemini-3-flash/v1/chat/completions" 
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2 if task_type != "spun" else 0.7 
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=120)
            if res.status_code == 200:
                result_text = res.json()["choices"][0]["message"]["content"].strip()
                
                # --- LỚP GIÁP 1: BẢO VỆ KHI XỬ LÝ KẾT QUẢ THÀNH CÔNG ---
                try:
                    if self.ui.main_app.root.winfo_exists():
                        self.ui.main_app.root.after(0, lambda: self.ui._process_ai_result(result_text, task_type))
                except (RuntimeError, AttributeError, tk.TclError):
                    pass # App đã tắt thì bơ đi
            else:
                # --- LỚP GIÁP 2: BẢO VỆ KHI API BÁO LỖI ---
                try:
                    if self.ui.main_app.root.winfo_exists():
                        self.ui.main_app.root.after(0, lambda err=res.text: self.ui.add_log(f"❌ Lỗi Kie: {err}", provider="kie"))
                except (RuntimeError, AttributeError, tk.TclError):
                    pass
        except Exception as e:
            # --- LỚP GIÁP 3: BẢO VỆ KHI MẤT KẾT NỐI MẠNG ---
            try:
                if self.ui.main_app.root.winfo_exists():
                    self.ui.main_app.root.after(0, lambda err=str(e): self.ui.add_log(f"❌ Lỗi mạng: {err}", provider="kie"))
            except (RuntimeError, AttributeError, tk.TclError):
                pass