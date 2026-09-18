import time
from playwright.sync_api import sync_playwright

URL = "https://halle.de/serviceportal/online-terminvergabe/online-terminvereinbarung-einbuergerungsbehoerde-standesamt"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    
    # Dump frames
    for frame in page.frames:
        print("Frame URL:", frame.url)
        
    page.screenshot(path="screenshot.png")
    
    # Try to find the text
    text = "Staatsangehörigkeitsangelegenheiten"
    print(f"Found '{text}' on main page:", page.locator(f"text={text}").count())
    
    for frame in page.frames:
        if frame != page.main_frame:
            print(f"Found '{text}' on frame {frame.url}:", frame.locator(f"text={text}").count())
            
    browser.close()
