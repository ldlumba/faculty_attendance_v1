import hashlib
import random

# DSA parameters (demo values)
p = 23
q = 11
g = 4

# Fixed private/public key
x = 5
y = pow(g, x, p)

def hash_record(record):
    # Hashes the attendance data before signing or verification.
    record_str = f"{record['teacher_id']}{record['date']}{record['time']}{record['action']}"
    return int(hashlib.sha256(record_str.encode()).hexdigest(), 16) % q


def sign(h):
    # Produces the demo DSA signature values r and s.
    while True:
        k = random.randint(1, q - 1)

        r = pow(g, k, p) % q
        if r == 0:
            continue

        try:
            k_inv = pow(k, -1, q)
        except ValueError:
            continue

        s = (k_inv * (h + x * r)) % q
        if s == 0:
            continue

        return r, s


def verify(record, r, s):
    # Verifies whether a stored attendance record was altered.
    if not (0 < r < q and 0 < s < q):
        return False

    h = hash_record(record)

    try:
        w = pow(s, -1, q)
    except ValueError:
        return False

    u1 = (h * w) % q
    u2 = (r * w) % q

    v = ((pow(g, u1, p) * pow(y, u2, p)) % p) % q

    return v == r
