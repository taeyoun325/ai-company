"""빌드 때 '믿는 프록시' 대역 목록을 만든다 (DAY 27).

Firebase Hosting 이 Cloud Run 에 붙을 때 쓰는 주소는 **구글 서비스 대역**
(goog.json)에 있다. 거기서 **GCP 고객이 빌릴 수 있는 대역**(cloud.json)을
뺀다 — 빼지 않으면 공격자가 GCP VM 에서 접속해 자기 주소를 '프록시'로
믿게 만들고, 왼쪽의 위조값이 실제 주소로 뽑힌다.

    python google_proxies.py goog.json cloud.json > /etc/trusted-proxies.txt
"""
import ipaddress
import json
import sys


def prefixes(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return [ipaddress.ip_network(p.get("ipv4Prefix") or p["ipv6Prefix"])
            for p in d["prefixes"]]


def main(goog: str, cloud: str) -> None:
    customer = prefixes(cloud)
    out = []
    for net in prefixes(goog):
        parts = [net]
        for c in customer:
            if c.version != net.version:
                continue
            nxt = []
            for p in parts:
                if c.subnet_of(p):
                    nxt.extend(p.address_exclude(c))
                elif p.subnet_of(c):
                    continue
                else:
                    nxt.append(p)
            parts = nxt
        out.extend(parts)
    print(f"# goog.json - cloud.json ({len(out)} ranges)")
    for n in ipaddress.collapse_addresses([n for n in out if n.version == 4]):
        print(n)
    for n in ipaddress.collapse_addresses([n for n in out if n.version == 6]):
        print(n)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
