from datetime import date
import sys
from eprx_scraper import EPRX

if __name__ == "__main__":
    if len(sys.argv) > 2:
        print("Usage: python run_eprx_results.py [YYYY]")
        sys.exit(1)

    if len(sys.argv) == 2:
        try:
            fiscal_year = int(sys.argv[1])
        except ValueError:
            print("Year must be a 4-digit number, e.g. 2024")
            sys.exit(1)
    else:
        fiscal_year = date.today().year if date.today().month >= 4 else date.today().year - 1

    scraper = EPRX()
    scraper.results(debug=False, year=fiscal_year)
    scraper.close_session()

