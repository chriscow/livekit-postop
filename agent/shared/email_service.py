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


def format_summary_for_sms(
    instructions: List[Dict], 
    patient_name: Optional[str] = None,
    session_id: Optional[str] = None,
    patient_language: Optional[str] = None
) -> str:
    """
    Format instruction summary for SMS-style delivery (concise, clear format)
    
    Args:
        instructions: List of instruction dictionaries with 'text' field
        patient_name: Patient's name to include in summary
        session_id: Session ID for tracking
        patient_language: Patient's preferred language for the summary
        
    Returns:
        SMS-formatted string suitable for text messaging
    """
    
    # Header with patient name and timestamp
    timestamp = datetime.now().strftime("%m/%d %I:%M%p")
    
    # Determine if translation is needed
    needs_translation = patient_language and patient_language.lower() != 'english'
    
    # Create base content in English first
    if needs_translation:
        header = f"Discharge Summary - {patient_name or 'Patient'} ({timestamp})"
        no_instructions_msg = "No discharge instructions were captured during this session."
        footer_msg = "Questions? Call your healthcare provider."
    else:
        header = f"Discharge Summary - {patient_name or 'Patient'} ({timestamp})"
        no_instructions_msg = "No discharge instructions were captured during this session."  
        footer_msg = "Questions? Call your healthcare provider."
    
    # Handle no instructions case
    if not instructions or len(instructions) == 0:
        base_message = f"{header}\n\n{no_instructions_msg}"
        
        if needs_translation:
            try:
                translated_message = _translate_text_with_openai(base_message, patient_language)
                return translated_message if translated_message else base_message
            except Exception as e:
                logger.error(f"Translation failed: {e}")
                return base_message
        return base_message
    
    # Build concise instruction list
    formatted_lines = [header, ""]
    
    for idx, instruction in enumerate(instructions, 1):
        if isinstance(instruction, dict):
            text = instruction.get("text", "").strip()
        else:
            text = str(instruction).strip()
            
        if text:
            # Keep instructions concise for SMS - truncate if too long
            if len(text) > 120:
                text = text[:117] + "..."
            formatted_lines.append(f"{idx}. {text}")
    
    # Add footer
    formatted_lines.append("")
    formatted_lines.append(footer_msg)
    
    # Join with newlines and ensure total length is reasonable for SMS gateways
    full_message = "\n".join(formatted_lines)
    
    # Translate if needed
    if needs_translation:
        try:
            translated_message = _translate_text_with_openai(full_message, patient_language)
            full_message = translated_message if translated_message else full_message
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            # Continue with English version if translation fails
    
    # Log message length for monitoring
    logger.debug(f"SMS-formatted summary length: {len(full_message)} characters")
    
    return full_message


def send_instruction_summary_email(
    instructions: List[Dict],
    patient_name: Optional[str] = None,
    session_id: Optional[str] = None,
    gmail_username: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    recipient_email: Optional[str] = None,
    patient_language: Optional[str] = None,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587
) -> tuple[bool, str]:
    """
    Send instruction summary via Gmail SMTP as SMS-formatted email
    
    Args:
        instructions: List of instruction dictionaries
        patient_name: Patient's name
        session_id: Session ID for tracking
        gmail_username: Gmail account username
        gmail_app_password: Gmail app password (not regular password)
        recipient_email: Email address to send summary to
        patient_language: Patient's preferred language for the summary
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
        # Format the summary for SMS
        sms_content = format_summary_for_sms(instructions, patient_name, session_id, patient_language)
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Discharge Summary - {patient_name or 'Patient'}"
        msg['From'] = gmail_username
        msg['To'] = recipient_email
        
        # Create plain text version (primary for SMS gateways)
        text_part = MIMEText(sms_content, 'plain')
        msg.attach(text_part)
        
        # Create simple HTML version as fallback
        html_content = sms_content.replace('\n', '<br>')
        html_part = MIMEText(f"<pre>{html_content}</pre>", 'html')
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
        {"text": "Test instruction 1 - Take medication as prescribed"},
        {"text": "Test instruction 2 - Follow up with doctor in 1 week"}
    ]
    
    return send_instruction_summary_email(
        instructions=test_instructions,
        patient_name="Test Patient",
        session_id="test-session",
        gmail_username=gmail_username,
        gmail_app_password=gmail_app_password,
        recipient_email=recipient_email,
        patient_language="English",
        smtp_server=smtp_server,
        smtp_port=smtp_port
    )