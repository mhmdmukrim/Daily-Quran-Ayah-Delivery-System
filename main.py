import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
try:
    from googletrans import Translator
    TRANSLATOR_TYPE = "googletrans"
except ImportError:
    try:
        from translate import Translator as TranslateTranslator
        TRANSLATOR_TYPE = "translate"
    except ImportError:
        print("Neither googletrans nor translate library found. Please install one of them:")
        print("pip install googletrans==4.0.0-rc1")
        print("or")
        print("pip install translate")
        sys.exit(1)
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import os
import logging
import time
from datetime import datetime
import sys

# Enhanced Configuration
class Config:
    EMAIL = "mukrimmhmd@gmail.com"
    PASSWORD = "iguk mpfl rjot boxw"  # Consider using environment variables
    TO_EMAILS = ["mukrimmhmd@gmail.com","shafeekafathima1@gmail.com","mhmdmukarram200@gmail.com"]
    
    STATE_FILE = "quran_reading_state.json"
    VERSE_CHUNK = 10
    PDF_FILE = "daily_ayahs.pdf"
    LOG_FILE = "quran_reader.log"
    
    # API endpoints
    API_BASE = "https://api.alquran.cloud/v1"
    BACKUP_API = "https://api.quran.com/api/v4"  # Backup option
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

# Setup logging
def setup_logging():
    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # File handler (supports UTF-8)
    file_handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    
    # Console handler with UTF-8 support
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    
    # Try to set UTF-8 encoding for Windows console
    try:
        import codecs
        if sys.platform.startswith('win'):
            # Try to set console to UTF-8 mode
            import os
            os.system('chcp 65001 >nul 2>&1')
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass
    
    # Setup root logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# Enhanced Arablish Mapping with better diacritics handling
def transliterate_arabic(text):
    mapping = {
        # Basic letters
        'ا':'a', 'ب':'b', 'ت':'t', 'ث':'th', 'ج':'j', 'ح':'h', 'خ':'kh',
        'د':'d', 'ذ':'dh', 'ر':'r', 'ز':'z', 'س':'s', 'ش':'sh', 'ص':'s',
        'ض':'d', 'ط':'t', 'ظ':'z', 'ع':'a', 'غ':'gh', 'ف':'f', 'ق':'q',
        'ك':'k', 'ل':'l', 'م':'m', 'ن':'n', 'ه':'h', 'و':'w', 'ي':'y',
        
        # Special characters
        'ء':'', 'ى':'a', 'ة':'h', 'ﻻ':'la',
        
        # Diacritics
        'ً':'an', 'ٌ':'un', 'ٍ':'in', 'َ':'a', 'ُ':'u', 'ِ':'i', 
        'ّ':'', 'ْ':'', 'ٰ':'a', 'ٓ':'',
        
        # Additional characters
        'آ': 'aa', 'إ': 'i', 'أ': 'a', 'ؤ': 'u', 'ئ': 'i'
    }
    
    result = ''
    for char in text:
        if char in mapping:
            result += mapping[char]
        elif char.isspace() or char in '.,;:!?()[]{}':
            result += char
        else:
            result += char
    
    # Clean up multiple consecutive vowels
    import re
    result = re.sub(r'([aui])\1+', r'\1', result)
    return result.strip()

