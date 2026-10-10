"""Exercise rule ordering, idempotence and rollback without modifying the host firewall."""
import json
import os
from pathlib import Path
import subprocess


def test_dns_guard_reorders_only_its_rules_and_can_roll_back(tmp_path):
    state = tmp_path / "rules.json"
    original = [["-j", "ts-input"], ["-j", "ufw-before-input"]]
    state.write_text(json.dumps(original))
    binary = tmp_path / "iptables"
    binary.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ["DNS_TEST_RULES"])
rules = json.loads(p.read_text())
a = sys.argv[1:]
assert a[:2] == ["-w", "5"]
a = a[2:]
assert a[1] == "INPUT"
if a[0] == "-S":
    print("-P INPUT DROP")
    for r in rules: print("-A INPUT " + " ".join('"' + x + '"' if x == "quantum-cloud-dns" else x for x in r))
elif a[0] == "-C":
    sys.exit(0 if a[2:] in rules else 1)
elif a[0] == "-D":
    rules.remove(a[2:])
elif a[0] == "-I":
    assert a[2] == "1"
    rules.insert(0, a[3:])
else: raise AssertionError(a)
p.write_text(json.dumps(rules))
''')
    binary.chmod(0o755)
    script = Path(__file__).resolve().parents[1] / "scripts/ensure_cloud_dns.sh"
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "DNS_TEST_RULES": str(state)}

    def run(*args):
        subprocess.run(["bash", str(script), *args], env=env, check=True)
        return json.loads(state.read_text())

    added = run()
    assert added[4:] == original
    assert len(added) == 6
    for rule in added[:4]:
        assert "ESTABLISHED" in rule and "eth0" in rule
        assert rule[rule.index("--sport") + 1] == "53"
        assert rule[rule.index("-s") + 1] in {"100.100.2.136/32", "100.100.2.138/32"}
    assert run() == added
    # Simulate Tailscale moving its jump ahead of our existing exceptions.
    state.write_text(json.dumps([original[0], *added[:4], original[1]]))
    assert run() == added
    assert run("remove") == original
    assert run("remove") == original
    assert subprocess.run(["bash", str(script), "unexpected"], env=env, capture_output=True).returncode == 2
