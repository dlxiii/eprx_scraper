import os
import requests
import urllib3
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.eprx.or.jp/information/"
RESULTS_PAGE = urljoin(BASE_URL, "results.php")


class EPRX:
    """Simple scraper for EPRX trading results."""

    def __init__(self) -> None:
        self.base_url = BASE_URL
        self.results_page = RESULTS_PAGE
        self.browser = None
        self.playwright = None
        self.page = None

    def _launch_browser(self, playwright, debug: bool = False):
        browser = playwright.chromium.launch(
            headless=not debug,
            slow_mo=50 if debug else 0,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--start-maximized" if debug else "--disable-gpu",
            ],
        )
        return browser

    def _download_zip(self, dir_name: str, date: str, out_path: str, overwrite: bool = True):
        date_str = date.replace("/", "")
        file_name = f"{dir_name}_{date_str}.zip"
        url = urljoin(self.results_page, file_name)

        if os.path.exists(out_path) and not overwrite:
            print(f"File exists, skipping download: {out_path}")
            return

        headers = {
            "Referer": self.page.url if self.page else self.results_page,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(url, headers=headers, verify=False)
        if r.ok and len(r.content) > 100:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(r.content)
            print(f"Downloaded: {out_path}")
        else:
            print(f"Failed to download ZIP: {url}")

    def _navigate_results_page(
        self,
        date: str,
        debug: bool = False,
        accept_downloads: bool = False,
        item: str = "results",
    ) -> None:
        self.playwright = sync_playwright().start()
        self.browser = self._launch_browser(self.playwright, debug)
        context = self.browser.new_context(accept_downloads=accept_downloads)
        self.page = context.new_page()
        self.page.goto(self.base_url, wait_until="domcontentloaded")
        try:
            self.page.get_by_role("link", name="詳細はこちら").click()
        except Exception:
            self.page.goto(self.results_page)
        self.page.wait_for_load_state("networkidle")

    def trading_results(self, debug: bool = False):
        self._navigate_results_page("", debug, accept_downloads=False)
        data = []

        tables = self.page.query_selector_all("table")
        target_table = None
        for table in tables:
            caption = table.query_selector("caption")
            if caption and "取引結果" in caption.inner_text():
                target_table = table
                break
        if not target_table and tables:
            target_table = tables[0]

        if target_table:
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
                        data.append(
                            {
                                "year": year,
                                "product": products[idx] if idx < len(products) else f"column{idx+1}",
                                "url": urljoin(self.results_page, href),
                            }
                        )
        return data

    def close_session(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def main():
    scraper = EPRX()
    for item in scraper.trading_results():
        print(f"{item['year']} {item['product']} {item['url']}")
    scraper.close_session()


if __name__ == "__main__":
    main()
