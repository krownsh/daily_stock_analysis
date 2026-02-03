import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_twse_resp():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    url = "https://www.twse.com.tw/exchangeReport/T86?response=json&date=20240201&selectType=ALL"
    resp = requests.get(url, headers=headers, verify=False)
    print(f"Status: {resp.status_code}")
    print(f"Text Content (First 200 chars): {resp.text[:200]}")

if __name__ == "__main__":
    check_twse_resp()
