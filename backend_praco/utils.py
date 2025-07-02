from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import logging

logger = logging.getLogger(__name__)

def send_email(subject, body, receiver, is_html=True, attachments=None):
    """
    Universal email sending function for Praco Packaging with a professional HTML template.

    Args:
        subject (str): The subject of the email
        body (str): The main content of the email (without footer)
        receiver (str): The recipient's email address
        is_html (bool): If True, sends the body as HTML content (default: True)
        attachments (list): List of tuples [(filename, content, mimetype), ...] for email attachments

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # HTML template with Tailwind CSS for professional, clean, minimalist design
        html_body = (
            f'<!DOCTYPE html>'
            f'<html lang="en">'
            f'<head>'
            f'  <meta charset="UTF-8">'
            f'  <meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'  <title>{subject}</title>'
            f'  <script src="https://cdn.tailwindcss.com"></script>'
            f'</head>'
            f'<body class="bg-gray-100 font-sans">'
            f'  <div class="max-w-2xl mx-auto bg-white p-8 my-8 rounded-lg shadow-sm">'
            f'    <div class="mb-6">'
            f'      <img src="http://127.0.0.1:8000/static/images/logo.svg" alt="Praco Packaging Logo" class="h-12">'
            f'    </div>'
            f'    <div class="text-gray-700 leading-relaxed">'
            f'      {body}'
            f'    </div>'
            f'    <div class="mt-8 border-t pt-4 text-gray-600">'
            f'      <p>Please contact our support team at <a href="mailto:support@pracopackaging.co.uk" class="text-blue-600 hover:underline">support@pracopackaging.co.uk</a>.</p>'
            f'      <p class="mt-4">Best regards,<br>The Praco Packaging Team<br>Praco Packaging Supplies Ltd.</p>'
            f'    </div>'
            f'  </div>'
            f'</body>'
            f'</html>'
        )

        email_message = EmailMessage(
            subject=f"[Praco Packaging] {subject}",
            body=html_body if is_html else body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[receiver]
        )
        if is_html:
            email_message.content_subtype = 'html'
        if attachments:
            for filename, content, mimetype in attachments:
                email_message.attach(filename, content, mimetype)
        email_message.send(fail_silently=False)
        logger.info(f"Email sent successfully to {receiver} with subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {receiver} with subject {subject}: {str(e)}")
        return False

def get_tokens_for_user(user):
    """
    Generates JWT refresh and access tokens for the given user.
    """
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }