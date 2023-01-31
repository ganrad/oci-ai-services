import requests
import json

endpoint = 'http://127.0.0.1:8080/score'
model_id = 'ocid1.datasciencemodel.oc1.phx.amaaaaaaor7l3jiaupzleckeogmotcnpjhdrmyejnfuk2eshmvqi4ytr6o2a'

print("POST to model-server url", endpoint)

# Read json file to a dict
with open('raw-data.json','r') as f:
    payload = json.load(f)

# Print the payload ~ dict
print('REQUEST Json:')
print(json.dumps(payload,indent=4,sort_keys=True))

headers = {'Content-Type':'application/json'}
params = {'model_id': model_id}

# json param takes a dict
# resp = requests.post(endpoint,headers=headers,json=payload,params=params)
# OR
# data param takes a json string
resp = requests.post(endpoint,headers=headers,data=json.dumps(payload),params=params)

# Load the returned json response to a dict
result_dict = json.loads(resp.text)
print('RESPONSE Json:')
print(json.dumps(result_dict,indent=4,sort_keys=True))
