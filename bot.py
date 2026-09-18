import time
import re
import argparse
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Import user configuration if available
try:
    from user_config import USER_DATA, MIN_DATE, AUTO_SUBMIT
except ImportError:
    USER_DATA = None
    MIN_DATE = None
    AUTO_SUBMIT = False

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
URL = "https://itc-halle.saas.smartcjm.com/m/standesamt/extern/calendar/?uid=9da900ff-e9a5-46be-a622-ecdfa078121c"

DEFAULT_CATEGORY = "Staatsangehörigkeitsangelegenheiten"
DEFAULT_SERVICE = "02. Antrag Einbürgerung"

TEST_CATEGORY = "Standesamt"
TEST_SERVICE = "02. Beratung in Eheangelegenheiten mit Auslandsbeteiligung (Termine zur anschließenden Anmeldung der Eheschließung werden vom Standesamt vergeben)"

def send_telegram_message(text):
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print(f"[Telegram Not Configured] Message:\n{text}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending telegram message: {e}")

def find_target_slot(slots, min_date_str=None):
    """Finds the first slot on or after min_date_str (format YYYY-MM-DD)."""
    if not slots:
        return None
    if not min_date_str:
        return slots[0]
    
    target_date = datetime.strptime(min_date_str, "%Y-%m-%d").date()
    for s in slots:
        dt = s.get("date_time", "")
        if " " in dt:
            d_part = dt.split(" ")[0]
            try:
                slot_date = datetime.strptime(d_part, "%d.%m.%Y").date()
                if slot_date >= target_date:
                    return s
            except ValueError:
                pass
    return None

