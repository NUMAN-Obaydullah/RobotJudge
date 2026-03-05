import requests
import json

url = 'http://localhost:8000/api/submit'
file_path = 'submissions/flaky_solver.py'

with open(file_path, 'rb') as f:
    files = {'solver': f}
    data = {'seeds': '0..2', 'time_limit': 15000}
    response = requests.post(url, files=files, data=data)

print(f"Status Code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
