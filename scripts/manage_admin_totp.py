"""Provision, rotate, or revoke one admin's personal TOTP secret.

Replaces the single ADMIN_TOTP_SECRET shared by every admin with one
secret per admin email (see models/admin_totp.py). An email with no row
here still falls back to the legacy shared secret, so this is opt-in --
run `set` for an admin whenever you want to give them their own code
independent of everyone else's.

Usage:
    python scripts/manage_admin_totp.py list
    python scripts/manage_admin_totp.py set admin@example.com --generate
    python scripts/manage_admin_totp.py set admin@example.com --secret JBSWY3DPEHPK3PXP...
    python scripts/manage_admin_totp.py remove admin@example.com

`set --generate` prints the raw Base32 secret and an otpauth:// URI --
hand both to the admin out-of-band (Signal/1Password/etc.), the same
trust model already used for distributing the legacy shared secret. The
admin pastes the secret (or a QR made from the URI) into any RFC 6238
authenticator app.
"""

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "web" / "backend"))


def _generate_secret_base32():
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _otpauth_uri(email, secret_base32):
    from urllib.parse import quote

    label = quote(f'FlowMate:{email}')
    return f'otpauth://totp/{label}?secret={secret_base32}&issuer=FlowMate&digits=6&period=30'


def cmd_list(_args):
    from models import admin_totp
    from config import Config

    provisioned = set(admin_totp.list_emails())
    allowlisted = sorted(Config.ADMIN_EMAILS)
    if not allowlisted:
        print('ADMIN_EMAILS is not configured -- nothing to list.')
        return
    for email in allowlisted:
        status = 'personal secret' if email in provisioned else 'legacy shared secret (fallback)'
        print(f'{email}: {status}')
    extra = provisioned - set(allowlisted)
    for email in sorted(extra):
        print(f'{email}: personal secret configured, but NOT in ADMIN_EMAILS (inert)')


def cmd_set(args):
    from models import admin_totp
    from routes.admin import _decode_totp_secret

    email = args.email.strip().lower()
    if args.generate:
        secret_base32 = _generate_secret_base32()
    elif args.secret:
        secret_base32 = args.secret.strip().upper()
    else:
        print('Provide --generate or --secret BASE32', file=sys.stderr)
        sys.exit(1)

    _decode_totp_secret(secret_base32)  # raises ValueError if not usable

    admin_totp.set_secret(email, secret_base32)
    print(f'Secret set for {email}.')
    if args.generate:
        print(f'  secret:  {secret_base32}')
        print(f'  otpauth: {_otpauth_uri(email, secret_base32)}')
        print('Hand these to the admin out-of-band; this is the only time they are printed.')


def cmd_remove(args):
    from models import admin_totp

    email = args.email.strip().lower()
    admin_totp.remove_secret(email)
    print(f'Personal secret removed for {email} (falls back to the legacy shared secret, if configured).')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('list', help="Show which admins have a personal secret vs. the shared fallback").set_defaults(func=cmd_list)

    set_parser = subparsers.add_parser('set', help='Provision or rotate one admin\'s personal secret')
    set_parser.add_argument('email')
    set_parser.add_argument('--generate', action='store_true', help='Generate a fresh random secret')
    set_parser.add_argument('--secret', help='Use this exact Base32 secret instead of generating one')
    set_parser.set_defaults(func=cmd_set)

    remove_parser = subparsers.add_parser('remove', help='Revoke one admin\'s personal secret')
    remove_parser.add_argument('email')
    remove_parser.set_defaults(func=cmd_remove)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
