import requests
import threading
import tkinter as tk  # <--- CHÚ Ý: Bổ sung thư viện này để bắt lỗi giao diện

class KieAIHandler:
    def __init__(self, ui_tab):
        self.ui = ui_tab

    def extract_info_and_keys(self, orig_text, kie_key):
        threading.Thread(target=self._get_product_info, args=(kie_key, orig_text), daemon=True).start()
        threading.Thread(target=self._get_keys, args=(kie_key, orig_text), daemon=True).start()

    def _get_product_info(self, api_key, orig_text):
        prompt = f"""Phân tích voice và trích xuất THÔNG TIN SẢN PHẨM thô.
Yêu cầu:
- Chỉ liệt kê các thông số, tính năng, tên gọi cụ thể.
- Tuyệt đối KHÔNG viết câu dẫn (Dưới đây là...), KHÔNG chia nhóm, KHÔNG viết dài dòng.
- Mỗi thông tin là một dòng ngắn gọn (dưới 15 chữ).

Đoạn voice:
{orig_text}"""
        self._call_kie_api_direct(api_key, prompt, "prod_info")

    def _get_keys(self, api_key, orig_text):
        prompt = f"""Phân tích voice và lấy ra 10 ý chính (key content) để làm video.
Yêu cầu:
- Chỉ lấy nội dung mô tả cốt lõi nhất của ý đó.
- Tuyệt đối KHÔNG ghi 'Tên key', KHÔNG ghi 'Hook', KHÔNG đánh số.
- Mỗi ý là một dòng duy nhất, ngắn gọn, súc tích. Trả về đúng 10 dòng.

Đây là đoạn voice:
{orig_text}"""
        self._call_kie_api_direct(api_key, prompt, "keys")

    def spin_script_ai(self, orig_text, system_prompt, product_info, keys_text, selected_hook, kie_key):
        hook_instruction = ""
        if selected_hook:
            hook_instruction = f"\n\n--- 🔥 MỆNH LỆNH TỐI CAO: DÙNG Ý SAU LÀM HOOK MỞ ĐẦU (ĐẨY LÊN ĐẦU VIDEO) ---\n[{selected_hook}]\n(Hãy dùng ý này để giật tít, gây chú ý ngay giây đầu tiên, sau đó mới dẫn vào các phần khác)."

        user_content = f"--- THÔNG TIN SẢN PHẨM ---\n{product_info}\n\n--- CÁC Ý CHÍNH ---\n{keys_text}{hook_instruction}\n\n--- KỊCH BẢN GỐC ---\n{orig_text}"
        
        # ĐÃ FIX: Cho lệnh gọi API vào chạy luồng ngầm để tool không bị đơ "Not Responding"
        threading.Thread(target=self._call_kie_api_direct, args=(kie_key, system_prompt + "\n\n" + user_content, "spun"), daemon=True).start()

    def _call_kie_api_direct(self, api_key, prompt, task_type):
        url = "https://api.kie.ai/gemini-3-flash/v1/chat/completions" 
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
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
                if task_type == "spun": 
                    # --- LỚP GIÁP 2: BẢO VỆ KHI API BÁO LỖI ---
                    try:
                        if self.ui.main_app.root.winfo_exists():
                            self.ui.main_app.root.after(0, lambda err=res.text: self.ui.txt_log.insert("end", f"\n❌ Lỗi Kie: {err}"))
                    except (RuntimeError, AttributeError, tk.TclError):
                        pass
        except Exception as e:
            if task_type == "spun": 
                # --- LỚP GIÁP 3: BẢO VỆ KHI MẤT KẾT NỐI MẠNG ---
                try:
                    if self.ui.main_app.root.winfo_exists():
                        self.ui.main_app.root.after(0, lambda err=str(e): self.ui.txt_log.insert("end", f"\n❌ Lỗi mạng: {err}"))
                except (RuntimeError, AttributeError, tk.TclError):
                    pass