# Enhanced API fetching with retry logic and error handling
def get_ayahs_from_surah(surah_number, start_ayah, count, max_retries=Config.MAX_RETRIES):
    """Fetch ayahs with retry logic and better error handling"""
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Fetching Surah {surah_number}, Ayahs {start_ayah}-{start_ayah+count-1} (Attempt {attempt+1})")
            
            # Primary API calls
            url_en = f"{Config.API_BASE}/surah/{surah_number}/en.asad"
            url_ar = f"{Config.API_BASE}/surah/{surah_number}/ar.alafasy"
            
            # Add timeout and better error handling
            response_en = requests.get(url_en, timeout=10)
            response_ar = requests.get(url_ar, timeout=10)
            
            response_en.raise_for_status()
            response_ar.raise_for_status()
            
            data_en = response_en.json()
            data_ar = response_ar.json()

            if data_en["status"] != "OK" or data_ar["status"] != "OK":
                raise Exception(f"API returned error status: EN={data_en.get('status')}, AR={data_ar.get('status')}")

            ayahs_en = data_en["data"]["ayahs"]
            ayahs_ar = data_ar["data"]["ayahs"]
            total_ayahs = len(ayahs_ar)
            
            # Validate ayah range
            if start_ayah > total_ayahs:
                logger.warning(f"Start ayah {start_ayah} exceeds total ayahs {total_ayahs} in surah {surah_number}")
                return None, total_ayahs
            
            # Adjust count if it exceeds available ayahs
            actual_count = min(count, total_ayahs - start_ayah + 1)
            
            selected_en = ayahs_en[start_ayah - 1 : start_ayah - 1 + actual_count]
            selected_ar = ayahs_ar[start_ayah - 1 : start_ayah - 1 + actual_count]

            result = []
            for ar, en in zip(selected_ar, selected_en):
                result.append({
                    "arabic": ar["text"],
                    "translation": en["text"],
                    "numberInSurah": ar["numberInSurah"],
                    "surahName": data_en["data"]["englishName"],
                    "surahArabicName": data_ar["data"]["name"],
                    "surahNumber": surah_number,
                    "revelationPlace": data_en["data"]["revelationType"]
                })

            logger.info(f"Successfully fetched {len(result)} ayahs from Surah {data_en['data']['englishName']}")
            return result, total_ayahs
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error on attempt {attempt+1}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error on attempt {attempt+1}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt+1}: {e}")
        
        if attempt < max_retries - 1:
            logger.info(f"Retrying in {Config.RETRY_DELAY} seconds...")
            time.sleep(Config.RETRY_DELAY)
    
    logger.error(f"Failed to fetch ayahs after {max_retries} attempts")
    return None, 0

# Enhanced state management with backup
def load_state():
    """Load state with validation and backup handling"""
    try:
        if os.path.exists(Config.STATE_FILE):
            with open(Config.STATE_FILE, "r") as f:
                state = json.load(f)
            
            # Validate state
            if not isinstance(state, dict) or "surah" not in state or "ayah" not in state:
                raise ValueError("Invalid state format")
            
            # Validate ranges
            if not (1 <= state["surah"] <= 114) or not (state["ayah"] >= 1):
                raise ValueError(f"Invalid state values: surah={state['surah']}, ayah={state['ayah']}")
            
            logger.info(f"Loaded state: Surah {state['surah']}, Ayah {state['ayah']}")
            return state
        else:
            logger.info("No state file found, starting from beginning")
            return {"surah": 1, "ayah": 1}
            
    except Exception as e:
        logger.error(f"Error loading state: {e}")
        logger.info("Using default state")
        return {"surah": 1, "ayah": 1}

def save_state(state):
    """Save state with backup"""
    try:
        # Create backup
        if os.path.exists(Config.STATE_FILE):
            backup_file = Config.STATE_FILE + ".backup"
            os.rename(Config.STATE_FILE, backup_file)
        
        with open(Config.STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"Saved state: Surah {state['surah']}, Ayah {state['ayah']}")
        
    except Exception as e:
        logger.error(f"Error saving state: {e}")
        # Restore backup if available
        backup_file = Config.STATE_FILE + ".backup"
        if os.path.exists(backup_file):
            os.rename(backup_file, Config.STATE_FILE)
            logger.info("Restored state from backup")