def fill_and_book_appointment(page, slot, user_data=USER_DATA, auto_submit=False):
    """Navigates to the booking link for the given slot and fills Kontaktdaten."""
    if not user_data:
        print("Error: USER_DATA is not configured in user_config.py.")
        return False
    
    m = re.search(r'href=["\']([^"\']+)["\']', slot.get("link", ""))
    if not m:
        print("Could not extract booking link from slot.")
        return False
    
    booking_path = m.group(1).replace("\t", "").strip()
    booking_url = "https://itc-halle.saas.smartcjm.com" + booking_path
    
    print(f"\n[Booking] Navigating to booking form for: {slot.get('date_time', '')}...")
    page.goto(booking_url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    
    # Fill Anrede (Salutation)
    try:
        sal_val = user_data.get("salutation", "m")
        page.evaluate(f"""() => {{
            var sel = document.getElementById('salutation');
            if (sel) {{
                sel.value = '{sal_val}';
                if (window.$ && $(sel).parent().hasClass('dropdown')) {{
                    $(sel).parent().dropdown('set selected', '{sal_val}');
                }}
            }}
        }}""")
    except Exception as e:
        print(f"Warning setting salutation: {e}")
        
    # Fill text inputs
    page.fill('input[name="first_name"]', user_data.get("first_name", ""))
    page.fill('input[name="last_name"]', user_data.get("last_name", ""))
    page.fill('input[name="mail"]', user_data.get("email", ""))
    page.fill('input[name="mail2"]', user_data.get("email", ""))
    page.fill('input[name="phone"]', user_data.get("phone", ""))
    page.fill('input[name="birthday"]', user_data.get("birthday", ""))
    
    # Check data privacy checkbox
    privacy_checkbox = page.locator('input[name="dataprivacy"]')
    if not privacy_checkbox.is_checked():
        privacy_checkbox.check()
    
    page.wait_for_timeout(1000)
    page.screenshot(path="form_filled.png")
    print("Screenshot of filled form saved as form_filled.png.")
    
    if auto_submit:
        print("Submitting booking ('Termin buchen')...")
        page.click("#book-appointment")
        page.wait_for_timeout(5000)
        page.screenshot(path="booking_confirmation.png")
        print("Booking confirmation saved as booking_confirmation.png.")
        
        success_msg = f"🎉 نوبت با موفقیت ثبت قطعی شد!\nتاریخ و ساعت: {slot.get('date_time', '')}\nنام: {user_data.get('first_name')} {user_data.get('last_name')}"
        print(success_msg)
        send_telegram_message(success_msg)
        return True
    else:
        print("\n" + "="*55)
        print("ℹ️ DRY-RUN: تمام فیلدهای فرم با موفقیت تکمیل شدند.")
        print(f"نوبت انتخابی: {slot.get('date_time', '')}")
        print("دکمه نهایی 'Termin buchen' کلیک نشد (حالت تست / امنیت).")
        print("برای ثبت قطعی، فلگ --submit را اضافه کنید یا AUTO_SUBMIT = True بگذارید.")
        print("="*55 + "\n")
        return True

def check_appointments(category_name=DEFAULT_CATEGORY, service_name=DEFAULT_SERVICE, auto_book=False, auto_submit=False, min_date_filter=MIN_DATE):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking appointments for '{service_name}' ({category_name})...")
            page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            
            # Handle cookie banner if present
            try:
                page.wait_for_selector('button:has-text("Alle akzeptieren"), button:has-text("Zustimmen")', timeout=4000)
                page.locator('button:has-text("Alle akzeptieren"), button:has-text("Zustimmen")').first.click()
                time.sleep(1)
            except:
                pass
            
            # Expand category accordion
            cat_elem = page.locator(".title").filter(has_text=category_name).first
            cat_elem.wait_for(state="visible", timeout=30000)
            cat_elem.click()
            page.wait_for_timeout(1000)
            
            # Click service
            srv_elem = page.locator(".service_title").filter(has_text=service_name).first
            srv_elem.wait_for(state="visible", timeout=15000)
            srv_elem.click()
            page.wait_for_timeout(3000)
            
            # Extract appointment data directly from page JS state
            slots = page.evaluate("() => (typeof pA !== 'undefined' && pA !== 'nothing_Found' && pA.appointments) ? pA.appointments : []")
            
            if not slots:
                if "Keine freien Termine gefunden" in page.content() or page.evaluate("() => typeof pA !== 'undefined' && pA === 'nothing_Found'"):
                    print("No free appointments found.")
                else:
                    print("No appointments found (calendar empty).")
                return False
            else:
                target_slot = find_target_slot(slots, min_date_filter)
                if min_date_filter and not target_slot:
                    print(f"Appointments found, but none match criteria (>={min_date_filter}). Continuing search...")
                    return False

                # Group appointments by date
                dates = {}
                for s in slots:
                    dt = s.get("date_time", "")
                    if " " in dt:
                        d, t = dt.split(" ", 1)
                        dates.setdefault(d, []).append(t)
                    elif dt:
                        dates.setdefault(dt, [])

                # Format human-readable summary
                date_lines = []
                for d, times in list(dates.items())[:8]:
                    times_preview = ", ".join(times[:4])
                    if len(times) > 4:
                        times_preview += f" (+{len(times)-4} more)"
                    date_lines.append(f"📅 {d}: {times_preview}")
                
                if len(dates) > 8:
                    date_lines.append(f"... und {len(dates) - 8} weitere Tage")
                
                summary = "\n".join(date_lines)
                msg = (
                    f"🚨 نوبت آزاد پیدا شد!\n"
                    f"خدمت: {service_name}\n"
                    f"تعداد کل نوبت‌ها: {len(slots)} نوبت در {len(dates)} روز\n\n"
                    f"تاریخ‌های موجود:\n{summary}\n\n"
                    f"لینک رزرو:\n{URL}"
                )
                print("\n" + "="*50)
                print(msg)
                print("="*50 + "\n")
                send_telegram_message(msg)
                
                # If auto-booking is requested:
                if auto_book:
                    if target_slot:
                        print(f"Selected target appointment matching filter (>={min_date_filter}): {target_slot.get('date_time')}")
                        fill_and_book_appointment(page, target_slot, USER_DATA, auto_submit)
                    else:
                        print(f"Appointments found, but none match criteria (>={min_date_filter}).")
                
                return True
                
        except Exception as e:
            print(f"Error during check: {e}")
            page.screenshot(path="error_screenshot.png")
            print("Screenshot saved as error_screenshot.png.")
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Termin Bot for Halle Serviceportal")
    parser.add_argument("--category", "-c", type=str, default=None, help="Category name (default: Staatsangehörigkeitsangelegenheiten)")
    parser.add_argument("--service", "-s", type=str, default=None, help="Service name (default: 02. Antrag Einbürgerung)")
    parser.add_argument("--ehe", action="store_true", help="Shortcut to check 02. Beratung in Eheangelegenheiten")
    parser.add_argument("--book", action="store_true", help="Automatically fill booking form for the first matching slot")
    parser.add_argument("--submit", action="store_true", help="Actually click 'Termin buchen' to finalize booking")
    parser.add_argument("--min-date", type=str, default=MIN_DATE, help="Minimum date (YYYY-MM-DD, e.g. 2027-02-01)")
    parser.add_argument("--once", action="store_true", help="Run once and exit instead of continuous loop")
    parser.add_argument("--interval", type=int, default=90, help="Interval between checks in seconds (default: 90)")
    
    args = parser.parse_args()
    
    # Determine category and service
    if args.ehe:
        selected_category = TEST_CATEGORY
        selected_service = TEST_SERVICE
    elif args.service:
        selected_service = args.service
        if args.category:
            selected_category = args.category
        elif "Ehe" in args.service:
            selected_category = "Standesamt"
        else:
            selected_category = DEFAULT_CATEGORY
    else:
        selected_category = args.category if args.category else DEFAULT_CATEGORY
        selected_service = DEFAULT_SERVICE
        
    print(f"Starting Termin Bot for '{selected_service}' in '{selected_category}'...")
    
    auto_book = args.book or (AUTO_SUBMIT is True)
    auto_submit = args.submit or AUTO_SUBMIT
    
    if args.once:
        check_appointments(selected_category, selected_service, auto_book=auto_book, auto_submit=auto_submit, min_date_filter=args.min_date)
    else:
        while True:
            found = check_appointments(selected_category, selected_service, auto_book=auto_book, auto_submit=auto_submit, min_date_filter=args.min_date)
            if found:
                print("Termin found! Stopping bot.")
                break
            time.sleep(args.interval)


