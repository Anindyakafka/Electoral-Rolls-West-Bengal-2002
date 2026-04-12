import pandas as pd
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib3
import glob
import re
import shutil
import tempfile
from pathlib import Path
# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


DATA_ROOT = repo_root() / "data" / "raw" / "ceowestbengal"
EXCEL_FILE = DATA_ROOT / "all_booth_urls.xlsx"
LEGACY_EXCEL_FILE = DATA_ROOT / "all_booths_urls.xlsx"
OUTPUT_FOLDER = DATA_ROOT / "pdfs"
MAX_RETRIES = 3
DOWNLOAD_TIMEOUT = 30

def setup_chrome_driver():
    chrome_options = Options()
    # Remove headless mode to debug
    # chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_argument('--disable-notifications')
    
    # Set up default download preferences (will be overridden per-download)
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    download_path = str(OUTPUT_FOLDER.resolve())
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver

def wait_for_download_in_folder(folder_path, timeout=60, min_size=2000):
    start_time = time.time()
    while time.time() - start_time < timeout:
        crdownloads = glob.glob(os.path.join(folder_path, '*.crdownload'))
        if crdownloads:
            time.sleep(0.8)
            continue
        pdfs = glob.glob(os.path.join(folder_path, '*.pdf'))
        for p in pdfs:
            try:
                if os.path.getsize(p) >= min_size:
                    time.sleep(0.5)
                    return p
            except OSError:
                continue
        time.sleep(0.5)
    return None

def download_booth(driver, row):
    ac_no = row['AC No']
    ac_name = row['AC Name']
    booth_no = row['Booth No']
    url = row['URL']

    folder_path = os.path.join(OUTPUT_FOLDER, f"{ac_no} - {ac_name}")
    os.makedirs(folder_path, exist_ok=True)
    expected_file_path = os.path.join(folder_path, f"{booth_no}.pdf")

    if os.path.exists(expected_file_path) and os.path.getsize(expected_file_path) > 1000:
        return f"Skipped {booth_no}.pdf (already exists)"

    for attempt in range(1, MAX_RETRIES + 1):
        temp_dir = None
        try:
            print(f"Attempting download for booth {booth_no} (try {attempt})")

            # create a unique temp folder for this download to avoid collisions
            temp_dir = tempfile.mkdtemp(prefix=f"dl_{booth_no}_", dir=folder_path)

            # open new tab and set download folder for that tab using CDP
            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])

            # set Chrome download behavior to this temp folder
            try:
                driver.execute_cdp_cmd(
                    "Page.setDownloadBehavior",
                    {"behavior": "allow", "downloadPath": os.path.abspath(temp_dir)}
                )
            except Exception as e:
                print("Warning: failed to set CDP download behavior:", e)

            driver.get(url)

            # If server uses meta-refresh, detect and follow immediately
            try:
                page_src = driver.page_source
                m = re.search(r'url=([^"\'>]+)', page_src, flags=re.IGNORECASE)
                if m:
                    redirect_url = m.group(1).strip()
                    redirect_url = redirect_url.replace("&amp;", "&")
                    if redirect_url and redirect_url != url:
                        print("Following meta-refresh to:", redirect_url)
                        driver.get(redirect_url)
            except Exception:
                pass

            # wait for a PDF to appear in the temp folder
            downloaded = wait_for_download_in_folder(temp_dir, timeout=DOWNLOAD_TIMEOUT)
            if downloaded:
                try:
                    # move the downloaded file to the expected path, avoiding overwrite issues
                    if os.path.exists(expected_file_path):
                        # keep existing file (or optionally rename with suffix)
                        os.remove(expected_file_path)
                    shutil.move(downloaded, expected_file_path)
                    return f"Downloaded {booth_no}.pdf"
                except Exception as e:
                    print("Post-download file handling error:", e)
                    return f"Downloaded (but move failed) {downloaded}"
            else:
                print(f"Retry {attempt}: Download timeout for {booth_no}.pdf")
                if attempt == 1:
                    print(f"Page source: {driver.page_source[:500]}...")
        except Exception as e:
            print(f"Retry {attempt}: Error {booth_no}.pdf -> {e}")
        finally:
            # cleanup temp dir and close tab
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass
            if temp_dir and os.path.isdir(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

        time.sleep(3)
    return f"Failed {booth_no}.pdf after {MAX_RETRIES} retries"

def main():
    excel_path = EXCEL_FILE if EXCEL_FILE.exists() else LEGACY_EXCEL_FILE
    if not excel_path.exists():
        raise FileNotFoundError(
            f"Booth URL Excel not found. Expected one of: {EXCEL_FILE} or {LEGACY_EXCEL_FILE}"
        )

    df = pd.read_excel(excel_path)
    assemblies = df.groupby(['AC No', 'AC Name'])

    total_assemblies = len(assemblies)
    print(f"Total assemblies: {total_assemblies}\n")

    driver = setup_chrome_driver()

    try:
        for i, ((ac_no, ac_name), group) in enumerate(assemblies, 1):
            print(f"=== Assembly {i}/{total_assemblies}: {ac_no} - {ac_name} ({len(group)} booths) ===")
            assembly_start = time.time()

            for idx, row in group.iterrows():
                result = download_booth(driver, row)
                print(result)

            assembly_elapsed = time.time() - assembly_start
            print(f"Assembly {ac_no} completed in {assembly_elapsed:.2f}s\n")
            time.sleep(5)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
