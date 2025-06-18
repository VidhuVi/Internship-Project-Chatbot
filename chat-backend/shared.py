import io
import fitz
from docx import Document
from PIL import Image
import pytesseract
import logging
from starlette.concurrency import run_in_threadpool
logging.basicConfig(level=logging.INFO)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
def chunk_text(text: str, chunk_word_size: int = 150, chunk_overlap_words: int = 30) -> list[str]:
    """
    Splits text into overlapping chunks based on word count.
    """
    chunks = []
    if not text.strip():
        return chunks
    words = text.strip().split()
    if not words:
        return chunks
    chunk_word_size = max(1, min(chunk_word_size, len(words)))
    chunk_overlap_words = max(0, min(chunk_overlap_words, chunk_word_size - 1))
    current_idx = 0
    while current_idx < len(words):
        end_idx = min(current_idx + chunk_word_size, len(words))
        chunk_words = words[current_idx:end_idx]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        current_idx += chunk_word_size - chunk_overlap_words
        if chunk_word_size - chunk_overlap_words <= 0 and current_idx < len(words):
            current_idx += 1
        if current_idx >= len(words) and len(chunks) > 0 and (len(" ".join(chunks)) < len(text.strip()) or len(words) == chunk_word_size):
            last_chunk = " ".join(words[max(0, len(words) - chunk_word_size):])
            if last_chunk not in chunks:
                chunks.append(last_chunk)
            break
        elif current_idx >= len(words):
            break
    final_chunks = []
    seen = set()
    for chunk in chunks:
        if chunk not in seen:
            final_chunks.append(chunk)
            seen.add(chunk)
    logging.info(f"Chunked text into {len(final_chunks)} chunks (original chars: {len(text.strip())})")
    return final_chunks
async def extract_text_from_pdf(file_stream: io.BytesIO) -> list[str]:
    """Extracts text from a PDF and returns it as a list of chunks."""
    full_text_content = []
    try:
        doc = await run_in_threadpool(fitz.open, stream=file_stream.read(), filetype="pdf")
        for page_num in range(doc.page_count):
            page = await run_in_threadpool(doc.load_page, page_num)
            text = await run_in_threadpool(page.get_text)
            if text.strip():
                full_text_content.append(text)
            img_list = await run_in_threadpool(page.get_images, full=True)
            for img_index, img in enumerate(img_list):
                xref = img[0]
                base_image = await run_in_threadpool(doc.extract_image, xref)
                image_bytes = base_image["image"]
                try:
                    img_pillow = await run_in_threadpool(Image.open, io.BytesIO(image_bytes))
                    if img_pillow.mode != 'L':
                        img_pillow = await run_in_threadpool(img_pillow.convert, 'L')
                    ocr_text = await run_in_threadpool(pytesseract.image_to_string, img_pillow)
                    if ocr_text.strip():
                        full_text_content.append(f"\n--- OCR Text from PDF Image (Page {page_num+1}, Image {img_index+1}) ---\n{ocr_text.strip()}\n--- End OCR ---")
                except Exception as img_e:
                    logging.warning(f"Could not process image for OCR on PDF page {page_num+1}, image {img_index+1}: {img_e}")
        await run_in_threadpool(doc.close)
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}", exc_info=True)
        return [f"Error extracting text from PDF: {str(e)}"]
    return chunk_text("\n\n".join(full_text_content))
async def extract_text_from_docx(file_stream: io.BytesIO) -> list[str]:
    """Extracts text from a DOCX and returns it as a list of chunks."""
    full_text_content = []
    try:
        document = await run_in_threadpool(Document, file_stream)
        for paragraph in document.paragraphs:
            text = paragraph.text.strip() 
            if text:
                full_text_content.append(text)
        for rel in document.part.rels:
            if "image" in document.part.rels[rel].target_ref:
                image_part = document.part.rels[rel].target_part
                image_bytes = image_part.blob
                try:
                    img_pillow = await run_in_threadpool(Image.open, io.BytesIO(image_bytes))
                    if img_pillow.mode != 'L':
                        img_pillow = await run_in_threadpool(img_pillow.convert, 'L')
                    ocr_text = await run_in_threadpool(pytesseract.image_to_string, img_pillow)
                    if ocr_text.strip():
                        full_text_content.append(f"\n--- OCR Text from Embedded DOCX Image ---\n{ocr_text.strip()}\n--- End OCR ---")
                except Exception as img_e:
                    logging.warning(f"Could not process embedded DOCX image for OCR: {img_e}")
    except Exception as e:
        logging.error(f"Error extracting text from DOCX: {e}", exc_info=True)
        return [f"Error extracting text from DOCX: {str(e)}"]
    return chunk_text("\n\n".join(full_text_content))