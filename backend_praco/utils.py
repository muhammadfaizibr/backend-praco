import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders


def send_email(subject, body, receiver_email, media=False, media_path=None):
    """
    Sends an email with the specified subject and body to the receiver.
    Optionally attaches a media file if provided.
    """
    sender_email = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")

    # Create MIME message
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = receiver_email

    # Professional HTML email template
    html = f"""\
    <html>
    <body>
        <p>
        Dear Recipient,<br><br>
        
        {body}<br><br>
        
        Best regards,<br>
        Praco
        </p>
    </body>
    </html>
    """

    # Attach HTML content
    message.attach(MIMEText(html, "html"))

    # Attach media file if provided
    if media and media_path:
        try:
            with open(media_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(media_path)}')
            message.attach(part)
        except FileNotFoundError:
            raise FileNotFoundError(f"Attachment file not found: {media_path}")

    # Send email using SMTP
    try:
        # Use a secure SSL context
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.connect(smtp_host, smtp_port)  # Explicitly connect to the server
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message.as_string())
    except smtplib.SMTPException as e:
        raise Exception(f"Failed to send email: {str(e)}")

from email import encoders
from rest_framework_simplejwt.tokens import RefreshToken
def get_tokens_for_user(user):
    """
    Generates JWT refresh and access tokens for the given user.
    """
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }