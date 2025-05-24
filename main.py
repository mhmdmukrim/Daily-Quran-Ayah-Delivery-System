import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from googletrans import Translator
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import os

# Configuration
EMAIL = "mukrimmhmd@gmail.com"
PASSWORD = "iguk mpfl rjot boxw"
TO_EMAILS = ["mukrimmhmd@gmail.com"]

STATE_FILE = "quran_reading_state.json"
VERSE_CHUNK = 20
PDF_FILE = "daily_ayahs.pdf"

# Arablish Mapping
def transliterate_arabic(text):
    mapping = {
        'ا':'a', 'ب':'b', 'ت':'t', 'ث':'th', 'ج':'j', 'ح':'h', 'خ':'kh',
        'د':'d', 'ذ':'dh', 'ر':'r', 'ز':'z', 'س':'s', 'ش':'sh', 'ص':'s',
        'ض':'d', 'ط':'t', 'ظ':'z', 'ع':'a', 'غ':'gh', 'ف':'f', 'ق':'q',
        'ك':'k', 'ل':'l', 'م':'m', 'ن':'n', 'ه':'h', 'و':'w', 'ي':'y',
        'ء':'', 'ى':'a', 'ة':'h', 'ﻻ':'la', 'ً':'an', 'ٌ':'un', 'ٍ':'in',
        'َ':'a', 'ُ':'u', 'ِ':'i', 'ّ':'', 'ْ':''
    }
    return ''.join(mapping.get(char, char) for char in text)

# Fetch ayahs
def get_ayahs_from_surah(surah_number, start_ayah, count):
    url_en = f"https://api.alquran.cloud/v1/surah/{surah_number}/en.asad"
    url_ar = f"https://api.alquran.cloud/v1/surah/{surah_number}/ar.alafasy"

    try:
        data_en = requests.get(url_en).json()
        data_ar = requests.get(url_ar).json()

        if data_en["status"] != "OK" or data_ar["status"] != "OK":
            return None, 0

        ayahs_en = data_en["data"]["ayahs"]
        ayahs_ar = data_ar["data"]["ayahs"]
        total_ayahs = len(ayahs_ar)

        selected_en = ayahs_en[start_ayah - 1 : start_ayah - 1 + count]
        selected_ar = ayahs_ar[start_ayah - 1 : start_ayah - 1 + count]

        result = []
        for ar, en in zip(selected_ar, selected_en):
            result.append({
                "arabic": ar["text"],
                "translation": en["text"],
                "numberInSurah": ar["numberInSurah"],
                "surahName": data_en["data"]["englishName"],
                "surahNumber": surah_number
            })

        return result, total_ayahs
    except Exception as e:
        print(f"Error fetching ayahs: {e}")
        return None, 0

# State management
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"surah": 1, "ayah": 1}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# Translate
def translate_to_sinhala(text, translator):
    try:
        translated = translator.translate(text, dest='si').text
        # Clean up any problematic characters for PDF rendering
        return translated.encode('utf-8', errors='ignore').decode('utf-8')
    except Exception as e:
        print(f"Translation error: {e}")
        return "Sinhala translation unavailable."

