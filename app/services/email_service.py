import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.settings = get_settings()
        self.smtp_host = self.settings.smtp_host or "smtp.hostinger.com"
        self.smtp_port = self.settings.smtp_port or 465
        self.smtp_user = self.settings.smtp_user or "support@apexbooks.in"
        self.smtp_password = self.settings.smtp_password
        self.from_email = self.settings.from_email or "support@apexbooks.in"
        self.from_name = self.settings.from_name or "ApexBooks"

    def send_email(self, to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
        """Send email via SMTP."""
        if not self.smtp_password:
            logger.error("SMTP password not configured")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email

            if not text_body:
                text_body = self._html_to_text(html_body)

            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')

            msg.attach(part1)
            msg.attach(part2)

            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_email, [to_email], msg.as_string())
            server.quit()

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion."""
        import re
        text = re.sub(r'<[^>]+>', '', html)
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        return text.strip()

    def send_password_reset_email(self, to_email: str, otp: str, expiry_minutes: int = 10) -> bool:
        """Send password reset OTP email."""
        subject = "Password Reset Request - ApexBooks"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #10B981; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px 20px; background: #f9f9f9; }}
                .otp-box {{ background: white; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px; }}
                .otp {{ font-size: 32px; font-weight: bold; color: #10B981; letter-spacing: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; padding: 12px 30px; background: #10B981; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>ApexBooks</h1>
                    <p>Password Reset Request</p>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p>You have requested to reset your password for your ApexBooks account.</p>
                    
                    <div class="otp-box">
                        <p style="margin: 0; color: #666; font-size: 14px;">Your OTP is:</p>
                        <p class="otp">{otp}</p>
                        <p style="margin: 10px 0 0 0; color: #666; font-size: 12px;">
                            This OTP will expire in {expiry_minutes} minutes.
                        </p>
                    </div>

                    <p><strong>Important:</strong></p>
                    <ul>
                        <li>Do not share this OTP with anyone</li>
                        <li>Our team will never ask for your password or OTP</li>
                        <li>If you didn't request this, please ignore this email</li>
                    </ul>

                    <p style="text-align: center;">
                        <a href="https://apexbooks.in/reset-password" class="button">Reset Password</a>
                    </p>
                </div>
                <div class="footer">
                    <p>This email was sent from ApexBooks GST API Engine.</p>
                    <p>&copy; 2024 ApexBooks. All rights reserved.</p>
                    <p>If you have any questions, contact us at support@apexbooks.in</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        ApexBooks - Password Reset Request

        Hello,

        You have requested to reset your password for your ApexBooks account.

        Your OTP is: {otp}

        This OTP will expire in {expiry_minutes} minutes.

        Important:
        - Do not share this OTP with anyone
        - Our team will never ask for your password or OTP
        - If you didn't request this, please ignore this email

        Reset your password at: https://apexbooks.in/reset-password

        ---
        This email was sent from ApexBooks GST API Engine.
        © 2024 ApexBooks. All rights reserved.
        If you have any questions, contact us at support@apexbooks.in
        """

        return self.send_email(to_email, subject, html_body, text_body)

    def send_welcome_email(self, to_email: str, full_name: str, company_name: str) -> bool:
        """Send welcome email to new users."""
        subject = f"Welcome to ApexBooks, {full_name}!"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #10B981; color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px 20px; }}
                .button {{ display: inline-block; padding: 12px 30px; background: #10B981; color: white; text-decoration: none; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to ApexBooks!</h1>
                </div>
                <div class="content">
                    <p>Hi {full_name},</p>
                    <p>Welcome to <strong>ApexBooks</strong>! We're excited to have you on board.</p>
                    <p>Your company <strong>{company_name}</strong> has been successfully registered.</p>
                    
                    <p><strong>What's next?</strong></p>
                    <ul>
                        <li>Complete your business profile in Settings</li>
                        <li>Add your first customer or vendor</li>
                        <li>Create your first invoice</li>
                        <li>Explore our GST reports and analytics</li>
                    </ul>

                    <p style="text-align: center; margin-top: 30px;">
                        <a href="https://apexbooks.in/dashboard" class="button">Go to Dashboard</a>
                    </p>

                    <p>If you have any questions, our support team is here to help at support@apexbooks.in</p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 ApexBooks. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Welcome to ApexBooks!

        Hi {full_name},

        Welcome to ApexBooks! We're excited to have you on board.

        Your company {company_name} has been successfully registered.

        What's next?
        - Complete your business profile in Settings
        - Add your first customer or vendor
        - Create your first invoice
        - Explore our GST reports and analytics

        Go to Dashboard: https://apexbooks.in/dashboard

        If you have any questions, our support team is here to help at support@apexbooks.in

        ---
        © 2024 ApexBooks. All rights reserved.
        """

        return self.send_email(to_email, subject, html_body, text_body)


email_service = EmailService()
