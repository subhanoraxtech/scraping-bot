from fastapi import FastAPI, HTTPException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
import time
import json
from urllib.parse import unquote

app = FastAPI()

def scrape_sms(url: str):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    chrome_options.page_load_strategy = 'eager'
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(10)
    
    try:
        driver.get(url)
        time.sleep(2)
        
        button = driver.execute_script("""
            const elements = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]'));
            for (let elem of elements) {
                const text = (elem.textContent || elem.innerText || elem.getAttribute('aria-label') || '').toLowerCase();
                if (text.includes('sms')) {
                    return elem;
                }
            }
            return null;
        """)
        
        if not button:
            raise Exception("Could not find Send SMS button")
        
        driver.execute_script("arguments[0].click();", button)
        time.sleep(2)
        
        logs = driver.get_log('performance')
        sms_number = None
        sms_body = None
        
        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']
                if log['method'] == 'Network.requestWillBeSent':
                    sms_url = log['params']['request'].get('url', '')
                    if sms_url.startswith('sms://') and 'body=' in sms_url:
                        number_start = 6
                        number_end = sms_url.find('/', number_start)
                        sms_number = sms_url[number_start:number_end]
                        
                        body_start = sms_url.find('body=') + 5
                        sms_body = unquote(sms_url[body_start:])
                        break
            except:
                continue
        
        return sms_number, sms_body
    
    finally:
        driver.quit()

@app.get("/")
def root():
    return {"message": "SMS Scraper API", "usage": "/get-sms?url=YOUR_URL"}

@app.get("/get-sms")
def get_sms(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
    
    try:
        number, text = scrape_sms(url)
        
        if number and text:
            return {
                "success": True,
                "number": number,
                "text": text
            }
        else:
            raise HTTPException(status_code=404, detail="Could not capture SMS data")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)