# PDF generation
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        # Only add Arabic font if the file exists
        if os.path.exists("Amiri-Regular.ttf"):
            try:
                self.add_font("Amiri", "", "Amiri-Regular.ttf")
            except Exception as e:
                print(f"Could not load Arabic font: {e}")
        
        # Only add Sinhala font if the file exists
        if os.path.exists("NotoSansSinhala-Regular.ttf"):
            try:
                self.add_font("Sinhala", "", "NotoSansSinhala-Regular.ttf")
            except Exception as e:
                print(f"Could not load Sinhala font: {e}")

    def safe_cell(self, w, h, txt, new_x=XPos.RIGHT, new_y=YPos.TOP, font_name="Arial", font_size=12):
        """Safely add text with fallback font handling"""
        try:
            self.set_font(font_name, size=font_size)
            self.cell(w, h, txt, new_x=new_x, new_y=new_y)
        except Exception:
            # Fallback to Arial/Helvetica
            self.set_font("Arial", size=font_size)
            # Remove problematic characters
            safe_txt = txt.encode('ascii', errors='ignore').decode('ascii')
            self.cell(w, h, safe_txt, new_x=new_x, new_y=new_y)

    def safe_multi_cell(self, w, h, txt, font_name="Arial", font_size=12):
        """Safely add multiline text with fallback font handling"""
        try:
            self.set_font(font_name, size=font_size)
            self.multi_cell(w, h, txt)
        except Exception as e:
            print(f"Multi-cell error with {font_name}: {e}")
            try:
                # Fallback to Helvetica
                self.set_font("Helvetica", size=font_size)
                # Remove problematic characters and limit text length
                safe_txt = txt.encode('ascii', errors='ignore').decode('ascii')
                if not safe_txt.strip():
                    safe_txt = "[Text rendering not supported]"
                # Limit line length to prevent horizontal space issues
                if len(safe_txt) > 80:
                    safe_txt = safe_txt[:77] + "..."
                self.multi_cell(w, h, safe_txt)
            except Exception as e2:
                print(f"Even Helvetica failed: {e2}")
                # Final fallback - use simple cell instead of multi_cell
                try:
                    self.set_font("Helvetica", size=font_size)
                    self.cell(0, h, "[Text rendering failed]", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                except Exception:
                    # Just skip this text entirely
                    self.ln(h)

def generate_pdf(verses, filepath):
    try:
        pdf = PDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        for v in verses:
            # Title
            pdf.safe_cell(0, 10, f"Surah {v['surahName']} - Ayah {v['numberInSurah']}", 
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT, font_name="Helvetica", font_size=12)
            
            # Arabic text
            if os.path.exists("Amiri-Regular.ttf"):
                pdf.safe_cell(0, 12, v["arabic"], new_x=XPos.LMARGIN, new_y=YPos.NEXT, 
                             font_name="Amiri", font_size=16)
            else:
                pdf.safe_cell(0, 12, f"Arabic: {v['arabic']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, 
                             font_name="Helvetica", font_size=12)

            # Arablish
            pdf.safe_cell(0, 10, f"Arablish: {transliterate_arabic(v['arabic'])}", 
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT, font_name="Helvetica", font_size=10)

            # English translation
            pdf.safe_multi_cell(0, 10, f"English: {v['translation']}", font_name="Helvetica", font_size=10)

            # Sinhala translation - Skip this entirely to avoid errors
            try:
                translator = Translator()
                sinhala_text = translate_to_sinhala(v["translation"], translator)
                
                # Try to add Sinhala text, but with more safety
                if len(sinhala_text) < 100 and sinhala_text != "Sinhala translation unavailable.":
                    if os.path.exists("NotoSansSinhala-Regular.ttf"):
                        pdf.safe_multi_cell(0, 10, f"Sinhala: {sinhala_text}", font_name="Sinhala", font_size=10)
                    else:
                        # Skip Sinhala if no font
                        pdf.safe_cell(0, 10, "Sinhala: [Font not available]", 
                                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, font_name="Helvetica", font_size=10)
                else:
                    pdf.safe_cell(0, 10, "Sinhala: [Translation too long or unavailable]", 
                                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, font_name="Helvetica", font_size=10)
            except Exception as e:
                print(f"Skipping Sinhala translation due to error: {e}")
                pdf.safe_cell(0, 10, "Sinhala: [Translation skipped]", 
                             new_x=XPos.LMARGIN, new_y=YPos.NEXT, font_name="Helvetica", font_size=10)

            # Add separator line
            try:
                pdf.set_draw_color(0, 0, 0)
                pdf.set_line_width(0.3)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(5)
            except Exception:
                pdf.ln(10)  # Just add space if line drawing fails

        pdf.output(filepath)
        print(f"PDF generated successfully: {filepath}")
        return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        # Create a simple fallback PDF
        return create_simple_pdf(verses, filepath)

def create_simple_pdf(verses, filepath):
    """Create a simple PDF with basic formatting as fallback"""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        pdf.set_font("Helvetica", size=16)
        pdf.cell(0, 10, "Daily Quran Verses", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(10)
        
        for i, v in enumerate(verses):
            pdf.set_font("Helvetica", size=12)
            pdf.cell(0, 8, f"Ayah {v['numberInSurah']} - Surah {v['surahName']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Only include English translation to avoid character issues
            english_text = v['translation']
            # Break long text into chunks
            max_chars = 80
            while len(english_text) > max_chars:
                break_point = english_text.rfind(' ', 0, max_chars)
                if break_point == -1:
                    break_point = max_chars
                pdf.cell(0, 6, english_text[:break_point], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                english_text = english_text[break_point:].lstrip()
            
            if english_text:
                pdf.cell(0, 6, english_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            pdf.ln(5)
        
        pdf.output(filepath)
        print(f"Simple PDF generated successfully: {filepath}")
        return True
    except Exception as e:
        print(f"Failed to create even simple PDF: {e}")
        # Create a minimal text file as last resort
        try:
            with open(filepath.replace('.pdf', '.txt'), 'w', encoding='utf-8') as f:
                f.write("Daily Quran Verses\n\n")
                for v in verses:
                    f.write(f"Ayah {v['numberInSurah']} - Surah {v['surahName']}\n")
                    f.write(f"English: {v['translation']}\n\n")
            print(f"Created text file instead: {filepath.replace('.pdf', '.txt')}")
            return False
        except Exception as e2:
            print(f"Even text file creation failed: {e2}")
            return False
# Send email
def send_email(body, attachments=[]):
    msg = MIMEMultipart()
    msg['From'] = EMAIL
    msg['To'] = ", ".join(TO_EMAILS)
    msg['Subject'] = "Your Daily Quran Ayahs 🌙"

    msg.attach(MIMEText(body, 'plain'))

    for filepath in attachments:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(filepath))
                    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filepath)}"'
                    msg.attach(part)
                print(f"Attached: {filepath}")
            except Exception as e:
                print(f"Failed to attach {filepath}: {e}")

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, TO_EMAILS, msg.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

if __name__ == "__main__":
    print("Starting Daily Quran Reader...")

    state = load_state()
    surah = state["surah"]
    ayah = state["ayah"]

    print(f"Current position: Surah {surah}, Ayah {ayah}")

    translator = Translator()
    verses, total_ayahs = get_ayahs_from_surah(surah, ayah, VERSE_CHUNK)

    if not verses:
        print("❌ Failed to fetch verses.")
        exit(1)

    print(f"✅ Fetched {len(verses)} verses from Surah {verses[0]['surahName']}")

    body = f"📖 Daily Quran Verses from Surah {verses[0]['surahName']} (Surah {verses[0]['surahNumber']})\n\n"
    for v in verses:
        translit = transliterate_arabic(v["arabic"])
        sinhala = translate_to_sinhala(v["translation"], translator)
        body += (
            f"🌟 Ayah {v['numberInSurah']}\n"
            f"Arabic: {v['arabic']}\n"
            f"Arablish: {translit}\n"
            f"English: {v['translation']}\n"
            f"Sinhala: {sinhala}\n\n"
        )

    # Generate PDF
    print("Generating PDF...")
    pdf_success = generate_pdf(verses, PDF_FILE)

    # Prepare attachments
    attachments = []
    if pdf_success and os.path.exists(PDF_FILE):
        attachments.append(PDF_FILE)
    else:
        # Try fallback text file
        txt_file = PDF_FILE.replace('.pdf', '.txt')
        if os.path.exists(txt_file):
            attachments.append(txt_file)

    # Send Email
    print("Sending email...")
    send_email(body, attachments=attachments)

    # Update reading state
    last_ayah = verses[-1]["numberInSurah"]
    if last_ayah >= total_ayahs:
        new_state = {"surah": surah + 1, "ayah": 1}
        print(f"Completed Surah {surah}. Moving to Surah {surah + 1}")
    else:
        new_state = {"surah": surah, "ayah": last_ayah + 1}
        print(f"Next reading: Surah {surah}, Ayah {last_ayah + 1}")

    save_state(new_state)
    print("✅ Daily Quran reading completed successfully!")
