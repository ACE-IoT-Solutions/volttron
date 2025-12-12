import csv
import requests
import os

SCAN_RESULTS_DIR = "/var/lib/volttron/scripts/bacnet/scan_results/cudd"
URL = "https://manager.aceiot.cloud/api"

def build_updated_points(points, row, bbmd_address):
    for point in points:
        if row['address'] == point['bacnet_data']['device_address']:
            point['collect_config']['bbmd_address'] = bbmd_address
            points_to_upload.append(point)
    

def upload_points(points):
    i = 0
    chunk_size = 1
    while True:
        remaining_points = len(points) - i
        up = {"points": points[i:i+chunk_size]}
        result = requests.post(f"{URL}/points", json=up, headers=headers)
        print(f"uploaded result: {result.status_code}: {remaining_points=}")
        i += chunk_size
        if i >= len(points):
            break

headers = {"Authorization": f"Bearer {os.environ['ACE_JWT']}"}
points_list = []
per_page = 5000
page = 1
while True:
    request = requests.get(f"{URL}/configured_points", headers=headers, params={"per_page": per_page, "page": page})
    print(f"Requesting page {page}... {request.status_code}")
    page += 1
    points = request.json()['items']
    # print(points)
    points_list.append(points)
    if len(points) < per_page:
        break

# print(points_list[0][0])

points_to_upload = []
for path, dirs, files in os.walk(SCAN_RESULTS_DIR):
    # print(path, dirs, files)
    for file in files:
        if file.endswith('.csv'):
            bbmd_address = file.split('-')[2]
            with open(os.path.join(path, file)) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    device_address = row['address']
                    build_updated_points(points_list[0], row, bbmd_address)
                    # requests.post('http://localhost:8080/api/bacnet/points', json=row)
        upload_points(points_to_upload)
        points_to_upload = []

# print(points_to_upload[0])
# upload_points(points_to_upload)