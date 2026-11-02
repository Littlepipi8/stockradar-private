"""Email alerts for newly observed daily signals (deduplicated using committed state)."""
import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from scanner import OUT

STATE = Path(__file__).resolve().parent / 'data' / 'alert_state.json'

def notify():
    payload = json.loads(OUT.read_text())
    if payload['scanned'] < max(1, int(payload['universe_size']*.8)):
        raise RuntimeError('Insufficient coverage; not alerting')
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    active = {r['ticker']: f"{r['date']}:{r['signal']}" for r in payload['results'] if r['signal'] != 'NONE'}
    fresh = [r for r in payload['results'] if r['ticker'] in active and previous.get(r['ticker']) != active[r['ticker']]]
    # Do not mark alerts as sent until email succeeds.
    if fresh:
        required = ['SMTP_HOST','SMTP_PORT','SMTP_USER','SMTP_PASSWORD','ALERT_EMAIL_TO']
        missing = [k for k in required if not os.getenv(k)]
        if missing:
            print('Email not configured; skipping notification. Missing: ' + ', '.join(missing))
            return
        message = EmailMessage()
        message['Subject'] = f"StockRadar: {len(fresh)} new daily signal(s)"
        message['From'] = os.getenv('ALERT_EMAIL_FROM', os.environ['SMTP_USER'])
        message['To'] = os.environ['ALERT_EMAIL_TO']
        message.set_content('Daily StockRadar signals (research only):\n\n' + '\n'.join(
            f"{r['ticker']} | {r['signal']} | Close ${r['close']} | Support ${r['support']} | Distance {r['distance_pct']}% | Date {r['date']}"
            for r in fresh) + '\n\nNote: signals are heuristic and not trading advice.')
        with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ['SMTP_PORT']), timeout=30) as smtp:
            smtp.starttls()
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
        print(f'Sent {len(fresh)} alerts')
    else:
        print('No new alerts')
    STATE.write_text(json.dumps(active, indent=2), encoding='utf-8')

if __name__ == '__main__': notify()
