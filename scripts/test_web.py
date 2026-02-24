"""Quick API test for the web server."""
import urllib.request
import json

BASE = "http://localhost:8000"

def test_endpoint(name, url):
    try:
        data = json.loads(urllib.request.urlopen(url).read())
        if isinstance(data, list):
            print(f"  [OK] {name}: {len(data)} items")
        elif isinstance(data, dict):
            keys = list(data.keys())[:5]
            print(f"  [OK] {name}: keys={keys}")
        return data
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return None

def test_page(name, url):
    try:
        resp = urllib.request.urlopen(url)
        html = resp.read().decode("utf-8")
        print(f"  [OK] {name}: {len(html)} bytes, status={resp.status}")
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")

print("=== API Endpoints ===")
cases = test_endpoint("GET /api/cases", f"{BASE}/api/cases")
results = test_endpoint("GET /api/results", f"{BASE}/api/results")

if cases and len(cases) > 0:
    cid = cases[0]["id"]
    test_endpoint(f"GET /api/case/{cid}", f"{BASE}/api/case/{cid}")

if results and len(results) > 0:
    rname = results[0]["name"]
    test_endpoint(f"GET /api/results/{rname}", f"{BASE}/api/results/{rname}")

print("\n=== HTML Pages ===")
test_page("GET / (Problems)", f"{BASE}/")
test_page("GET /status", f"{BASE}/status")
test_page("GET /submit", f"{BASE}/submit")

if cases and len(cases) > 0:
    test_page(f"GET /problem/{cases[0]['id']}", f"{BASE}/problem/{cases[0]['id']}")

print("\nAll tests done!")
