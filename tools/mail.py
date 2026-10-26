"""Search several Gmail mailboxes at once for the morning brief.

Each mailbox has its own OAuth token in .secrets/token_<email>.json, all made
from the same OAuth client in .secrets/credentials.json. .secrets/ is gitignored.

    python tools/mail.py accounts
    python tools/mail.py add partnerships@5cnetwork.com
    python tools/mail.py search "newer_than:30d -from:..." [--account EMAIL] [--max 50]
    python tools/mail.py brief [--days 30]

brief applies per mailbox rules and prints only threads that may need Sunil.

Own inbox: threads where the last message is from someone else, or Sunil's own
ask with no reply for 48h. Mail to support@ or ai.teleradiology@ not addressed
to him only after 48h unanswered. Threads where he is only on cc show only if
the latest message names him. Bulk and auto replies are dropped.

Shared mailboxes: threads where the last real message came from outside 5C and
nobody from 5C has replied since. Bulk, auto replies and transactional senders
are dropped. support@ is handled by finance_reply_bot, so payment threads there
only show once unanswered for 48h; everything else shows straight away.
"""

import argparse
import glob
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, '.secrets')
CREDS_PATH = os.path.join(SECRETS, 'credentials.json')
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

OWN = 'sunil.kumar@5cnetwork.com'
INTERNAL_DOMAINS = ('5cnetwork.com', '5cnetwork.in', 'ask5c.in')
FINANCE_BOT_MAILBOXES = {'support@5cnetwork.com'}
TEAM_ONLY_ADDRESSES = ('support@5cnetwork.com', 'ai.teleradiology@5cnetwork.com')
PAYMENT_RE = re.compile(
    r'payment|outstanding|overdue|invoice|reminder|\bdues?\b|ledger|receipt|\butr\b|\btds\b|'
    r'remittance|statement of account|\bsoa\b|balance|\bneft\b|\brtgs\b|transfer|'
    r'suspen|blocked|unblock|unlock|acknowledg', re.I)
BULK_SENDER_RE = re.compile(
    r'no-?reply|do-?not-?reply|mailer-daemon|postmaster|notification|newsletter|alerts?@|'
    r'ticketadmin@|ecatering@|etender|calendar-notification|@google\.com$', re.I)
AUTO_REPLY_RE = re.compile(
    r'^(automatic reply|auto(matic)?[- ]?reply|out of (the )?office|auto:|undeliverable|'
    r'delivery status notification|accepted:|declined:|tentative:)', re.I)
EXCLUSIONS = (
    '-from:analytics@5cnetwork.com -from:insights@5cnetwork.com -from:support@5cnetwork.com '
    '-from:partnerships@5cnetwork.com -from:insights@ask5c.in -from:proradinsights@5cnetwork.com '
    '-subject:"Invitation:*" -from:do-not-reply@cloud.sophos.com '
    '-subject:" Assessment link and submission Instruction" -from:noreply@airindia.com '
    '-from:mailer-daemon@googlemail.com -from:policy.noreply@service.uiic.co.in')
HEADERS = ['From', 'To', 'Cc', 'Subject', 'Date', 'List-Unsubscribe', 'Precedence', 'Auto-Submitted']
BATCH_SIZE = 20


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
    creds = flow.run_local_server(port=0, login_hint=email)
    svc = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    actual = svc.users().getProfile(userId='me').execute()['emailAddress']
    if actual.lower() != email.lower():
        sys.exit(f'Logged in as {actual}, expected {email}. Token not saved.')
    with open(token_path(email), 'w') as f:
        f.write(creds.to_json())
    print(f'Saved token for {email}.')


def is_internal(addr):
    return addr.split('@')[-1] in INTERNAL_DOMAINS


def list_thread_ids(svc, query, max_threads):
    ids, token = [], None
    while len(ids) < max_threads:
        resp = svc.users().threads().list(userId='me', q=query, pageToken=token,
                                          maxResults=min(100, max_threads - len(ids))).execute()
        ids += [t['id'] for t in resp.get('threads', [])]
        token = resp.get('nextPageToken')
        if not token:
            break
    return ids


def fetch_threads(svc, thread_ids):
    """Thread metadata for many IDs, using batched HTTP requests."""
    out = {}

    def get(tid):
        return svc.users().threads().get(userId='me', id=tid, format='metadata', metadataHeaders=HEADERS)

    def done(request_id, response, exception):
        if exception is None:
            out[request_id] = response

    for i in range(0, len(thread_ids), BATCH_SIZE):
        batch = svc.new_batch_http_request(callback=done)
        for tid in thread_ids[i:i + BATCH_SIZE]:
            batch.add(get(tid), request_id=tid)
        batch.execute()
    # Gmail rejects some batched calls with 429; fetch those one at a time.
    for tid in [t for t in thread_ids if t not in out]:
        try:
            out[tid] = get(tid).execute(num_retries=3)
        except Exception as e:
            print(f'# thread {tid}: {type(e).__name__}', file=sys.stderr)
    return [out[t] for t in thread_ids if t in out]


