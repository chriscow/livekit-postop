"""
Email service for sending instruction summaries via Gmail SMTP

This module provides functionality to send discharge instruction summaries
as SMS-formatted emails using Gmail's SMTP server with app password authentication.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional
import os

logger = logging.getLogger("postop-agent")


def _translate_text_with_openai(text: str, target_language: str) -> Optional[str]:
    """
    Translate text to target language using OpenAI API
    
    Args:
        text: English text to translate
        target_language: Target language (e.g., 'Spanish', 'French')
        
    Returns:
        Translated text or None if translation fails
    """
    try:
        import openai
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""Translate the following medical discharge summary from English to {target_language}. 
        Maintain medical accuracy and use patient-friendly language. Keep the same format and structure:

        {text}"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a medical translator specializing in discharge instructions. Translate accurately while using patient-friendly language."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.1
        )
        
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content.strip()
        
        return None
        
    except Exception as e:
        logger.error(f"OpenAI translation error: {e}")
        return None


def format_email_content(
    instructions: List[Dict], 
    patient_name: Optional[str] = None,
    session_id: Optional[str] = None,
    patient_language: Optional[str] = None,
    healthcare_provider_name: Optional[str] = None
) -> tuple[str, str]:
    """
    Format instruction summary as personalized email content
    
    Args:
        instructions: List of instruction dictionaries with 'text' field
        patient_name: Patient's name to include in summary
        session_id: Session ID for tracking
        patient_language: Patient's preferred language for the summary
        healthcare_provider_name: Name of the healthcare provider
        
    Returns:
        Tuple of (subject_line, email_body)
    """
    
    # Get current date components
    now = datetime.now()
    month = now.strftime("%B")  # Full month name (January, February, etc.)
    day = now.strftime("%d").lstrip('0')  # Day without leading zero
    
    provider_name = healthcare_provider_name or "your doctor"
    patient_display_name = patient_name or "Patient"
    
    # Determine if translation is needed
    needs_translation = patient_language and patient_language.lower() != 'english'
    
    # Create subject line
    subject_line = f"Maya from {provider_name}'s Office | Your Discharge Summary from {month} {day}"
    
    # Create email body
    if not instructions or len(instructions) == 0:
        email_body = f"""Hi {patient_display_name},

Great to meet you earlier today. As promised, here's your discharge summary from your conversation with {provider_name}'s office.

No specific discharge instructions were captured during this session.

If you have any questions, don't hesitate to call or text me anytime. I'm here 24/7 to make your recovery process as smooth as possible!

Best,
Maya"""
    else:
        # Build instruction list
        instruction_lines = []
        for idx, instruction in enumerate(instructions, 1):
            if isinstance(instruction, dict):
                text = instruction.get("text", "").strip()
            else:
                text = str(instruction).strip()
                
            if text:
                instruction_lines.append(f"    {idx}. {text}")
        
        instructions_text = "\n".join(instruction_lines)
        
        email_body = f"""Hi {patient_display_name},

Great to meet you earlier today. As promised, here's your discharge summary from your conversation with {provider_name}'s office.

{instructions_text}

If you have any questions, don't hesitate to call or text me anytime. I'm here 24/7 to make your recovery process as smooth as possible!

Best,
Maya"""
    
    # Translate if needed
    if needs_translation:
        try:
            # Translate subject line
            translated_subject = _translate_text_with_openai(subject_line, patient_language)
            if translated_subject:
                subject_line = translated_subject
            
            # Translate email body
            translated_body = _translate_text_with_openai(email_body, patient_language)
            if translated_body:
                email_body = translated_body
                
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            # Continue with English version if translation fails
    
    return subject_line, email_body


def send_instruction_summary_email(
    instructions: List[Dict],
    patient_name: Optional[str] = None,
    session_id: Optional[str] = None,
    gmail_username: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    recipient_email: Optional[str] = None,
    patient_language: Optional[str] = None,
    healthcare_provider_name: Optional[str] = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587
) -> tuple[bool, str]:
    """
    Send instruction summary via Gmail SMTP as personalized email
    
    Args:
        instructions: List of instruction dictionaries
        patient_name: Patient's name
        session_id: Session ID for tracking
        gmail_username: Gmail account username
        gmail_app_password: Gmail app password (not regular password)
        recipient_email: Email address to send summary to
        patient_language: Patient's preferred language for the summary
        healthcare_provider_name: Name of the healthcare provider
        smtp_server: SMTP server (default: smtp.gmail.com)
        smtp_port: SMTP port (default: 587)
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    
    # Validate required parameters
    if not gmail_username or not gmail_app_password or not recipient_email:
        error_msg = "Missing required email configuration (username, app_password, or recipient)"
        logger.error(f"[EMAIL] {error_msg}")
        return False, error_msg
    
    try:
        # Format the email content
        subject_line, email_body = format_email_content(
            instructions, 
            patient_name, 
            session_id, 
            patient_language, 
            healthcare_provider_name
        )
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject_line
        msg['From'] = gmail_username
        msg['To'] = recipient_email
        
        # Create plain text version
        text_part = MIMEText(email_body, 'plain')
        msg.attach(text_part)
        
        # Create HTML version with proper formatting
        html_body = email_body.replace('\n', '<br>')
        html_part = MIMEText(f"<div style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.5;'>{html_body}</div>", 'html')
        msg.attach(html_part)
        
        # Connect to Gmail SMTP server
        logger.debug(f"[EMAIL] Connecting to {smtp_server}:{smtp_port}")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable TLS encryption
        
        # Authenticate with app password
        server.login(gmail_username, gmail_app_password)
        
        # Send the email
        text = msg.as_string()
        server.sendmail(gmail_username, recipient_email, text)
        server.quit()
        
        success_msg = f"Email sent successfully to {recipient_email}"
        logger.info(f"[EMAIL] Session: {session_id} | {success_msg}")
        return True, success_msg
        
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Gmail authentication failed - check app password: {str(e)}"
        logger.error(f"[EMAIL] Session: {session_id} | {error_msg}")
        return False, error_msg
        
    except smtplib.SMTPException as e:
        error_msg = f"SMTP error occurred: {str(e)}"
        logger.error(f"[EMAIL] Session: {session_id} | {error_msg}")
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Unexpected error sending email: {str(e)}"
        logger.error(f"[EMAIL] Session: {session_id} | {error_msg}")
        return False, error_msg


def test_email_configuration(
    gmail_username: str,
    gmail_app_password: str,
    recipient_email: str,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587
) -> tuple[bool, str]:
    """
    Test email configuration by sending a test message
    
    Args:
        gmail_username: Gmail account username
        gmail_app_password: Gmail app password
        recipient_email: Email address to send test to
        smtp_server: SMTP server
        smtp_port: SMTP port
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    
    test_instructions = [
        {"text": "Take Advil for the next three days."},
        {"text": "Call us if you see any swelling."},
        {"text": "Do not shower for the first twenty-four hours after surgery."}
    ]
    
    return send_instruction_summary_email(
        instructions=test_instructions,
        patient_name="Test Patient",
        session_id="test-session",
        gmail_username=gmail_username,
        gmail_app_password=gmail_app_password,
        recipient_email=recipient_email,
        patient_language="English",
        healthcare_provider_name="Dr. Test",
        smtp_server=smtp_server,
        smtp_port=smtp_port
    )