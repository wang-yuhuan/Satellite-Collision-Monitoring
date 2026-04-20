import requests
import json

url = "http://127.0.0.1:8000/api/socrates"

payload = {
    "sat_id": 49256,
    "start_time": "2026-03-08",
    "end_time": "2026-03-09"
}

print("正在发送请求...")
response = requests.post(url, json=payload)

# 打印格式化后的结果
print(json.dumps(response.json(), indent=2, ensure_ascii=False))