from fastapi import FastAPI, HTTPException
from playwright.async_api import async_playwright
import asyncio
from urllib.parse import unquote
import json
import os

app = FastAPI()

async def scrape_sms(url: str):
    async with async_playwright() as p:
        # Check for remote browser endpoint (Required for Vercel)
        browser_ws_endpoint = os.environ.get("BROWSER_WS_ENDPOINT")
        
        if browser_ws_endpoint:
            print(f"Connecting to remote browser...")
            browser = await p.chromium.connect(browser_ws_endpoint)
        else:
            # Fallback to local launch (Works on Railway/Local)
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-extensions',
                    '--disable-images',
                ]
            )
        
        context = await browser.new_context()
        page = await context.new_page()
        
        # Store network requests
        sms_data = {'number': None, 'body': None}
        
        async def handle_request(request):
            url = request.url
            if url.startswith('sms://') and 'body=' in url:
                number_start = 6
                # Find the end of the number (either / or ?)
                number_end_slash = url.find('/', number_start)
                number_end_q = url.find('?', number_start)
                
                if number_end_slash != -1 and (number_end_q == -1 or number_end_slash < number_end_q):
                    number_end = number_end_slash
                elif number_end_q != -1:
                    number_end = number_end_q
                else:
                    number_end = len(url)
                    
                sms_data['number'] = url[number_start:number_end]
                
                body_start = url.find('body=') + 5
                sms_data['body'] = unquote(url[body_start:])
        
        page.on('request', handle_request)
        
        try:
            # Navigate to the page
            await page.goto(url, wait_until='domcontentloaded', timeout=10000)
            await asyncio.sleep(2)
            
            # Find and click the SMS button
            button = await page.evaluate("""
                () => {
                    const elements = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]'));
                    for (let elem of elements) {
                        const text = (elem.textContent || elem.innerText || elem.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('sms')) {
                            return elem;
                        }
                    }
                    return null;
                }
            """)
            
            if not button:
                raise Exception("Could not find Send SMS button")
            
            # Click the button
            await page.click('button:has-text("SMS"), div[role="button"]:has-text("SMS"), span[role="button"]:has-text("SMS")')
            await asyncio.sleep(2)
            
            return sms_data['number'], sms_data['body']
        
        finally:
            await browser.close()

@app.get("/")
def root():
    return {"message": "SMS Scraper API", "usage": "/get-sms?url=YOUR_URL"}

@app.get("/get-sms")
async def get_sms(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
    
    try:
        number, text = await scrape_sms(url)
        
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