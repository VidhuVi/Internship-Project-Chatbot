import azure.functions as func
import logging
import json
import os
import io
import re
import uuid
import http.client
from collections import defaultdict

from openai import AzureOpenAI

# For file processing and OCR
from docx import Document
import fitz # PyMuPDF for PDF processing
from PIL import Image # Pillow for image manipulation (for OCR)
import pytesseract # For OCR

# --- Tesseract Path ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Ensure this is correct!


# Initialize the Function App instance
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# --- Global In-Memory Storage for Uploaded Files (Now stores chunks) ---
file_storage = defaultdict(list)
# --- End Global Storage ---


# Initialize Azure OpenAI Client globally
client = None
try:
    client = AzureOpenAI(
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15"),
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    )
    logging.info("AzureOpenAI client initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize AzureOpenAI client: {e}", exc_info=True)
    client = None


# --- Text Chunking Helper Function (REFINED parameters) ---
# Adjusted chunk_word_size to allow more chunks to fit in context
def chunk_text(text: str, chunk_word_size: int = 150, chunk_overlap_words: int = 30) -> list[str]:
    """
    Splits text into overlapping chunks based on word count.
    Adjusted for robustness and smaller chunk size.
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


# --- Helper function for manual multipart parsing --- (Unchanged)
def _parse_multipart_formdata(req_body_bytes, content_type_header):
    form_data = {}
    files = []
    match = re.search(r'boundary=([^;]+)', content_type_header)
    if not match:
        raise ValueError("Boundary not found in Content-Type header")
    boundary = match.group(1).encode('utf-8')
    parts = [p for p in req_body_bytes.split(b'--' + boundary) if p.strip()]
    for part in parts:
        headers_and_content = part.split(b'\r\n\r\n', 1)
        if len(headers_and_content) != 2:
            continue
        raw_headers = headers_and_content[0].decode('utf-8').strip().split('\r\n')
        content = headers_and_content[1].strip(b'\r\n')
        field_name = None
        file_name = None
        file_content_type = None
        for header_line in raw_headers:
            if header_line.lower().startswith('content-disposition'):
                name_match = re.search(r'name="([^"]+)"', header_line)
                if name_match:
                    field_name = name_match.group(1)
                filename_match = re.search(r'filename="([^"]+)"', header_line)
                if filename_match:
                    file_name = filename_match.group(1)
            elif header_line.lower().startswith('content-type'):
                file_content_type = header_line.split(':', 1)[1].strip()
        if field_name:
            if file_name:
                files.append({
                    'name': field_name,
                    'filename': file_name,
                    'content_type': file_content_type,
                    'content': content
                })
            else:
                form_data[field_name] = content.decode('utf-8')
    return form_data, files

# --- File Extraction Functions (Calls Refined chunk_text) ---
def extract_text_from_pdf(file_stream: io.BytesIO) -> list[str]:
    full_text_content = []
    try:
        doc = fitz.open(stream=file_stream.read(), filetype="pdf")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text = page.get_text().strip()
            if text:
                full_text_content.append(text)

            img_list = page.get_images(full=True)
            for img_index, img in enumerate(img_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                try:
                    img_pillow = Image.open(io.BytesIO(image_bytes))
                    if img_pillow.mode != 'L':
                        img_pillow = img_pillow.convert('L')
                    ocr_text = pytesseract.image_to_string(img_pillow)
                    if ocr_text.strip():
                        full_text_content.append(f"\n--- OCR Text from PDF Image (Page {page_num+1}, Image {img_index+1}) ---\n{ocr_text.strip()}\n--- End OCR ---")
                except Exception as img_e:
                    logging.warning(f"Could not process image for OCR on PDF page {page_num+1}, image {img_index+1}: {img_e}")
        doc.close()
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}", exc_info=True)
        return [f"Error extracting text from PDF: {str(e)}"]

    return chunk_text("\n\n".join(full_text_content))


def extract_text_from_docx(file_stream: io.BytesIO) -> list[str]:
    full_text_content = []
    try:
        document = Document(file_stream)
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                full_text_content.append(text)

        for rel in document.part.rels:
            if "image" in document.part.rels[rel].target_ref:
                image_part = document.part.rels[rel].target_part
                image_bytes = image_part.blob
                try:
                    img_pillow = Image.open(io.BytesIO(image_bytes))
                    if img_pillow.mode != 'L':
                        img_pillow = img_pillow.convert('L')
                    ocr_text = pytesseract.image_to_string(img_pillow)
                    if ocr_text.strip():
                        full_text_content.append(f"\n--- OCR Text from Embedded DOCX Image ---\n{ocr_text.strip()}\n--- End OCR ---")
                except Exception as img_e:
                    logging.warning(f"Could not process embedded DOCX image for OCR: {img_e}")
    except Exception as e:
        logging.error(f"Error extracting text from DOCX: {e}", exc_info=True)
        return [f"Error extracting text from DOCX: {str(e)}"]

    return chunk_text("\n\n".join(full_text_content))


# --- File Upload HTTP Trigger (MODIFIED to store chunks) ---
@app.function_name(name="upload_file")
@app.route(route="upload-file", methods=["POST"])
def upload_file(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function (upload_file) processed a request.')

    uploaded_file_refs = []
    try:
        content_type_header = req.headers.get('Content-Type', '')
        if not content_type_header.startswith('multipart/form-data'):
            logging.warning("Upload_file received non-multipart/form-data request.")
            return func.HttpResponse(
                json.dumps({"message": "Expected multipart/form-data request for file upload."}),
                mimetype="application/json",
                status_code=http.client.BAD_REQUEST
            )

        form_fields, uploaded_files_data = _parse_multipart_formdata(req.get_body(), content_type_header)

        for file_data in uploaded_files_data:
            file_name = file_data['filename']
            file_content_type = file_data['content_type']
            file_stream = io.BytesIO(file_data['content'])

            logging.info(f"Processing uploaded file: {file_name} (Content-Type: {file_content_type})")

            extracted_chunks = []
            if file_content_type == 'application/pdf':
                extracted_chunks = extract_text_from_pdf(file_stream)
            elif file_content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                extracted_chunks = extract_text_from_docx(file_stream) # Corrected assignment
            else:
                logging.warning(f"Unsupported file type uploaded: {file_name} ({file_content_type})")
                return func.HttpResponse(
                    json.dumps({"message": f"Unsupported file type: {file_name} ({file_content_type}). Only PDF and DOCX are allowed."}),
                    mimetype="application/json",
                    status_code=http.client.BAD_REQUEST
                )

            # Store each chunk with a unique ID and associate it with the file
            file_id = str(uuid.uuid4()) # Unique ID for this *document*
            for i, chunk_content in enumerate(extracted_chunks):
                if chunk_content.strip(): 
                    chunk_obj = {
                        'chunk_id': str(uuid.uuid4()),
                        'content': chunk_content,
                        'file_name': file_name,
                        'file_id': file_id,
                        'chunk_index': i
                    }
                    file_storage[file_id].append(chunk_obj)

            num_stored_chunks = len(file_storage[file_id])
            if num_stored_chunks == 0 and extracted_chunks:
                logging.warning(f"No valid non-empty chunks were stored for file {file_name} (ID: {file_id}) despite extraction. Original text might be empty or unchunkable.")

            uploaded_file_refs.append({"id": file_id, "name": file_name, "num_chunks": num_stored_chunks})

            logging.info(f"Extracted and stored {num_stored_chunks} chunks for file {file_name} with Document ID: {file_id}. Total content length (from stored chunks): {sum(len(c['content']) for c in file_storage[file_id])} chars.")

        if not uploaded_file_refs:
            return func.HttpResponse(
                json.dumps({"message": "No valid files uploaded."}),
                mimetype="application/json",
                status_code=http.client.BAD_REQUEST
            )

        return func.HttpResponse(
            json.dumps({"message": "Files uploaded and processed successfully.", "fileRefs": uploaded_file_refs}),
            mimetype="application/json",
            status_code=http.client.OK
        )

    except Exception as e:
        logging.error(f"An unexpected error occurred during file upload processing: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"message": f"An internal server error occurred during file upload: {str(e)}"}),
            mimetype="application/json",
            status_code=http.client.INTERNAL_SERVER_ERROR
        )

# --- Chat HTTP Trigger (MODIFIED for Chunk Retrieval) ---
@app.function_name(name="HttpExample")
@app.route(route="HttpExample", methods=["POST"])
def http_example(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function (HttpExample) processed a request.')

    if not client:
        return func.HttpResponse(
            json.dumps({"message": "Azure OpenAI client not initialized. Check your application settings and logs."}),
            mimetype="application/json",
            status_code=http.client.INTERNAL_SERVER_ERROR
        )

    conversation_history = None

    try:
        retrieved_contents = [] # Initialize here
        file_context_string = "" # Initialize here

        req_body = req.get_json()
        conversation_history = req_body.get('conversation')
        received_file_refs = req_body.get('fileRefs', [])

        # --- Retrieve and select relevant chunks ---
        all_relevant_chunks = []
        if received_file_refs:
            user_query = ""
            for msg in reversed(conversation_history):
                if msg['role'] == 'user':
                    user_query = msg['content']
                    break

            # Clean the user query to remove "[Files attached: ...]" noise
            user_query_cleaned = re.sub(r'\[Files attached:.*?\]', '', user_query).strip()
            logging.info(f"Original user query: '{user_query}'")
            logging.info(f"Cleaned user query for keyword extraction: '{user_query_cleaned}'")

            for ref in received_file_refs:
                file_id = ref.get('id')
                file_name = ref.get('name', 'unknown_file')
                if file_id and file_id in file_storage:
                    all_relevant_chunks.extend(file_storage[file_id])
                    logging.info(f"Retrieved {len(file_storage[file_id])} chunks for document ID: {file_id} ({file_name})")
                else:
                    logging.warning(f"Document content for ID '{file_id}' not found in storage (name: {file_name}).")

            # Use cleaned user query for keyword extraction
            query_keywords = set(word.lower() for word in user_query_cleaned.split() if len(word) > 2)

            scored_chunks = []
            for chunk_obj in all_relevant_chunks:
                score = sum(1 for keyword in query_keywords if keyword in chunk_obj['content'].lower())
                scored_chunks.append((score, chunk_obj))

            scored_chunks.sort(key=lambda x: x[0], reverse=True)

            top_k = 5
            selected_chunks = []
            added_content_length = 0
            max_context_length = 2500 # Increased to allow more chunks

            logging.info(f"User query keywords for retrieval: {list(query_keywords)}")
            logging.info(f"Total chunks available for retrieval: {len(all_relevant_chunks)}")
            logging.info(f"Max context length allowed: {max_context_length} chars.")

            for score, chunk_obj in scored_chunks:
                logging.info(f"Evaluating chunk (score: {score}, current context len: {added_content_length}): {chunk_obj['content'][:50]}...")

                if score > 0 and len(selected_chunks) < top_k:
                    estimated_chunk_len = len(chunk_obj['content']) + len(f"--- Document Context (from {chunk_obj['file_name']}) ---\n\n--- End Context ---") + 20 # Add more buffer

                    if added_content_length + estimated_chunk_len <= max_context_length:
                        selected_chunks.append(f"--- Document Context (from {chunk_obj['file_name']}) ---\n{chunk_obj['content']}\n--- End Context ---")
                        added_content_length += estimated_chunk_len
                        logging.info(f"Chunk selected. New context length: {added_content_length}. Chunks selected: {len(selected_chunks)}")
                    else:
                        logging.info(f"Chunk from {chunk_obj['file_name']} (score {score}) would exceed max_context_length. Stopping retrieval.")
                        break 
                elif len(selected_chunks) >= top_k:
                    logging.info(f"Already selected top_k ({top_k}) relevant chunks. Stopping retrieval.")
                    break
                else:
                    logging.info(f"Skipping chunk from {chunk_obj['file_name']} due to score 0 (no matching keywords). Stopping retrieval for remaining chunks.")
                    break 

            file_context_string = "\n\n".join(selected_chunks)
            logging.info(f"Final selected {len(selected_chunks)} chunks for context. Total selected context length: {len(file_context_string)} chars.")

            for ref in received_file_refs:
                file_id = ref.get('id')
                if file_id in file_storage:
                    del file_storage[file_id]
            if selected_chunks:
                logging.info(f"Cleared associated document chunks for {len(received_file_refs)} files from in-memory storage after use (if found).")
        else:
            file_context_string = ""


        if not conversation_history or not isinstance(conversation_history, list) or not all(isinstance(m, dict) and 'role' in m and 'content' in m for m in conversation_history):
            logging.warning("Invalid 'conversation' data received in HttpExample.")
            return func.HttpResponse(
                json.dumps({"message": "Please send a valid 'conversation' array in the request body."}),
                mimetype="application/json",
                status_code=http.client.BAD_REQUEST
            )

        messages_for_openai = list(conversation_history)

        if file_context_string:
            messages_for_openai.insert(0, {"role": "system", "content": f"The user has provided the following *relevant document context* related to your query. Use this information to answer precisely:\n{file_context_string}\n\nBased on this context and our conversation history, provide a helpful and concise response."})
        else:
            pass 

        last_user_message = next((m['content'] for m in reversed(messages_for_openai) if m['role'] == 'user'), 'N/A')
        logging.info(f"Sending conversation to OpenAI (last user message: '{last_user_message}') with selected file context length: {len(file_context_string)} chars.")

        deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
        if not deployment_name:
            logging.error("AZURE_OPENAI_DEPLOYMENT_NAME environment variable is not set.")
            return func.HttpResponse(
                json.dumps({"message": "Azure OpenAI deployment name is missing."}),
                mimetype="application/json",
                status_code=http.client.INTERNAL_SERVER_ERROR
            )

        stream_response_chunks = client.chat.completions.create(
            model=deployment_name,
            messages=messages_for_openai,
            temperature=0.7,
            max_tokens=500,
            stream=True
        )

        sse_lines = []

        sse_lines.append("event: start\n")
        sse_lines.append("data: {}\n")

        for chunk in stream_response_chunks:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                sse_lines.append(f"data: {json.dumps({'token': token})}\n")

        sse_lines.append("event: end\n")
        sse_lines.append("data: {}\n")

        full_sse_body = "\n".join(sse_lines) + "\n"

        logging.info("Simulated streaming complete; returning full SSE body to frontend.")

        return func.HttpResponse(
            full_sse_body,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            },
            status_code=http.client.OK
        )

    except json.JSONDecodeError:
        logging.error("Request body could not be parsed as JSON in HttpExample. Expected JSON payload for chat queries.")
        return func.HttpResponse(
            json.dumps({"message": "Request body could not be parsed as JSON. Expected JSON payload for chat queries."}),
            mimetype="application/json",
            status_code=http.client.BAD_REQUEST
        )
    except Exception as e:
        logging.error(f"An unexpected error occurred in HttpExample function: {e}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"message": f"An internal server error occurred: {str(e)}"}),
            mimetype="application/json",
            status_code=http.client.INTERNAL_SERVER_ERROR
        )