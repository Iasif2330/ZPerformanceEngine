import yaml
import sys
import json

with open(sys.argv[1], "r") as f:
    data = yaml.safe_load(f)

print(json.dumps(data))