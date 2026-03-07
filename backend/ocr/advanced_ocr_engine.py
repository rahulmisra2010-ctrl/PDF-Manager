import fitz  # PyMuPDF
import pytesseract  # Tesseract
from easyocr import Reader  # EasyOCR

class AdvancedOCREngine:
    def __init__(self):
        self.tesseract_path = '/usr/bin/tesseract'  # Path to Tesseract executable
        self.easyocr_reader = Reader(lang_list=['en'])  # Initialize EasyOCR reader

    def perform_ocr(self, image_path):
        # Attempt OCR using EasyOCR
        try:
            result = self.easyocr_reader.readtext(image_path)
            return self.format_result(result)
        except Exception as e:
            print(f"EasyOCR failed: {e}")  # Log the error

        # Fallback to Tesseract
        try:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
            result = pytesseract.image_to_string(image_path)
            return result
        except Exception as e:
            print(f"Tesseract failed: {e}")  # Log the error

        # Fallback to PyMuPDF for image processing if required
        try:
            doc = fitz.open(image_path)
            # Convert the pages to images or perform any required processing
            return self.process_with_pymupdf(doc)
        except Exception as e:
            print(f"PyMuPDF failed: {e}")  # Log the error

    def format_result(self, result):
        formatted_text = "".join([res[1] for res in result])  # Join the recognized text
        return formatted_text

    def process_with_pymupdf(self, doc):
        # Custom logic for processing with PyMuPDF
        text = ""
        for page in doc:
            text += page.get_text()  # Extract text from each page
        return text

# Example usage:
# ocr_engine = AdvancedOCREngine()
# text = ocr_engine.perform_ocr('path_to_your_image_file.jpg')
# print(text)

