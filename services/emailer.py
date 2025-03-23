import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from services.data_manager import data_manager
from services.logger_service import logger


class EmailService:
    """Sends reports via email with PDF attachments"""

    def __init__(self, sender_email: str, sender_password: str):
        """
        Initializes the EmailService with sender's credentials.

        Args:
            sender_email (str): Sender's Gmail address.
            sender_password (str): Sender's Gmail password or app password.
        """
        self.sender_email = sender_email
        self.sender_password = sender_password

    def send_email(self, recipient_emails: list, subject: str, message_body: str, attachment_paths: list = None):
        """
        Sends an email with optional attachments to multiple recipients.

        Args:
            recipient_emails (list): List of recipient email addresses.
            subject (str): Email subject.
            message_body (str): Email body.
            attachment_paths (list, optional): List of paths to files to attach.
        """
        # Set up the email structure
        message = MIMEMultipart()
        message['From'] = self.sender_email
        message['To'] = ", ".join(recipient_emails)  # Join the recipient emails with a comma
        message['Subject'] = subject

        # Attach the message body
        message.attach(MIMEText(message_body, 'plain'))

        # Attach the files if specified
        if attachment_paths:
            for attachment_path in attachment_paths:
                if os.path.isfile(attachment_path):
                    with open(attachment_path, 'rb') as attachment:
                        mime_base = MIMEBase('application', 'octet-stream')
                        mime_base.set_payload(attachment.read())
                    encoders.encode_base64(mime_base)
                    mime_base.add_header(
                        'Content-Disposition',
                        f'attachment; filename={os.path.basename(attachment_path)}'
                    )
                    message.attach(mime_base)

        # Send the email via Gmail's SMTP server
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
                logger.info(f"Email sent to {', '.join(recipient_emails)} successfully.")
        except Exception as e:
            logger.exception(f"Failed to send email: {e}")


# Initialize the EmailService
email_service = EmailService(sender_email='aycf.scanner@gmail.com', sender_password='paez ybiz hdcb nyrw')

ROUNDTRIP_SUBJECT = "Round Trip: Wizz Air Flights Report!"

ONEWAY_MESSAGE_BODY = f"""
Hey there, Captain ✈️

Your personalized WizzAYCF flight report is ready and attached!  
We scraped, sorted, and sliced through WizzAir’s system—so you don’t have to.

Now it’s your turn to take off 🚀  
Happy travels!

– The Tatweer Ground Crew 🛠️

WhatsApp: https://chat.whatsapp.com/CHvgbPvqRcbJS0E6D4O8ka
App: https://aycf-flightfinder.tatweer.network/
Tatweer-Website: https://tatweer.network/
"""
ONEWAY_SUBJECT = "AYCF Flight Report! 🚀"
ATTACHMENT_PATHS = [data_manager.config.reporter.report_path]

oneway_kwargs = {
                 'subject': ONEWAY_SUBJECT,
                 'message_body': ONEWAY_MESSAGE_BODY,
                 'attachment_paths': ATTACHMENT_PATHS}

roundtrip_kwargs = {
                    'subject': ROUNDTRIP_SUBJECT,
                    'message_body': ONEWAY_MESSAGE_BODY,
                    'attachment_paths': ATTACHMENT_PATHS}

if __name__ == '__main__':
    # Send an email with a PDF attachment to multiple recipients
    email_service.send_email(
        recipient_emails=['vambire02@yahoo.com'],
        subject=SUBJECT,
        message_body=MESSAGE_BODY,
        attachment_paths=[r'C:\Users\Mohammad.Al-zoubi\Documents\projects\wizz-scraper\data\report.pdf']
    )
