import json
with open('patches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for idx, patch in enumerate(data):
    print(f"Patch {idx}: {patch.get('Description', '')} - {patch.get('toolSummary', '')}")