# Enhanced translation with caching and error handling
def translate_text(text, dest_lang, translator, max_retries=2):
    """Enhanced translation with retry logic"""
    for attempt in range(max_retries):
        try:
            if TRANSLATOR_TYPE == "googletrans":
                # For googletrans library
                translated = translator.translate(text, dest=dest_lang)
                if translated and hasattr(translated, 'text'):
                    result = translated.text.encode('utf-8', errors='ignore').decode('utf-8')
                    if result.strip():
                        return result
            else:
                # For translate library
                result = translator.translate(text, dest_lang)
                if result and result.strip():
                    return result.encode('utf-8', errors='ignore').decode('utf-8')
            
        except Exception as e:
            logger.warning(f"Translation error for {dest_lang} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)  # Brief delay before retry
    
    logger.error(f"Failed to translate to {dest_lang} after {max_retries} attempts")
    return f"{dest_lang.capitalize()} translation unavailable."

# Enhanced PDF generation with better error handling
class EnhancedQuranPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.fonts_loaded = {}
        self._add_fonts()
        
    def _add_fonts(self):
        """Add fonts with comprehensive error handling"""
        fonts = [
            ("Amiri", "Amiri-Regular.ttf", ""),
            ("NotoSansSinhala", "NotoSansSinhala-Regular.ttf", ""),
            ("NotoSansTamil", "NotoSansTamil-Regular.ttf", "")
        ]
        
        for font_name, font_file, font_style in fonts:
            try:
                if os.path.exists(font_file):
                    self.add_font(font_name, font_style, font_file)
                    self.fonts_loaded[font_name] = True
                    logger.info(f"Loaded font: {font_name}")
                else:
                    logger.warning(f"Font file not found: {font_file}")
                    self.fonts_loaded[font_name] = False
            except Exception as e:
                logger.error(f"Failed to load font {font_name}: {e}")
                self.fonts_loaded[font_name] = False
    
    def header(self):
        self.set_font("Helvetica", "B", 16)
        date_str = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 10, f"Daily Quran Verses - {date_str}", 0, 1, "C")
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()} | Generated by Daily Quran Reader", 0, 0, "C")
    
    def safe_set_font(self, font_name, style="", size=12):
        """Safely set font with fallback"""
        try:
            if font_name in self.fonts_loaded and self.fonts_loaded[font_name]:
                self.set_font(font_name, style, size)
                return True
            else:
                self.set_font("Helvetica", style, size)
                return False
        except Exception as e:
            logger.warning(f"Font setting error: {e}")
            self.set_font("Helvetica", style, size)
            return False
    
    def add_verse(self, verse, translator):
        """Enhanced verse addition with better formatting"""
        # Check if we need a new page
        if self.get_y() > 250:  # Near bottom of page
            self.add_page()
        
        # Surah and Ayah header
        self.safe_set_font("Helvetica", "B", 12)
        header_text = f"Surah {verse['surahName']} ({verse.get('surahArabicName', '')}) - Chapter {verse['surahNumber']}, Verse {verse['numberInSurah']}"
        if verse.get('revelationPlace'):
            header_text += f" [{verse['revelationPlace']}]"
        
        self.cell(0, 8, header_text, ln=1)
        self.ln(2)
        
        # Arabic text with better handling
        arabic_success = self.safe_set_font("Amiri", size=16)
        if not arabic_success:
            logger.warning("Arabic font not available, using default")
        
        self.multi_cell(0, 8, verse["arabic"], align="R")
        self.ln(3)
        
        # Transliteration
        self.safe_set_font("Helvetica", "I", 10)
        self.cell(0, 6, "Transliteration:", ln=1)
        self.safe_set_font("Helvetica", size=9)
        translit = transliterate_arabic(verse["arabic"])
        self.multi_cell(0, 5, translit)
        self.ln(3)
        
        # English translation
        self.safe_set_font("Helvetica", "B", 10)
        self.cell(0, 6, "English Translation:", ln=1)
        self.safe_set_font("Helvetica", size=10)
        self.multi_cell(0, 6, verse["translation"])
        self.ln(3)
        
        # Additional translations
        translations = [
            ("Sinhala", "si", "NotoSansSinhala"),
            ("Tamil", "ta", "NotoSansTamil")
        ]
        
        for lang_name, lang_code, font_name in translations:
            try:
                translated_text = translate_text(verse["translation"], lang_code, translator)
                
                self.safe_set_font("Helvetica", "B", 10)
                self.cell(0, 6, f"{lang_name} Translation:", ln=1)
                
                font_success = self.safe_set_font(font_name, size=10)
                if not font_success:
                    logger.warning(f"{lang_name} font not available, using default")
                
                self.multi_cell(0, 6, translated_text)
                self.ln(3)
                
            except Exception as e:
                logger.error(f"Error adding {lang_name} translation: {e}")
        
        # Separator line
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(8)

def generate_pdf(verses, filepath, translator):
    """Generate PDF with comprehensive error handling"""
    try:
        logger.info(f"Generating PDF with {len(verses)} verses")
        pdf = EnhancedQuranPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        for i, verse in enumerate(verses):
            logger.debug(f"Adding verse {i+1}/{len(verses)} to PDF")
            pdf.add_verse(verse, translator)
        
        pdf.output(filepath)
        
        # Verify PDF was created and has content
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:  # At least 1KB
            logger.info(f"PDF generated successfully: {filepath} ({os.path.getsize(filepath)} bytes)")
            return True
        else:
            logger.error("PDF file is missing or too small")
            return False
            
    except Exception as e:
        logger.error(f"Error generating enhanced PDF: {e}")
        return create_simple_pdf(verses, filepath)

