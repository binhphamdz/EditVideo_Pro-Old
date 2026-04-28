import argparse
import os
import sys
import time
from typing import Iterable, Optional


SHOWCASE_URL = "https://shop.tiktok.com/streamer/showcase/product/list"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"


def log(msg: str) -> None:
    print(f"[TEST-FLOW] {msg}")


def click_any(page, selectors: Iterable[str], timeout_ms: int = 6000) -> str:
    last_error: Optional[Exception] = None
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.click(timeout=timeout_ms)
            log(f"Clicked by selector: {sel}")
            return sel
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Khong tim thay nut can click. Tried: {list(selectors)}") from last_error


def fill_any(page, selectors: Iterable[str], value: str, timeout_ms: int = 6000) -> str:
    last_error: Optional[Exception] = None
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            try:
                loc.fill(value, timeout=timeout_ms)
            except Exception:
                loc.click(timeout=timeout_ms)
                page.keyboard.press("Control+A")
                page.keyboard.type(value)
            log(f"Filled by selector: {sel}")
            return sel
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Khong tim thay o nhap lieu. Tried: {list(selectors)}") from last_error


def ensure_not_login_redirect(page, where: str) -> None:
    url = (page.url or "").lower()
    if "login" in url or "signup" in url:
        raise RuntimeError(
            f"Dang bi redirect login o {where}. Mo profile chrome va dang nhap tay truoc. URL={page.url}"
        )


def phase_showcase(page, product_link: str, timeout_ms: int) -> None:
    log("PHASE 1: Mo Showcase va bom link san pham")
    page.goto(SHOWCASE_URL, wait_until="domcontentloaded")
    time.sleep(1.2)
    ensure_not_login_redirect(page, "showcase")

    # 1. Bấm nút Thêm sản phẩm mới
    click_any(
        page,
        [
            "button[data-tid='m4b_button']:has-text('Thêm sản phẩm mới')",
            "button:has-text('Thêm sản phẩm mới')",
        ],
        timeout_ms,
    )
    time.sleep(0.5)

    # 2. Điền link vào input đúng placeholder
    fill_any(
        page,
        [
            "input[data-tid='m4b_input'][placeholder*='URL sản phẩm']",
            "input[placeholder*='URL sản phẩm']",
        ],
        product_link,
        timeout_ms,
    )
    time.sleep(0.2)

    # 3. Bấm nút URL sản phẩm để load
    click_any(
        page,
        [
            "button[data-tid='m4b_button']:has-text('URL sản phẩm')",
            "button:has-text('URL sản phẩm')",
        ],
        timeout_ms,
    )
    time.sleep(1.2)

    # 4. Kiểm tra sản phẩm đã hiện ra trong bảng
    table = page.locator("[data-tid='m4b_table'] table tbody tr")
    if table.count() < 1:
        raise RuntimeError("Không tìm thấy sản phẩm nào sau khi nhập link. Kiểm tra lại link hoặc selector.")

    # 5. Bấm nút Thêm sản phẩm
    click_any(
        page,
        [
            "button.pc_add_product:has-text('Thêm sản phẩm')",
            "button:has-text('Thêm sản phẩm')",
        ],
        timeout_ms,
    )
    time.sleep(2)
    log("PHASE 1 DONE")


