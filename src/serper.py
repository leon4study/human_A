import http.client
import json

conn = http.client.HTTPSConnection("google.serper.dev")
payload = json.dumps({"q": "trump"})
headers = {
    "X-API-KEY": "d0745068cf88617e56823916e121b9fd0efa47d4",
    "Content-Type": "application/json",
}
conn.request("POST", "/search", payload, headers)
res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
