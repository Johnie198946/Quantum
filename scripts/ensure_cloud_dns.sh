#!/usr/bin/env bash
# Tailscale's CGNAT INPUT drop overlaps Alibaba DNS; allow only established DNS replies.
set -euo pipefail

if [[ $# -gt 1 || (${1:-} != "" && ${1:-} != "remove") ]]; then
  echo "usage: $0 [remove]" >&2
  exit 2
fi

rules=()
for address in 100.100.2.136 100.100.2.138; do
  for protocol in udp tcp; do
    rules+=("-i eth0 -s $address/32 -p $protocol --sport 53 -m conntrack --ctstate ESTABLISHED -m comment --comment quantum-cloud-dns -j ACCEPT")
  done
done

complete=true
for rule in "${rules[@]}"; do
  read -r -a args <<< "$rule"
  if ! iptables -w 5 -C INPUT "${args[@]}" 2>/dev/null; then complete=false; fi
done
leading=$(iptables -w 5 -S INPUT | head -n 5 | grep -Ec -- '--comment "?quantum-cloud-dns"?( |$)' || true)
if [[ ${1:-} != remove && $complete == true && $leading == 4 ]]; then exit 0; fi

for rule in "${rules[@]}"; do
  read -r -a args <<< "$rule"
  while iptables -w 5 -C INPUT "${args[@]}" 2>/dev/null; do
    iptables -w 5 -D INPUT "${args[@]}"
  done
  if [[ ${1:-} != remove ]]; then iptables -w 5 -I INPUT 1 "${args[@]}"; fi
done
