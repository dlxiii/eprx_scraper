import os
import requests
import urllib3
from urllib.parse import urljoin
from datetime import date
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

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
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                )
            }
        )

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
        report_type: str = "final",
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
        checkbox = self.page.locator('input[name="check"]')
        if checkbox.count() > 0:
            try:
                checkbox.check(force=True)
            except Exception:
                # Fallback to clicking the label if checkbox is hidden
                self.page.locator('label.agreeCheck__checkbox').click()
            self.page.locator('input[type="submit"][name="submit"]').click()
            self.page.wait_for_load_state("networkidle")

        # Select results type (速報値 or 確報値)
        target_link = "確報値" if report_type == "final" else "速報値"
        try:
            self.page.get_by_role("link", name=target_link).click()
        except Exception:
            self.page.locator(f'text="{target_link}"').first.click()
        self.page.wait_for_load_state("networkidle")

        if date:
            try:
                self.page.get_by_role("link", name=f"{date}年度").click()
            except Exception:
                self.page.locator(f'text="{date}年度"').first.click()
            self.page.wait_for_load_state("networkidle")

    def results(self, debug: bool = False, year: int | None = None, report_type: str = "final"):
        """Navigate to the results page for a specific year."""
        if year is None:
            year = date.today().year
        self._navigate_results_page(
            str(year),
            debug,
            accept_downloads=True,
            item="results",
            report_type=report_type,
        )
        if report_type == "final":
            self._download_year_zips(str(year))
        if debug:
            print(f"Navigated to: {self.page.url}")
        return self.page

    # ----- Direct download methods -----

    def fetch_results_page(self) -> str:
        """Return HTML of the results page."""
        r = self.session.get(self.results_page, verify=False)
        r.raise_for_status()
        return r.text

    def parse_links(self, html: str, year: str | None = None, report_type: str = "final") -> list[str]:
        """Parse ZIP file links from HTML."""
        table_title = (
            "取引結果・連系線確保量結果ダウンロード（確報値）"
            if report_type == "final"
            else "取引結果・連系線確保量結果ダウンロード（速報値）"
        )
        soup = BeautifulSoup(html, "html.parser")
        section_title = soup.find("h2", string=table_title)
        if not section_title:
            return []
        table = section_title.find_next("table")
        if not table:
            return []
        links: list[str] = []
        for tr in table.find_all("tr"):
            yr = tr.find("th", scope="row")
            if yr:
                yr_text = yr.get_text(strip=True).replace("年度", "")
                if year and yr_text != year:
                    continue
            for a in tr.find_all("a", href=True):
                links.append(urljoin(self.base_url, a["href"]))
        return links

    def download_files(self, links: list[str], out_dir: str = "zip", overwrite: bool = True) -> None:
        os.makedirs(out_dir, exist_ok=True)
        for url in links:
            filename = os.path.join(out_dir, os.path.basename(url))
            if os.path.exists(filename) and not overwrite:
                print(f"File exists, skipping: {filename}")
                continue
            try:
                r = self.session.get(url, verify=False)
                if r.ok and len(r.content) > 100:
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    print(f"Downloaded: {filename}")
                else:
                    print(f"Failed to download: {url}")
            except Exception as exc:
                print(f"Error downloading {url}: {exc}")

    def results_direct(self, debug: bool = False, year: int | None = None, report_type: str = "final") -> None:
        """Directly download result ZIP files without using Playwright."""
        if year is None:
            year = date.today().year
        try:
            html = self.fetch_results_page()
        except Exception as exc:
            print(f"Failed to fetch results page: {exc}")
            return
        links = self.parse_links(html, str(year), report_type)
        if not links:
            print("No links found.")
            return
        self.download_files(links)

    def _download_year_zips(self, year: str) -> None:
        """Download all ZIP files listed for the specified year."""
        links = self.page.locator('a[href$=".zip"]')
        count = links.count()
        os.makedirs("zip", exist_ok=True)
        for i in range(count):
            try:
                with self.page.expect_download() as download_info:
                    links.nth(i).click()
                download = download_info.value
                out_path = os.path.join("zip", download.suggested_filename)
                download.save_as(out_path)
                print(f"Downloaded: {out_path}")
            except Exception as e:
                print(f"Failed to download file: {e}")

    def close_session(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def main():
    scraper = EPRX()
    scraper.results_direct(debug=True, year=date.today().year, report_type="final")
    scraper.close_session()


if __name__ == "__main__":
    main()
