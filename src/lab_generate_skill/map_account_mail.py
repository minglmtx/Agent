"""Native Rails mail delivery to an instance-local inbox, with strict link selection.

This adapter never creates users or confirmation tokens. Only links emitted by
the site's actual mailer are eligible for the native confirmation form.
"""
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html import unescape
from pathlib import Path
import hashlib
import re
from urllib.parse import parse_qs, unquote, urlsplit

from .local_mail_capture import prepare


def install(frontend_state):
    state = Path(frontend_state)
    initializer = state / 'app/config/initializers/zz_local_account_mail.rb'
    if initializer.exists():
        raise ValueError('Local mail adapter already installed')
    outbox = prepare(state)
    # Publish only complete MIME messages. The async mail job may overlap reads.
    script = state / 'capture-mail.sh'
    script.write_text('''#!/bin/sh
set -eu
umask 077
message=$(mktemp /state/mail-outbox/.pending-XXXXXXXX)
trap 'rm -f -- "$message"' EXIT HUP INT TERM
cat > "$message"
mv -- "$message" "/state/mail-outbox/message-${message##*/}"
''')
    initializer.write_text('''# Instance-local delivery; genuine native mail content and tokens.
ActionMailer::Base.delivery_method = :sendmail
ActionMailer::Base.sendmail_settings = { :location => "/state/capture-mail.sh", :arguments => "-i" }
ActionMailer::Base.perform_deliveries = true
ActionMailer::Base.raise_delivery_errors = true
''')
    return outbox


def confirmation_from_message(payload, *, recipient, display_name, origin):
    """Return one exact native confirmation link, or reject the message.

    Caller provides the declared account and this instance's actual origin.
    Neither foreign hosts nor a different recipient/account may be substituted.
    """
    msg = BytesParser(policy=policy.default).parsebytes(payload)
    recipients = {address.casefold() for _, address in getaddresses(msg.get_all('To', []))}
    if recipients != {recipient.casefold()}:
        raise ValueError('Message recipient mismatch')
    target = urlsplit(origin)
    if target.scheme not in ('http', 'https') or not target.netloc or target.username or target.password:
        raise ValueError('Invalid instance origin')
    links = set()
    for part in msg.walk():
        if part.get_content_type() not in ('text/plain', 'text/html') or part.get_content_disposition() == 'attachment':
            continue
        text = unescape(part.get_content())
        for value in re.findall(r'https?://[^\s<>"\x27]+', text):
            url = urlsplit(value)
            query = parse_qs(url.query, keep_blank_values=True)
            if (url.scheme, url.netloc) != (target.scheme, target.netloc) or url.fragment:
                continue
            if unquote(url.path) != '/user/' + display_name + '/confirm':
                continue
            tokens = query.get('confirm_string', [])
            if len(tokens) == 1 and tokens[0] and set(query) == {'confirm_string'}:
                links.add(value)
    if len(links) != 1:
        raise ValueError('Expected one unambiguous local account confirmation URL')
    return {'url': links.pop(), 'message_sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