def summarise(owner, t):
    all_msgs = t['messages']
    msgs = [m for m in all_msgs if 'DRAFT' not in m.get('labelIds', [])] or all_msgs

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
    subject = hdr(msgs[0], 'Subject')
    last_subject = hdr(last, 'Subject')
    recipients = [a.lower() for _, a in getaddresses([hdr(last, 'To'), hdr(last, 'Cc')])]
    age_h = (datetime.now(timezone.utc).timestamp() - int(last['internalDate']) / 1000) / 3600
    return {
        'account': owner,
        'thread_id': t['id'],
        'subject': subject,
        'first_from': hdr(msgs[0], 'From'),
        'to': hdr(last, 'To'),
        'last_from': last_from,
        'last_date': last_date,
        'age_h': round(age_h),
        'messages': len(msgs),
        'last_is_owner': last_from == owner.lower(),
        'owner_replied': any(parseaddr(hdr(m, 'From'))[1].lower() == owner.lower() for m in msgs),
        'draft_pending': len(msgs) < len(all_msgs),
        'last_internal': is_internal(last_from),
        'owner_addressed': owner.lower() in [a.lower() for _, a in getaddresses([hdr(last, 'To')])],
        'team_only': any(a in recipients for a in TEAM_ONLY_ADDRESSES),
        'bulk': bool(hdr(last, 'List-Unsubscribe') or hdr(last, 'Precedence').lower() in ('bulk', 'list', 'junk')
                     or BULK_SENDER_RE.search(last_from)),
        'auto': bool(AUTO_REPLY_RE.search(last_subject) or AUTO_REPLY_RE.search(subject)
                     or hdr(last, 'Auto-Submitted').lower() not in ('', 'no')),
        'payment': bool(PAYMENT_RE.search(subject + ' ' + last.get('snippet', ''))),
        'snippet': last.get('snippet', '')[:160],
    }


def own_reason(row):
    """Why a thread in Sunil's own inbox may need him, or None to skip it."""
    if row['bulk'] or row['auto']:
        return None
    if row['last_is_owner']:
        return f'your ask, no reply in {row["age_h"]}h' if row['age_h'] >= 48 else None
    if row['team_only'] and not row['owner_addressed']:
        return f'team mail, unanswered {row["age_h"]}h' if row['age_h'] >= 48 else None
    if row['owner_addressed']:
        return 'pending on you'
    return 'cc, names you' if re.search(r'\bsunil\b', row['snippet'], re.I) else None


def shared_reason(row, mailbox):
    """Why a shared mailbox thread needs Sunil, or None to skip it."""
    if row['last_internal'] or row['bulk'] or row['auto']:
        return None
    if row['payment']:
        if mailbox in FINANCE_BOT_MAILBOXES:
            return f'payment, bot has not replied in {row["age_h"]}h' if row['age_h'] >= 48 else None
        return 'payment, external, unanswered'
    return 'external, unanswered'


def emit(row, cols):
    print('\t'.join(re.sub(r'\s+', ' ', str(row[c])) for c in cols))


def cmd_brief(days, max_threads):
    cols = ['account', 'thread_id', 'reason', 'last_date', 'age_h', 'messages', 'owner_replied',
            'draft_pending', 'last_from', 'first_from', 'to', 'subject', 'snippet']
    print('\t'.join(cols))
    for email in list_accounts():
        try:
            svc = service_for(email)
            if email == OWN:
                query = f'in:inbox newer_than:{days}d {EXCLUSIONS}'
            else:
                query = f'in:inbox newer_than:{days}d ' + ' '.join(f'-from:{d}' for d in INTERNAL_DOMAINS)
            for t in fetch_threads(svc, list_thread_ids(svc, query, max_threads)):
                row = summarise(email, t)
                row['reason'] = own_reason(row) if email == OWN else shared_reason(row, email)
                if row['reason']:
                    emit(row, cols)
        except Exception as e:
            print(f'# {email}: ERROR {type(e).__name__}: {e}', file=sys.stderr)


def cmd_search(query, accounts, max_threads):
    cols = ['account', 'thread_id', 'last_date', 'messages', 'last_is_owner',
            'owner_replied', 'last_from', 'first_from', 'to', 'subject', 'snippet']
    print('\t'.join(cols))
    for email in accounts:
        try:
            svc = service_for(email)
            for t in fetch_threads(svc, list_thread_ids(svc, query, max_threads)):
                emit(summarise(email, t), cols)
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
    b = sub.add_parser('brief')
    b.add_argument('--days', type=int, default=30)
    b.add_argument('--max', type=int, default=500, help='threads per mailbox')
    args = p.parse_args()

    if args.cmd == 'accounts':
        print('\n'.join(list_accounts()))
    elif args.cmd == 'add':
        cmd_add(args.email)
    elif args.cmd == 'brief':
        cmd_brief(args.days, args.max)
    else:
        cmd_search(args.query, [args.account] if args.account else list_accounts(), args.max)


if __name__ == '__main__':
    main()
