"""Bounded native account/session readouts without login or confirmation actions."""
import json
from urllib.parse import urlsplit


def account_record(site, email):
    if not isinstance(email, str) or not email or len(email) > 320:
        raise ValueError('Bounded target email required')
    literal = email.replace("'", "''")
    text = site.app_sql("SELECT row_to_json(x) FROM (SELECT id,email,display_name,status,email_valid "
                        "FROM users WHERE email='" + literal + "') x;").strip()
    return json.loads(text) if text else None


def account_snapshot(site, email):
    # Exceptions propagate; a failed SQL request never becomes a missing account.
    return dict(captured=True, target=account_record(site, email))


def session_identity(context, origin):
    """Read the terminated actor's cookies through a separate native settings tab.

    This does not submit a form, consume confirmation mail, or authenticate a
    new session. The actual resulting URL and status qualify the response.
    """
    page = context.new_page()
    try:
        response = page.goto(origin+'/account/edit', wait_until='domcontentloaded', timeout=20000)
        form = page.locator('#accountForm')
        found = form.count() == 1
        return dict(url=page.url, path=urlsplit(page.url).path,
                    http_status=response.status if response else None,
                    native_settings_form=found,
                    email=form.locator('input[name="user[email]"]').input_value() if found else None,
                    display_name=form.locator('input[name="user[display_name]"]').input_value() if found else None)
    finally:
        page.close()
