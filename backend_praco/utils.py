from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import logging

logger = logging.getLogger(__name__)

def send_email(subject, body, receiver, is_html=False):
    """
    Universal email sending function.
    
    Args:
        subject (str): The subject of the email
        body (str): The body content of the email
        receiver (str): The recipient's email address
        is_html (bool): If True, sends the body as HTML content
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        email_message = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[receiver]
        )
        if is_html:
            email_message.content_subtype = 'html'  # Set content type to HTML
        email_message.send(fail_silently=False)
        logger.info(f"Email sent successfully to {receiver}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {receiver}: {str(e)}")
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