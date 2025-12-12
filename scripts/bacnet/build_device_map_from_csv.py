import csv
import json
import os

from collections import defaultdict

# Read the CSV file
data = defaultdict(lambda: defaultdict(list))
for root, dirs, files in os.walk('./scan_results'):
    for filename in files:
        filename = f"{root}/{filename}"
        bbmd_address = filename.split('-')[2]
        with open(filename, 'r') as file_object:
            reader = csv.DictReader(file_object)
            for row in reader:
                network_number = row['address'].split(':')[0] if '.' not in row['address'] else None
                if network_number is None:
                    continue
                data[bbmd_address][network_number].append(f"{row['address']}-{row['device_id']}")
with open("device_map.json", "w") as file_object:
    file_object.write(json.dumps(data, indent=4))