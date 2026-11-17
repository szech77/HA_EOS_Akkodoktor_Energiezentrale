"""Scanner fixtures only; never execute this file."""
import builtins
import ssl
import subprocess
import requests
import json

# ruleid: eos.python.subprocess-shell
subprocess.run(command, shell=True)
# ok: eos.python.subprocess-shell
subprocess.run(['git', 'status'], check=True, shell=False)
# ruleid: eos.python.tls-verification-disabled
requests.get('https://device.example', verify=False)
# ok: eos.python.tls-verification-disabled
requests.get('https://device.example', verify=True)
# ruleid: eos.python.unverified-tls-context
ssl._create_unverified_context()
# ok: eos.python.unverified-tls-context
ssl.create_default_context()
# ruleid: eos.python.dynamic-code
eval(expression)
# ruleid: eos.python.dynamic-code
builtins.exec(expression)  # nosemgrep: eos.python.dynamic-code
# ok: eos.python.dynamic-code
json.loads(expression)
