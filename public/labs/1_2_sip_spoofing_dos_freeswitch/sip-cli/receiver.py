import hashlib
import os
import random
import re
import socket
import string
import sys
import time


SERVER_IP = os.getenv("SIP_SERVER", "10.12.0.5")
SERVER_PORT = int(os.getenv("SIP_PORT", "5060"))
SIP_DOMAIN = os.getenv("SIP_DOMAIN", SERVER_IP)
USERNAME = os.getenv("SIP_USERNAME", "1001")
PASSWORD = os.getenv("SIP_PASSWORD", "1234")
LOCAL_PORT = int(os.getenv("LOCAL_PORT", "5062"))
REGISTER_EXPIRES = int(os.getenv("REGISTER_EXPIRES", "3600"))
REGISTER_RETRY_SEC = int(os.getenv("REGISTER_RETRY_SEC", "5"))


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def rand_token(length: int = 10) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def parse_status_line(packet: str) -> int:
    first = packet.splitlines()[0] if packet else ""
    m = re.match(r"SIP/2\.0\s+(\d{3})", first)
    return int(m.group(1)) if m else 0


def parse_digest_challenge(packet: str) -> dict:
    m = re.search(r"^WWW-Authenticate:\s*Digest\s+(.+)$", packet, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return {}
    challenge = m.group(1)
    fields = {}
    for key, value in re.findall(r"(\w+)=(\"[^\"]*\"|[^,\s]+)", challenge):
        fields[key.lower()] = value.strip('"')
    return fields


def header(packet: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}:\s*(.+)$", packet, flags=re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def auth_header(challenge: dict, method: str, uri: str, nonce_count: str = "00000001") -> str:
    realm = challenge.get("realm", SIP_DOMAIN)
    nonce = challenge.get("nonce", "")
    qop = challenge.get("qop", "")

    ha1 = md5_hex(f"{USERNAME}:{realm}:{PASSWORD}")
    ha2 = md5_hex(f"{method}:{uri}")

    parts = [
        f'username="{USERNAME}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        "algorithm=MD5",
    ]

    if qop:
        qop_value = "auth" if "auth" in qop else qop.split(",")[0].strip()
        cnonce = rand_token(16)
        response = md5_hex(f"{ha1}:{nonce}:{nonce_count}:{cnonce}:{qop_value}:{ha2}")
        parts.extend([
            f"qop={qop_value}",
            f"nc={nonce_count}",
            f'cnonce="{cnonce}"',
            f'response="{response}"',
        ])
    else:
        response = md5_hex(f"{ha1}:{nonce}:{ha2}")
        parts.append(f'response="{response}"')

    opaque = challenge.get("opaque")
    if opaque:
        parts.append(f'opaque="{opaque}"')

    return "Digest " + ", ".join(parts)


def build_register(contact_ip: str, call_id: str, from_tag: str, cseq: int, auth: str | None = None) -> str:
    via_branch = f"z9hG4bK-{rand_token(12)}"
    request_uri = f"sip:{SERVER_IP}"

    lines = [
        f"REGISTER {request_uri} SIP/2.0",
        f"Via: SIP/2.0/UDP {contact_ip}:{LOCAL_PORT};rport;branch={via_branch}",
        "Max-Forwards: 70",
        f"From: <sip:{USERNAME}@{SIP_DOMAIN}>;tag={from_tag}",
        f"To: <sip:{USERNAME}@{SIP_DOMAIN}>",
        f"Call-ID: {call_id}",
        f"CSeq: {cseq} REGISTER",
        f"Contact: <sip:{USERNAME}@{contact_ip}:{LOCAL_PORT};transport=udp>",
        f"Expires: {REGISTER_EXPIRES}",
        "User-Agent: rtc-attacks-sip-cli/1.0",
        "Allow: INVITE, ACK, BYE, CANCEL, OPTIONS, MESSAGE, INFO, UPDATE, REGISTER, REFER, NOTIFY",
        "Content-Length: 0",
    ]

    if auth:
        lines.insert(-1, f"Authorization: {auth}")

    return "\r\n".join(lines) + "\r\n\r\n"


def send_register(sock: socket.socket, contact_ip: str) -> bool:
    call_id = f"{rand_token(16)}@sip-cli"
    from_tag = rand_token(10)
    cseq = 1

    req = build_register(contact_ip, call_id, from_tag, cseq)
    sock.sendto(req.encode("utf-8"), (SERVER_IP, SERVER_PORT))

    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue

        packet = data.decode("utf-8", errors="ignore")
        code = parse_status_line(packet)

        if code == 200:
            print("[CLIENT] REGISTER_OK", flush=True)
            return True

        if code in (401, 407):
            challenge = parse_digest_challenge(packet)
            cseq += 1
            request_uri = f"sip:{SERVER_IP}"
            auth = auth_header(challenge, "REGISTER", request_uri)
            req2 = build_register(contact_ip, call_id, from_tag, cseq, auth=auth)
            sock.sendto(req2.encode("utf-8"), (SERVER_IP, SERVER_PORT))
            continue

        if code:
            print(f"[CLIENT] REGISTER_RESPONSE code={code}", flush=True)

    print("[CLIENT] REGISTER_TIMEOUT", flush=True)
    return False


def extract_body(packet: str) -> str:
    marker = "\r\n\r\n"
    if marker in packet:
        return packet.split(marker, 1)[1]
    return ""


def build_message_ok(request: str) -> str:
    via = header(request, "Via")
    from_h = header(request, "From")
    to_h = header(request, "To")
    call_id = header(request, "Call-ID")
    cseq = header(request, "CSeq")

    lines = [
        "SIP/2.0 200 OK",
        f"Via: {via}",
        f"From: {from_h}",
        f"To: {to_h}",
        f"Call-ID: {call_id}",
        f"CSeq: {cseq}",
        "Content-Length: 0",
    ]
    return "\r\n".join(lines) + "\r\n\r\n"


def main() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LOCAL_PORT))
    sock.settimeout(1.0)

    contact_ip = os.getenv("SIP_CONTACT_IP", "")
    if not contact_ip:
        contact_ip = sock.getsockname()[0]
        if contact_ip == "0.0.0.0":
            contact_ip = socket.gethostbyname(socket.gethostname())

    print(f"[CLIENT] SIP CLI monitor started on {contact_ip}:{LOCAL_PORT}", flush=True)
    print(f"[CLIENT] Target server {SERVER_IP}:{SERVER_PORT} user={USERNAME}", flush=True)

    while True:
        if send_register(sock, contact_ip):
            break
        time.sleep(REGISTER_RETRY_SEC)

    last_register = time.time()

    while True:
        now = time.time()
        if now - last_register > max(REGISTER_EXPIRES - 60, 60):
            if send_register(sock, contact_ip):
                last_register = now

        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except KeyboardInterrupt:
            return 0

        packet = data.decode("utf-8", errors="ignore")

        if packet.startswith("MESSAGE "):
            msg_from = header(packet, "From")
            msg_to = header(packet, "To")
            body = extract_body(packet).strip()
            print("[INCOMING_MESSAGE] from=" + msg_from, flush=True)
            print("[INCOMING_MESSAGE] to=" + msg_to, flush=True)
            print("[INCOMING_MESSAGE] body=" + body, flush=True)

            ok = build_message_ok(packet)
            sock.sendto(ok.encode("utf-8"), addr)
            continue

        if packet.startswith("OPTIONS "):
            # Keep noise down; FreeSWITCH may probe with OPTIONS.
            continue


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[CLIENT] Fatal error: {exc}", file=sys.stderr, flush=True)
        raise