def create_simple_pdf(verses, filepath):
    """Fallback simple PDF creation"""
    try:
        logger.info("Creating simple fallback PDF")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, f"Daily Quran Verses - {datetime.now().strftime('%B %d, %Y')}", 0, 1, "C")
        pdf.ln(10)
        
        for verse in verses:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, f"Surah {verse['surahName']} - Verse {verse['numberInSurah']}", 0, 1)
            pdf.ln(2)
            
            pdf.set_font("Helvetica", size=10)
            # Use simpler text handling for Arabic
            try:
                pdf.multi_cell(0, 6, f"Arabic: {verse['arabic']}")
            except:
                pdf.multi_cell(0, 6, "Arabic: [Text encoding issue]")
            pdf.ln(2)
            
            pdf.multi_cell(0, 6, f"Transliteration: {transliterate_arabic(verse['arabic'])}")
            pdf.ln(2)
            
            pdf.multi_cell(0, 6, f"Translation: {verse['translation']}")
            pdf.ln(5)
            
            # Simple separator
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(8)
        
        pdf.output(filepath)
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 500:
            logger.info(f"Simple PDF created successfully: {filepath}")
            return True
        else:
            logger.error("Simple PDF creation failed")
            return create_text_fallback(verses, filepath)
            
    except Exception as e:
        logger.error(f"Simple PDF creation failed: {e}")
        return create_text_fallback(verses, filepath)

def create_text_fallback(verses, filepath):
    """Create text file as last resort"""
    try:
        txt_filepath = filepath.replace('.pdf', '.txt')
        logger.info(f"Creating text fallback: {txt_filepath}")
        
        with open(txt_filepath, 'w', encoding='utf-8') as f:
            f.write(f"Daily Quran Verses - {datetime.now().strftime('%B %d, %Y')}\n")
            f.write("=" * 50 + "\n\n")
            
            for verse in verses:
                f.write(f"Surah {verse['surahName']} - Verse {verse['numberInSurah']}\n")
                f.write("-" * 40 + "\n")
                f.write(f"Arabic: {verse['arabic']}\n")
                f.write(f"Transliteration: {transliterate_arabic(verse['arabic'])}\n")
                f.write(f"English: {verse['translation']}\n\n")
        
        logger.info(f"Text file created: {txt_filepath}")
        return False  # Return False since we wanted PDF but created txt
        
    except Exception as e:
        logger.error(f"Text fallback creation failed: {e}")
        return False

# Enhanced email sending
def send_email(body, attachments=[]):
    """Send email with better error handling and validation"""
    try:
        logger.info("Preparing email...")
        
        msg = MIMEMultipart()
        msg['From'] = Config.EMAIL
        msg['To'] = ", ".join(Config.TO_EMAILS)
        msg['Subject'] = f"Your Daily Quran Verses 🌙 - {datetime.now().strftime('%B %d, %Y')}"

        # Add body
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Add attachments with validation
        attached_files = []
        for filepath in attachments:
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                        if len(content) > 25 * 1024 * 1024:  # 25MB limit
                            logger.warning(f"Attachment {filepath} too large ({len(content)} bytes), skipping")
                            continue
                        
                        part = MIMEApplication(content, Name=os.path.basename(filepath))
                        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filepath)}"'
                        msg.attach(part)
                        attached_files.append(filepath)
                        logger.info(f"Attached: {filepath} ({len(content)} bytes)")
                        
                except Exception as e:
                    logger.error(f"Failed to attach {filepath}: {e}")
            else:
                logger.warning(f"Skipping attachment {filepath} (missing or empty)")

        # Send email
        logger.info("Connecting to SMTP server...")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(Config.EMAIL, Config.PASSWORD)
        
        failed_recipients = server.sendmail(Config.EMAIL, Config.TO_EMAILS, msg.as_string())
        server.quit()
        
        if failed_recipients:
            logger.warning(f"Failed to send to some recipients: {failed_recipients}")
        else:
            logger.info("Email sent successfully to all recipients!")
            
        return True
        
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP Authentication failed - check email credentials")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return False

