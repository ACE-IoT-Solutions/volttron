# %%
import requests
API_URL = "https://localhost:18080"

TEST_USER = "admin"
TEST_PASSWORD = "admin"

# %%

r = requests.post(f"{API_URL}/login", json={"username": TEST_USER, "password": TEST_PASSWORD}, verify=False)
token = r.json().get("data")
# %%
assets = requests.get(f"{API_URL}/assets", headers={"Token": token}, verify=False)
print(assets.json())
# %%
endpoints = {}
for asset in assets.json():
    for endpoint in ["properties", "status", "quickview"]:
        url = f"{API_URL}/assets/{asset}/{endpoint}"
        data = requests.get(url, headers={"Token": token}, verify=False)
        if data.status_code == 200:
            endpoints[url] = data.json()
        else:
            endpoints[url] = data.text
with open("endpoints.json", "w") as f:
    import json
    json.dump(endpoints, f, indent=4)
# %%
with open("assets.json", "w") as f:
    json.dump({f"{API_URL}/assets": assets.json()}, f, indent=4)
# %%
