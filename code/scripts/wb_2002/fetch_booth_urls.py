import requests
from bs4 import BeautifulSoup
import pandas as pd
import base64
import time
from pathlib import Path

BASE_URL = "https://ceowestbengal.nic.in"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


EXCEL_FILE = repo_root() / "data" / "raw" / "ceowestbengal" / "all_booth_urls.xlsx"

def get_districts():
    url = f"{BASE_URL}/roll_dist"
    res = requests.get(url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    districts = []
    for a in soup.find_all("a", href=True):
        href = a['href']
        # Only real district links
        if "\\Roll_ac\\" in href:
            district_name = a.text.strip()
            district_link = BASE_URL + href.replace("\\", "/")  # fix backslashes
            districts.append((district_name, district_link))
    return districts

def get_assemblies(district_link):
    res = requests.get(district_link)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    assemblies = []
    for tr in soup.find_all("tr")[1:]:  # skip header
        tds = tr.find_all("td")
        if len(tds) >= 2:
            a_tag = tds[1].find("a")
            if a_tag and "\\Roll_ps\\" in a_tag['href']:
                ac_no = tds[0].text.strip()
                ac_name = a_tag.text.strip()
                ac_link = BASE_URL + a_tag['href'].replace("\\", "/")
                assemblies.append((ac_no, ac_name, ac_link))
    return assemblies

def get_booths(ac_no, ac_name, ac_link):
    res = requests.get(ac_link)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    booths = []
    for tr in soup.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) >= 3:
            booth_no = tds[0].text.strip()
            booth_name = tds[1].text.strip()
            a_tag = tds[2].find("a")
            if a_tag and "onclick" in a_tag.attrs:
                onclick = a_tag['onclick']
                parts = onclick.split("'")
                acId = parts[1]
                filename = parts[3]
                encoded_key = base64.b64encode(filename.encode()).decode()
                pdf_url = f"{BASE_URL}/RollPDF/GetDraft?acId={acId}&key={encoded_key}"
                booths.append((booth_no, booth_name, pdf_url))
    return booths

def main():
    all_data = []
    districts = get_districts()
    print(f"Found {len(districts)} districts\n")

    for d_index, (district_name, district_link) in enumerate(districts, 1):
        print(f"[{d_index}/{len(districts)}] Processing district: {district_name}")
        try:
            assemblies = get_assemblies(district_link)
        except Exception as e:
            print(f"  Error fetching assemblies: {e}")
            continue

        for a_index, (ac_no, ac_name, ac_link) in enumerate(assemblies, 1):
            print(f"  [{a_index}/{len(assemblies)}] Assembly {ac_no} - {ac_name}")
            try:
                booths = get_booths(ac_no, ac_name, ac_link)
            except Exception as e:
                print(f"    Error fetching booths: {e}")
                continue

            for booth_no, booth_name, pdf_url in booths:
                all_data.append({
                    "District": district_name,
                    "AC No": ac_no,
                    "AC Name": ac_name,
                    "Booth No": booth_no,
                    "Booth Name": booth_name,
                    "URL": pdf_url
                })

            print(f"    Collected {len(booths)} booths for Assembly {ac_no}")
        time.sleep(1)  # polite delay

    EXCEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_data)
    df.to_excel(EXCEL_FILE, index=False)
    print(f"\n✅ All booth URLs saved to {EXCEL_FILE}")

if __name__ == "__main__":
    main()
