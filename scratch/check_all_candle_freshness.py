import subprocess

script = """
import glob, json, os, datetime

now = datetime.datetime.now()
print(f"Current server time: {now}")
for f in sorted(glob.glob('/data/*/candele_*.json')):
    try:
        with open(f) as fp:
            d = json.load(fp)
        if not d:
            print(f"{f}: EMPTY")
            continue
        first_t = d[0].get('snapshotTime')
        last_t = d[-1].get('snapshotTime')
        count = len(d)
        print(f"{os.path.basename(os.path.dirname(f))}/{os.path.basename(f)}: count={count} first={first_t} last={last_t}")
    except Exception as e:
        print(f"{f}: error {e}")
"""

out = subprocess.run(['kubectl.exe', '--kubeconfig=local.yaml', '-n', 'macchinetta', 'exec', 'deployment/macchinetta-dashboard', '--', 'python3', '-c', script], capture_output=True, text=True)
print(out.stdout)