# Enhanced main function
def main():
    """Main execution function with comprehensive error handling"""
    try:
        logger.info("=" * 60)
        logger.info("Starting Daily Quran Reader")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        logger.info("=" * 60)
        
        # Load current state
        state = load_state()
        surah = state["surah"]
        ayah = state["ayah"]
        
        logger.info(f"Current reading position: Surah {surah}, Ayah {ayah}")
        
        # Check if we've completed the Quran
        if surah > 114:
            logger.info("[CELEBRATION] Congratulations! You have completed the entire Quran!")
            logger.info("Restarting from the beginning...")
            state = {"surah": 1, "ayah": 1}
            save_state(state)
            surah, ayah = 1, 1
        
        # Initialize translator
        logger.info("Initializing translator...")
        if TRANSLATOR_TYPE == "googletrans":
            translator = Translator()
        else:
            # For translate library, we'll create a simple wrapper
            class TranslatorWrapper:
                def __init__(self):
                    pass
                
                def translate(self, text, dest_lang):
                    trans = TranslateTranslator(to_lang=dest_lang)
                    return trans.translate(text)
            
            translator = TranslatorWrapper()
        
        # Fetch verses
        verses, total_ayahs = get_ayahs_from_surah(surah, ayah, Config.VERSE_CHUNK)

        if not verses:
            logger.error("[FAILED] Failed to fetch verses after all retries")
            return False
        
        logger.info(f"[SUCCESS] Successfully fetched {len(verses)} verses from Surah {verses[0]['surahName']}")
        
        # Prepare email body
        body = create_email_body(verses, translator)
        
        # Generate PDF
        logger.info("Generating PDF...")
        pdf_success = generate_pdf(verses, Config.PDF_FILE, translator)

        # Prepare attachments
        attachments = []
        if pdf_success and os.path.exists(Config.PDF_FILE):
            attachments.append(Config.PDF_FILE)
        
        # Check for text file fallback
        txt_file = Config.PDF_FILE.replace('.pdf', '.txt')
        if not pdf_success and os.path.exists(txt_file):
            attachments.append(txt_file)

        # Send email
        logger.info("Sending email...")
        email_success = send_email(body, attachments=attachments)
        
        if not email_success:
            logger.error("Failed to send email")
            return False

        # Update reading state
        update_reading_state(verses, surah, total_ayahs)
        
        logger.info("[SUCCESS] Daily Quran reading completed successfully!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error in main execution: {e}")
        return False

def create_email_body(verses, translator):
    """Create enhanced email body"""
    surah_name = verses[0]['surahName']
    surah_number = verses[0]['surahNumber']
    
    body = f"🌙 Assalamu Alaikum! 🌙\n\n"
    body += f"📖 Your Daily Quran Verses from Surah {surah_name} (Chapter {surah_number})\n"
    body += f"📅 {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
    
    if verses[0].get('revelationPlace'):
        body += f"🕌 Revelation: {verses[0]['revelationPlace']}\n\n"
    
    for i, verse in enumerate(verses, 1):
        body += f"🌟 Ayah {verse['numberInSurah']}\n"
        body += f"{'='*40}\n"
        body += f"Arabic: {verse['arabic']}\n\n"
        
        translit = transliterate_arabic(verse["arabic"])
        body += f"Transliteration: {translit}\n\n"
        
        body += f"English Translation: {verse['translation']}\n\n"
        
        # Add translations with error handling
        try:
            sinhala = translate_text(verse["translation"], "si", translator)
            body += f"Sinhala: {sinhala}\n\n"
        except Exception as e:
            logger.warning(f"Sinhala translation failed for verse {i}: {e}")
        
        try:
            tamil = translate_text(verse["translation"], "ta", translator)
            body += f"Tamil: {tamil}\n\n"
        except Exception as e:
            logger.warning(f"Tamil translation failed for verse {i}: {e}")
        
        body += "\n" + "-"*50 + "\n\n"
    
    body += f"🤲 May Allah bless your reading and grant you understanding.\n\n"
    body += f"📊 Progress: Surah {surah_number} of 114\n"
    body += f"Generated by Daily Quran Reader at {datetime.now().strftime('%I:%M %p')}"
    
    return body

def update_reading_state(verses, current_surah, total_ayahs):
    """Update reading state with validation"""
    try:
        last_ayah = verses[-1]["numberInSurah"]
        
        if last_ayah >= total_ayahs:
            # Move to next surah
            new_state = {"surah": current_surah + 1, "ayah": 1}
            logger.info(f"[COMPLETED] Completed Surah {current_surah} ({verses[0]['surahName']})")
            
            if current_surah + 1 <= 114:
                logger.info(f"[NEXT] Moving to Surah {current_surah + 1}")
            else:
                logger.info("[CELEBRATION] Completed the entire Quran! Starting over...")
                
        else:
            # Continue in current surah
            new_state = {"surah": current_surah, "ayah": last_ayah + 1}
            logger.info(f"[PROGRESS] Next reading: Surah {current_surah}, Ayah {last_ayah + 1}")
        
        save_state(new_state)
        
    except Exception as e:
        logger.error(f"Error updating reading state: {e}")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
