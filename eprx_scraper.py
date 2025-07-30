import os
from datetime import date
from urllib.parse import urljoin
import zipfile

import requests
import urllib3
from bs4 import BeautifulSoup
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

    def _download_zip(
        self, dir_name: str, date: str, out_path: str, overwrite: bool = True
    ):
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
                self.page.locator("label.agreeCheck__checkbox").click()
            self.page.locator('input[type="submit"][name="submit"]').click()
            self.page.wait_for_load_state("networkidle")

        # Locate the results table directly without clicking the link
        table_title = (
            "取引結果・連系線確保量結果ダウンロード（確報値）"
            if report_type == "final"
            else "取引結果・連系線確保量結果ダウンロード（速報値）"
        )
        section = self.page.locator(f'h2:has-text("{table_title}")')
        section.wait_for()

    def results(
        self, debug: bool = False, year: int | None = None, report_type: str = "final"
    ):
        """Navigate to the results page for a specific year and download ZIP files.

        Parameters
        ----------
        debug:
            Launch the browser in non headless mode for debugging.
        year:
            Target fiscal year. Defaults to the current year.
        report_type:
            Either ``"final"`` for 確報値 or ``"prompt"`` for 速報値.
        """
        if year is None:
            year = date.today().year
        self._navigate_results_page(
            str(year),
            debug,
            accept_downloads=True,
            item="results",
            report_type=report_type,
        )
        # Download all ZIP files listed on the selected year page for the
        # specified report type. Both the "final" (確報値) and "prompt"
        # (速報値) pages expose ZIP links, so handle them uniformly.
        self._download_year_zips(str(year))
        # Extract the downloaded ZIP files and remove the archives
        self._extract_downloaded_zips("zip")
        # Convert extracted CSV files from Shift-JIS to UTF-8
        self._convert_csv_encoding("zip")
        if debug:
            print(f"Navigated to: {self.page.url}")
        return self.page

    # ----- Direct download methods -----

    def fetch_results_page(self) -> str:
        """Return HTML of the results page."""
        r = self.session.get(self.results_page, verify=False)
        r.raise_for_status()
        return r.text

    def parse_links(
        self, html: str, year: str | None = None, report_type: str = "final"
    ) -> list[str]:
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

    def download_files(
        self, links: list[str], out_dir: str = "zip", overwrite: bool = True
    ) -> None:
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

    def results_direct(
        self, debug: bool = False, year: int | None = None, report_type: str = "final"
    ) -> None:
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
        # Restrict search to the table row that corresponds to the target year
        row = self.page.locator(f'tr:has-text("{year}年度")')
        links = row.locator('a[href$=".zip"]')
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

    def _extract_zip(self, path: str, remove_archive: bool = True) -> None:
        """Extract a ZIP file to a folder with the same base name."""
        extract_dir = os.path.splitext(path)[0]
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(extract_dir)
            print(f"Extracted: {path} -> {extract_dir}")
        except Exception as e:
            print(f"Failed to extract {path}: {e}")
            return
        if remove_archive:
            try:
                os.remove(path)
            except Exception as e:
                print(f"Failed to remove {path}: {e}")

    def _extract_downloaded_zips(self, directory: str = "zip") -> None:
        """Extract all ZIP files in the given directory."""
        if not os.path.isdir(directory):
            return
        for filename in os.listdir(directory):
            if filename.lower().endswith(".zip"):
                self._extract_zip(os.path.join(directory, filename))

    def _convert_csv_encoding(
        self, directory: str = "zip", src_enc: str = "shift_jis", dst_enc: str = "utf-8"
    ) -> None:
        """Recursively convert CSV files from ``src_enc`` to ``dst_enc``."""
        if not os.path.isdir(directory):
            return
        for root, _, files in os.walk(directory):
            for name in files:
                if name.lower().endswith(".csv"):
                    path = os.path.join(root, name)
                    try:
                        with open(path, "r", encoding=src_enc, errors="ignore") as f:
                            data = f.read()
                        with open(path, "w", encoding=dst_enc) as f:
                            f.write(data)
                        print(f"Converted: {path}")
                    except Exception as e:
                        print(f"Failed to convert {path}: {e}")

    def close_session(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def main():
    scraper = EPRX()
    # Example usage: navigate to the latest fiscal year's results page
    # and download all available ZIP files. "final" downloads 確報値 while
    # "prompt" downloads 速報値.
    scraper.results(debug=True, year=date.today().year, report_type="final")
    scraper.close_session()


if __name__ == "__main__":
    main()
