pip install selenium pandas beautifulsoup4

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import time

# set the browser
options = Options()
options.add_argument("--headless")  # بدون واجهة
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

service = Service("chromedriver.exe")  # المسار إلى WebDriver
driver = webdriver.Chrome(service=service, options=options)

# الصفحات المطلوبة
urls = [
    "https://www.carrefouregypt.com/mafegy/en",
    "https://www.carrefouregypt.com/mafegy/en/c/NFEGY2000000"
]

all_products = []

for url in urls:
    driver.get(url)
    time.sleep(5)  # استنى تحميل الصفحة
    
    # نزول تلقائي لجلب كل المنتجات (لو الصفحة طويلة)
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # كل منتج
    products = soup.find_all("div", class_="product-card")  # قد تحتاجي تحديث الكلاس حسب الموقع

    for p in products:
        name = p.find("p", class_="product-title")
        price = p.find("span", class_="selling-price")
        old_price = p.find("span", class_="was-price")
        discount = p.find("span", class_="discount")
        link = p.find("a", href=True)

        all_products.append({
            "Product Name": name.text.strip() if name else None,
            "Current Price": price.text.strip() if price else None,
            "Old Price": old_price.text.strip() if old_price else None,
            "Discount": discount.text.strip() if discount else None,
            "Product URL": "https://www.carrefouregypt.com" + link['href'] if link else None,
            "Page Source": url
        })

driver.quit()

# تحويل إلى DataFrame
df = pd.DataFrame(all_products)
df.to_excel("carrefour_data.xlsx", index=False)

print("✅ Data saved to carrefour_data.xlsx")






# أنشئي virtualenv يفضل
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate

pip install --upgrade pip
pip install playwright pandas openpyxl
# ثم ثبتي المتصفحات المطلوبة
python -m playwright install

from playwright.sync_api import sync_playwright
import time
import pandas as pd
import re
from urllib.parse import urljoin

BASE = "https://www.carrefouregypt.com"

def extract_from_html(page, product_selector, mappings):
    # runs in-browser JS to return list of dicts quickly
    return page.evaluate("""
    (product_selector, mappings) => {
        const nodes = Array.from(document.querySelectorAll(product_selector));
        return nodes.map(node => {
            const out = {};
            for (const [key, sel] of Object.entries(mappings)) {
                const el = node.querySelector(sel);
                out[key] = el ? el.innerText.trim() : null;
                // if href
                if (!out[key] && sel.endsWith('@href')) {
                    const s = sel.replace('@href','');
                    const e = node.querySelector(s);
                    out[key] = e ? e.href : null;
                }
            }
            return out;
        });
    }
    """, product_selector, mappings)

def run(urls, product_selector, mappings, headless=True, max_scrolls=20):
    all_items = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()

        # capture potential XHR/JSON responses that carry products
        api_responses = []
        def handle_response(response):
            try:
                url = response.url
                if "product" in url.lower() or "search" in url.lower() or "category" in url.lower():
                    ct = response.headers.get("content-type","")
                    if "application/json" in ct:
                        try:
                            api_responses.append({"url": url, "json": response.json()})
                        except:
                            pass
            except Exception as e:
                pass

        page.on("response", handle_response)

        for url in urls:
            print("Opening:", url)
            page.goto(url, wait_until="domcontentloaded")
            # انتظار اضافي لJS
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)

            # محاولة عمل scroll لجلب العناصر اللاحقة (infinite scroll)
            previous_height = None
            for i in range(max_scrolls):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
                page.wait_for_load_state("networkidle", timeout=5000)
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == previous_height:
                    break
                previous_height = new_height

            # إذا فيه زر "Load more" نحاول نضغطه حتى النهاية
            try:
                while True:
                    more = page.query_selector("button[aria-label*='Load more'], button.load-more, .load-more-button")
                    if not more:
                        break
                    more.click()
                    page.wait_for_load_state("networkidle", timeout=8000)
                    time.sleep(1.5)
            except Exception:
                pass

            # استخراج من DOM باستخدام سيلكتور عام للـ product-card
            try:
                results = extract_from_html(page, product_selector, mappings)
                for r in results:
                    r['source_page'] = url
                    # normalize relative urls
                    if r.get("Product URL") and r["Product URL"].startswith("/"):
                        r["Product URL"] = urljoin(BASE, r["Product URL"])
                all_items.extend(results)
            except Exception as e:
                print("HTML extraction failed:", e)

        browser.close()

    return all_items, api_responses

if __name__ == "__main__":
    urls = [
        "https://www.carrefouregypt.com/mafegy/en",
        "https://www.carrefouregypt.com/mafegy/en/c/NFEGY2000000"
    ]

    # عدّلي الماب ده حسب اللي تشوفيه في DevTools (أمثلة شائعة)
    mappings = {
        "Product Name": ".product-card__title, .product-title, .product-name",
        "Current Price": ".price, .selling-price, .product-card__price",
        "Old Price": ".was-price, .old-price, .product-card__was-price",
        "Discount": ".discount, .product-card__badge",
        "Product URL": "a.product-card__link@href, a[href*='/p/']@href"
    }

    # المكوّن الرئيسي الذي يحتوي منتجات (حددي بعد الفحص)
    product_selector = ".product-card, .product-list-item, .product-tile"

    items, api_resps = run(urls, product_selector, mappings, headless=True)

    # لو لقيت JSON في api_resps، ده غالبًا غني بالداتا الأصلية - افحصيه
    print("Captured API responses:", len(api_resps))

    # تحويل للقيم المفيدة وتنظيف بسيط
    df = pd.DataFrame(items)
    # تنظيف أسعار : شيل جنيه/EGP أو رموز
    def normalize_price(s):
        if not s: return None
        s = re.sub(r"[^\d\.]", "", s)
        try:
            return float(s)
        except:
            return None

    if "Current Price" in df.columns:
        df["Current Price Clean"] = df["Current Price"].apply(normalize_price)
    if "Old Price" in df.columns:
        df["Old Price Clean"] = df["Old Price"].apply(normalize_price)

    df.to_excel("carrefour_playwright_data.xlsx", index=False)
    print("Saved", len(df), "rows to carrefour_playwright_data.xlsx")