def phase_upload_and_post(page, video_path: str, caption: str, timeout_ms: int, skip_post: bool) -> None:
    # Chờ upload video hoàn tất trước khi làm các bước tiếp theo
    log("Chờ upload video hoàn tất...")
    upload_wait = 0
    max_upload_wait = 10 * 60  # 10 phút
    while upload_wait < max_upload_wait:
        # Nếu còn progress bar hoặc icon cloud-upload hoặc text MB/MB thì vẫn đang upload
        uploading = False
        try:
            # Thanh progress
            if page.locator('.info-progress').count() > 0 and page.locator('.info-progress').evaluate('el => el.offsetWidth > 0 && getComputedStyle(el).visibility !== "hidden"'):
                uploading = True
            # Icon cloud-upload
            if page.locator('[data-icon="CloudUpload"]').count() > 0:
                uploading = True
            # Text MB/MB hoặc %
            if page.locator('.info-status').count() > 0:
                status_text = page.locator('.info-status').inner_text()
                if "/" in status_text or "%" in status_text or "seconds left" in status_text:
                    uploading = True
        except Exception:
            pass
        if not uploading:
            break
        if upload_wait % 10 == 0:
            log(f"...đang chờ upload video ({upload_wait}s)")
        time.sleep(2)
        upload_wait += 2
    else:
        raise RuntimeError("Quá thời gian chờ upload video!")

    log("PHASE 2: Upload video, gan san pham, dang bai")
    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
    time.sleep(2)
    ensure_not_login_redirect(page, "upload")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Khong tim thay video: {video_path}")

    file_input = page.locator("input[type='file']").first
    file_input.set_input_files(video_path)
    log("Da set file video vao input upload")
    time.sleep(2)

    # 1. Điền mô tả vào caption-editor (ưu tiên contenteditable)
    if caption.strip():
        filled = False
        for sel in [
            "div.jsx-1601248207.caption-editor div[contenteditable='true']",
            "div[contenteditable='true']",
            "textarea",
            "[role='textbox']",
        ]:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=timeout_ms)
                loc.click(timeout=timeout_ms)
                loc.fill(caption, timeout=timeout_ms)
                log(f"Filled caption by selector: {sel}")
                filled = True
                break
            except Exception:
                continue
        if not filled:
            raise RuntimeError("Không điền được mô tả vào caption-editor")
        time.sleep(1)

    # 2. Ấn nút Add (icon Plus, class Button__root, text Add)
    click_any(
        page,
        [
            "button.Button__root:has-text('Add')",
            "button:has-text('Add')",
        ],
        timeout_ms,
    )
    time.sleep(1)

    # 3. Trong popup Add link: chọn Products nếu chưa chọn, ấn Next/Tiếp đúng modal (hỗ trợ cả tiếng Việt/Anh)
    try:
        # Kiểm tra nếu đã đúng loại liên kết thì không click nữa
        modal_titles = ["Add link", "Thêm liên kết"]
        modal = None
        for title in modal_titles:
            m = page.locator(f".TUXModal[title='{title}']")
            if m.count() > 0:
                modal = m
                break
        if modal is None:
            raise RuntimeError("Không tìm thấy modal Thêm liên kết/Add link!")
        # Kiểm tra text đang chọn
        selected = modal.locator("button.TUXSelect-button .select-option-label").first
        selected_text = selected.inner_text(timeout=timeout_ms).strip().lower()
        if selected_text not in ["products", "sản phẩm"]:
            selected.click(timeout=timeout_ms)
            # Chọn lại đúng option
            option = modal.locator(".select-option-label:has-text('Products'), .select-option-label:has-text('Sản phẩm')").first
            option.click(timeout=timeout_ms)
            log("Đã chọn lại loại liên kết Products/Sản phẩm trong Add link popup")
            time.sleep(0.3)
        else:
            log("Đã đúng loại liên kết Products/Sản phẩm, không cần chọn lại")
    except Exception:
        pass
    # Chờ nút Next/Tiếp trong modal đúng title
    modal = None
    for title in ["Add link", "Thêm liên kết"]:
        m = page.locator(f".TUXModal[title='{title}']")
        if m.count() > 0:
            modal = m
            break
    if modal is None:
        raise RuntimeError("Không tìm thấy modal Thêm liên kết/Add link!")
    btn_next = modal.locator("button.TUXButton--primary:has-text('Next'), button.TUXButton--primary:has-text('Tiếp')")
    btn_next.wait_for(state="visible", timeout=timeout_ms)
    for _ in range(20):
        if not btn_next.is_disabled():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Nút Next/Tiếp trong modal Thêm liên kết/Add link vẫn bị disabled!")
    btn_next.click(timeout=timeout_ms)
    time.sleep(1)

    # 4. Trong bảng sản phẩm: chọn radio đầu tiên, ấn Tiếp đúng modal
    radio = page.locator(".product-table input[type='radio']").first
    if radio.count() > 0:
        radio.check(timeout=timeout_ms)
        log("Checked first product radio")
    else:
        raise RuntimeError("Không tìm thấy radio chọn sản phẩm trong bảng sản phẩm")
    time.sleep(0.3)
    modal2 = page.locator(".TUXModal.product-selector-modal")
    btn_next2 = modal2.locator("button.TUXButton--primary:has-text('Next'), button.TUXButton--primary:has-text('Tiếp')")
    btn_next2.wait_for(state="visible", timeout=timeout_ms)
    for _ in range(20):
        if not btn_next2.is_disabled():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Nút Next/Tiếp trong modal chọn sản phẩm vẫn bị disabled!")
    btn_next2.click(timeout=timeout_ms)
    time.sleep(1)

    # 5. Trong modal Add product links: ấn Add/Thêm
    modal3 = page.locator(".TUXModal[title='Add product links']")
    btn_add = modal3.locator("button.TUXButton--primary:has-text('Add'), button.TUXButton--primary:has-text('Thêm')")
    btn_add.wait_for(state="visible", timeout=timeout_ms)
    for _ in range(20):
        if not btn_add.is_disabled():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Nút Add/Thêm trong modal Add product links vẫn bị disabled!")
    btn_add.click(timeout=timeout_ms)
    time.sleep(1)

    if skip_post:
        log("SKIP POST mode: da dung truoc buoc Dang")
        return

    # Liên tục scroll và kiểm tra nút Đăng khả dụng, thấy là bấm ngay
    log("Scroll và kiểm tra nút Đăng...")
    max_wait = 12 * 60  # 12 phút
    waited = 0
    post_btn = page.locator('button[data-e2e="post_video_button"]:not([aria-disabled="true"]):not([data-disabled="true"])')
    while waited < max_wait:
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        time.sleep(1)
        if post_btn.count() > 0 and post_btn.is_enabled():
            break
        waited += 1
    else:
        raise RuntimeError("Không tìm thấy nút Đăng khả dụng!")

    click_any(
        page,
        [
            "button:has-text('Đăng')",
            "button:has-text('Dang')",
            "button:has-text('Post')",
            "button:has-text('Publish')",
            "text=Đăng",
            "text=Dang",
            "text=Post",
        ],
        timeout_ms,
    )
    log("PHASE 2 DONE - Đã bấm Đăng, chờ load...")
    # Chờ trang load sau khi đăng (ví dụ: chờ nút Đăng biến mất hoặc chờ 10s)
    for _ in range(30):
        if post_btn.count() == 0:
            break
        time.sleep(1)
    time.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test luong TikTok Web: Showcase + Upload + Gan san pham + Dang")
    parser.add_argument(
        "--video",
        required=False,
        default=r"C:\Users\Binh\Desktop\Đèn Pin New\a.mov",
        help=r"Vi du: C:\Users\Binh\Desktop\Den Pin New\a.mov (mặc định nếu không truyền)"
    )
    parser.add_argument(
        "--product-link",
        required=False,
        default="https://www.tiktok.com/view/product/1729422730517318040",
        help="Vi du: https://www.tiktok.com/view/product/1729422730517318040 (mặc định nếu không truyền)"
    )
    parser.add_argument("--caption", default="", help="Caption dang bai")
    parser.add_argument("--user-data-dir", default=os.path.join(os.getcwd(), "Browser_Profile", "TikTokWeb"), help="Chrome user data dir")
    parser.add_argument("--profile-dir", default="Default", help="Chrome profile directory name")
    parser.add_argument("--timeout", type=int, default=25, help="Timeout moi thao tac (giay)")
    parser.add_argument("--headless", action="store_true", help="Chay an trinh duyet")
    parser.add_argument("--keep-open", action="store_true", help="Giu browser mo de quan sat")
    parser.add_argument("--skip-post", action="store_true", help="Test den buoc gan san pham, khong bam Dang")

    args = parser.parse_args()

    if not args.video:
        args.video = input("Nhap duong dan video (--video): ").strip()
    if not args.product_link:
        args.product_link = input("Nhap link san pham (--product-link): ").strip()

    if not args.video or not args.product_link:
        log("Thieu du lieu bat buoc. Can ca --video va --product-link")
        return 2

    timeout_ms = max(10, int(args.timeout)) * 1000
    os.makedirs(args.user_data_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        log("Chua co playwright. Cai bang: pip install playwright ; playwright install chromium")
        raise

    log("Bat dau test flow...")
    log(f"User data dir: {args.user_data_dir}")
    log(f"Profile dir: {args.profile_dir}")
    log(f"Headless: {args.headless}")

    with sync_playwright() as p:
        context = None
        try:
            launch_kwargs = {
                "user_data_dir": args.user_data_dir,
                "headless": bool(args.headless),
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    f"--profile-directory={args.profile_dir}",
                ],
            }

            try:
                context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
                log("Launched with Chrome channel")
            except Exception:
                context = p.chromium.launch_persistent_context(**launch_kwargs)
                log("Launched with Chromium fallback")

            context.set_default_timeout(timeout_ms)
            page = context.new_page()

            phase_showcase(page, args.product_link, timeout_ms)
            phase_upload_and_post(page, args.video, args.caption, timeout_ms, bool(args.skip_post))

            log("TEST SUCCESS")
            if args.keep_open:
                log("Keep-open enabled. Nhan Ctrl+C de thoat.")
                while True:
                    time.sleep(1)
            return 0

        except KeyboardInterrupt:
            log("Interrupted by user")
            return 130
        except Exception as exc:
            log(f"TEST FAILED: {exc}")
            return 1
        finally:
            if context is not None and not args.keep_open:
                context.close()


if __name__ == "__main__":
    sys.exit(main())
