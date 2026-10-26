"""Search several Gmail mailboxes at once for the morning brief.

Each mailbox has its own OAuth token in .secrets/token_<email>.json, all made
from the same OAuth client in .secrets/credentials.json. .secrets/ is gitignored.

    python tools/mail.py accounts
    python tools/mail.py add partnerships@5cnetwork.com
    python tools/mail.py search "newer_than:30d -from:..." [--account EMAIL] [--max 50]
"""

import argparse
import glob
import os
import sys
from email.utils import parseaddr, parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, '.secrets')
CREDS_PATH = os.path.join(SECRETS, 'credentials.json')
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def token_path(email):
    return os.path.join(SECRETS, f'token_{email}.json')


def list_accounts():
    files = glob.glob(os.path.join(SECRETS, 'token_*.json'))
    return sorted(os.path.basename(f)[len('token_'):-len('.json')] for f in files)


def service_for(email):
    path = token_path(email)
    creds = Credentials.from_authorized_user_file(path)
    if not creds.valid:
        creds.refresh(Request())
        with open(path, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def cmd_add(email):
    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
    print(f'Log in as {email} in the browser window that opens.')
    creds = flow.run_local_server(port=0)
    svc = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    actual = svc.users().getProfile(userId='me').execute()['emailAddress']
    if actual.lower() != email.lower():
        sys.exit(f'Logged in as {actual}, expected {email}. Token not saved.')
    with open(token_path(email), 'w') as f:
        f.write(creds.to_json())
    print(f'Saved token for {email}.')


def summarise(svc, owner, thread_id):
    t = svc.users().threads().get(
        userId='me', id=thread_id, format='metadata',
        metadataHeaders=['From', 'To', 'Cc', 'Subject', 'Date']).execute()
    msgs = t['messages']

    def hdr(m, name):
        for h in m['payload'].get('headers', []):
            if h['name'].lower() == name.lower():
                return h['value']
        return ''

    last = msgs[-1]
    last_from = parseaddr(hdr(last, 'From'))[1].lower()
    try:
        last_date = parsedate_to_datetime(hdr(last, 'Date')).strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError):
        last_date = ''
    owner_replied = any(parseaddr(hdr(m, 'From'))[1].lower() == owner.lower() for m in msgs)
    return {
        'account': owner,
        'thread_id': thread_id,
        'subject': hdr(msgs[0], 'Subject'),
        'first_from': hdr(msgs[0], 'From'),
        'to': hdr(last, 'To'),
        'last_from': last_from,
        'last_date': last_date,
        'messages': len(msgs),
        'last_is_owner': last_from == owner.lower(),
        'owner_replied': owner_replied,
        'snippet': last.get('snippet', '')[:160],
    }


def cmd_search(query, accounts, max_threads):
    cols = ['account', 'thread_id', 'last_date', 'messages', 'last_is_owner',
            'owner_replied', 'last_from', 'first_from', 'to', 'subject', 'snippet']
    print('\t'.join(cols))
    for email in accounts:
        try:
            svc = service_for(email)
            resp = svc.users().threads().list(userId='me', q=query, maxResults=max_threads).execute()
            for t in resp.get('threads', []):
                row = summarise(svc, email, t['id'])
                print('\t'.join(str(row[c]).replace('\t', ' ').replace('\n', ' ') for c in cols))
        except Exception as e:
            print(f'# {email}: ERROR {type(e).__name__}: {e}', file=sys.stderr)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('accounts')
    a = sub.add_parser('add')
    a.add_argument('email')
    s = sub.add_parser('search')
    s.add_argument('query')
    s.add_argument('--account', help='one mailbox; default is all')
    s.add_argument('--max', type=int, default=50)
    args = p.parse_args()

    if args.cmd == 'accounts':
        print('\n'.join(list_accounts()))
    elif args.cmd == 'add':
        cmd_add(args.email)
    else:
        cmd_search(args.query, [args.account] if args.account else list_accounts(), args.max)


if __name__ == '__main__':
    main()
