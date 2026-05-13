import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_newsletter(
    smtp_user: str,
    smtp_password: str,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"FMCG Marketing Intelligence <{smtp_user}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())
