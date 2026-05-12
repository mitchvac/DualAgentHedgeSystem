from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:8501")
    # Wait for Streamlit to finish loading and rendering plots
    time.sleep(8)
    page.screenshot(path="streamlit_dashboard.png", full_page=True)
    browser.close()
    print("Screenshot saved to streamlit_dashboard.png")
