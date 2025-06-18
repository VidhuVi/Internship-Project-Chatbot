from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from typing import AsyncGenerator
import json, re, os, uuid, io
from openai import AsyncAzureOpenAI
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
import logging

from starlette.concurrency import run_in_threadpool

from shared import chunk_text, extract_text_from_pdf, extract_text_from_docx # Ensure these are async in shared.py

logging.basicConfig(level=logging.INFO) # Set to INFO for clearer logs, use DEBUG for most verbose

app = FastAPI(root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GLOBAL IN-MEMORY FILE STORAGE ---
file_storage = defaultdict(list)
logging.info(f"fastapi_app.py: Global file_storage initialized or re-initialized. Current keys: {list(file_storage.keys())}")


# --- Initialize Azure OpenAI Client at module level ---
client: AsyncAzureOpenAI = None
try:
    logging.info("Attempting to initialize AsyncAzureOpenAI client at module level...")
    client = AsyncAzureOpenAI(
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15"),
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    )
    logging.info("AsyncAzureOpenAI client initialized successfully at module level.")
except Exception as e:
    logging.error(f"Failed to initialize AsyncAzureOpenAI client at module level: {e}", exc_info=True)
    client = None


# --- CHAT ENDPOINT ---
@app.post("/chat")
async def chat(request: Request):
    logging.info("--- /chat endpoint received request ---")
    logging.info(f"CHAT: Global file_storage keys at start of /chat: {list(file_storage.keys())}")

    body = await request.json()
    logging.info(f"CHAT: Request body received. Keys: {body.keys()}")

    conversation_history = body.get("conversation")
    received_file_refs = body.get("fileRefs", [])
    file_context_string = ""

    if not client:
        logging.error("CHAT: Azure OpenAI client is NOT initialized when /chat was called. Returning 500.")
        return JSONResponse(status_code=500, content={"message": "Backend service not ready. OpenAI client not initialized."})

    messages = list(conversation_history) 

    if received_file_refs:
        logging.info(f"CHAT: Received file references in /chat payload: {received_file_refs}")

        last_user_message_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]['role'] == 'user':
                last_user_message_index = i
                break

        if last_user_message_index != -1:
            original_user_content = messages[last_user_message_index]['content']
            user_query_cleaned = re.sub(r'\[Files attached:.*?\]', '', original_user_content).strip()
            messages[last_user_message_index]['content'] = user_query_cleaned
            logging.info(f"CHAT: Cleaned user message in conversation history: '{original_user_content}' -> '{user_query_cleaned}'")
            user_query = user_query_cleaned
        else:
            user_query = ""

        query_keywords = set(word.lower() for word in user_query.split() if len(word) > 2)
        logging.info(f"CHAT: Extracted query keywords (from cleaned query): {list(query_keywords)}")


        all_chunks = []
        for ref in received_file_refs:
            file_id = ref.get("id")
            file_name = ref.get("name", "unknown_file")
            if file_id in file_storage:
                logging.info(f"CHAT: Found chunks for file_id: {file_id} ({file_name}). Number of chunks: {len(file_storage[file_id])}")
                all_chunks.extend(file_storage[file_id])
            else:
                logging.warning(f"CHAT: File ID {file_id} ({file_name}) NOT FOUND in file_storage during retrieval for /chat. Content will be missing.")

        logging.info(f"CHAT: Total chunks retrieved from storage for processing: {len(all_chunks)}")

        scored_chunks = []
        if all_chunks: # Only proceed if chunks were actually retrieved
            for c in all_chunks:
                score = sum(1 for kw in query_keywords if kw in c["content"].lower())
                scored_chunks.append((score, c))

            scored_chunks.sort(key=lambda x: x[0], reverse=True)
            logging.info(f"CHAT: Top 5 scored chunks (score, filename, first 50 chars):")
            for score, chunk_obj in scored_chunks[:5]:
                logging.info(f"- Score: {score}, File: {chunk_obj['file_name']}, Chunk: '{chunk_obj['content'][:50]}...'")
        else:
            logging.info("CHAT: No chunks retrieved, skipping scoring and selection.")

        selected = []
        added_len = 0
        max_context_length = 3000
        top_k_chunks = 5

        for score, c in scored_chunks:
            if score > 0 and len(selected) < top_k_chunks:
                block_header_footer_len = len(f"--- Document Context (from {c['file_name']}) ---\n\n--- End Context ---") + 20
                potential_block_len = len(c["content"]) + block_header_footer_len

                if added_len + potential_block_len <= max_context_length:
                    selected.append(f"--- Document Context (from {c['file_name']}) ---\n{c['content']}\n--- End Context ---")
                    added_len += potential_block_len
                    logging.info(f"CHAT: Selected chunk (score {score}). Current context chars: {added_len}. Chunks selected: {len(selected)}")
                else:
                    logging.info(f"CHAT: Skipping chunk (score {score}) due to max_context_length ({max_context_length}) being exceeded. Current added_len: {added_len}.")
                    break
            elif len(selected) >= top_k_chunks:
                logging.info(f"CHAT: Reached top_k_chunks ({top_k_chunks}). Stopping retrieval.")
                break
            elif score == 0 and len(query_keywords) > 0:
                logging.info(f"CHAT: Skipping chunk (score 0). No more relevant chunks found based on keywords.")
                break

        file_context_string = "\n\n".join(selected)
        logging.info(f"CHAT: Final file_context_string length: {len(file_context_string)} chars. Selected {len(selected)} chunks.")

        # IMPORTANT: Clear chunks from in-memory storage *after* use for the current request
        # This is done for memory management, assuming a file's context is only for one specific query.
        # If you need context to persist for subsequent queries, you'd need a different strategy (e.g. database).
        # for ref in received_file_refs:
        #     file_id = ref.get('id')
        #     if file_id in file_storage:
        #         logging.info(f"CHAT: Deleting file_id {file_id} from file_storage after use for this chat request.")
        #         del file_storage[file_id]
        # logging.info(f"CHAT: Global file_storage keys after clearing for this request: {list(file_storage.keys())}")


    if file_context_string:
        messages.insert(0, {
            "role": "system",
            "content": f"The user has provided the following *relevant document context* related to their query. Use this information to answer precisely:\n{file_context_string}\n\nBased on this context and our conversation history, provide a helpful and concise response."
        })
        logging.info(f"CHAT: System message with file context added. Total messages for OpenAI: {len(messages)}")
    else:
        logging.info("CHAT: No file context added to system message.")

    logging.info("CHAT: Attempting to call client.chat.completions.create...")
    try:
        stream_response = await client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            messages=messages,
            temperature=0.7,
            max_tokens=500,
            stream=True
        )
        logging.info("CHAT: client.chat.completions.create call initiated successfully.")
    except Exception as e:
        logging.error(f"CHAT: Error calling OpenAI API: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Error communicating with OpenAI API: {str(e)}"})

    async def event_stream() -> AsyncGenerator[str, None]:
        logging.info("CHAT: Starting event_stream generator for true streaming.")
        yield "event: start\ndata: {}\n\n"
        try:
            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    logging.debug(f"CHAT: Streamed token: {token}")
        except Exception as e:
            logging.error(f"CHAT: Error during streaming response in event_stream: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': f'Streaming error: {str(e)}'})}\n\n"
        finally:
            yield "event: end\ndata: {}\n\n"
            logging.info("CHAT: Event_stream generator finished.")

    logging.info("CHAT: Returning StreamingResponse from /chat endpoint.")
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# --- UPLOAD FILE ENDPOINT ---
@app.post("/upload-file")
async def upload_file_endpoint(files: list[UploadFile] = File(...)):
    logging.info("--- /upload-file endpoint received request ---")
    logging.info(f"UPLOAD: Global file_storage keys at start of /upload-file: {list(file_storage.keys())}")
    file_refs = []

    if not client:
        logging.error("UPLOAD: Azure OpenAI client is not initialized. Returning 500.")
        return JSONResponse(status_code=500, content={"message": "Backend service not ready. OpenAI client not initialized."})


    for file in files:
        content_type = file.content_type
        file_name = file.filename
        file_id = str(uuid.uuid4())

        logging.info(f"UPLOAD: Processing file {file_name} (Type: {content_type}) with new ID: {file_id}")

        file_bytes = await file.read()
        stream = io.BytesIO(file_bytes)

        chunks = []
        try:
            if content_type == 'application/pdf':
                chunks = await extract_text_from_pdf(stream)
            elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                chunks = await extract_text_from_docx(stream)
            else:
                logging.warning(f"UPLOAD: Unsupported file type: {content_type} for file {file_name}. Returning 400.")
                return JSONResponse(status_code=400, content={"message": f"Unsupported file type: {content_type}"})
        except Exception as e:
            logging.error(f"UPLOAD: Error during text extraction for {file_name}: {e}", exc_info=True)
            return JSONResponse(status_code=500, content={"message": f"Error processing file {file_name}: {str(e)}"})

        num_stored_chunks = 0
        # Ensure file_id key exists before appending
        if file_id not in file_storage:
            file_storage[file_id] = []

        for i, chunk_content in enumerate(chunks):
            if chunk_content.strip(): # Only store non-empty chunks
                chunk_obj = {
                    "chunk_id": str(uuid.uuid4()),
                    "content": chunk_content,
                    "file_name": file_name,
                    "file_id": file_id,
                    "chunk_index": i
                }
                file_storage[file_id].append(chunk_obj)
                num_stored_chunks += 1

        logging.info(f"UPLOAD: Extracted {len(chunks)} total chunks, stored {num_stored_chunks} non-empty chunks for {file_name} (ID: {file_id}).")

        file_refs.append({
            "id": file_id,
            "name": file_name,
            "num_chunks": num_stored_chunks
        })

    logging.info(f"UPLOAD: Global file_storage keys after processing ALL uploaded files: {list(file_storage.keys())}")
    logging.info("UPLOAD: Returning JSONResponse from /upload-file endpoint.")
    return JSONResponse(content={"message": "Files uploaded successfully.", "fileRefs": file_refs})