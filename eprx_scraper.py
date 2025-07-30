import os
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.eprx.or.jp/information/"
RESULTS_PAGE = urljoin(BASE_URL, "results.php")

def scrape_trading_results():
    data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)
        # Click the link that navigates to the results page
        try:
            page.get_by_role("link", name="\u8a73\u7d30\u306f\u3053\u3061\u3089").click()
        except Exception:
            # Fallback: directly open the results page
            page.goto(RESULTS_PAGE)
        page.wait_for_load_state("networkidle")

        # Find the first table that contains trading result downloads
        tables = page.query_selector_all("table")
        target_table = None
        for table in tables:
            caption = table.query_selector("caption")
            if caption and "\u53d6\u5f15\u7d50\u679c" in caption.inner_text():
                target_table = table
                break
        if not target_table and tables:
            target_table = tables[0]

        if target_table:
            # Extract headers from the second row (product names)
            header_cells = target_table.query_selector_all("tr:nth-of-type(2) th")[1:]
            products = [cell.inner_text().strip() for cell in header_cells]
            rows = target_table.query_selector_all("tr")[2:]
            for row in rows:
                cells = row.query_selector_all("td")
                if not cells:
                    continue
                year = cells[0].inner_text().strip()
                for idx, cell in enumerate(cells[1:]):
                    link = cell.query_selector("a[href$='.zip']")
                    if link:
                        href = link.get_attribute("href")
                        data.append({
                            "year": year,
                            "product": products[idx] if idx < len(products) else f"column{idx+1}",
                            "url": urljoin(RESULTS_PAGE, href),
                        })
        browser.close()
    return data


def main():
    for item in scrape_trading_results():
        print(f"{item['year']} {item['product']} {item['url']}")


if __name__ == "__main__":
    main()
