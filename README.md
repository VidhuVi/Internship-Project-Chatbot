# AI Chatbot with Document Understanding and Streaming Responses

This project implements a conversational AI chatbot with the ability to upload and process PDF and DOCX documents. It leverages Azure OpenAI for generating responses and provides a real-time, streaming chat experience. The frontend is built with React and styled with Tailwind CSS, while the backend is a Python Azure Function.

## Features

- **Conversational Chat Interface:** A familiar ChatGPT-style UI for natural interactions.
- **Document Upload:** Supports uploading single or multiple PDF and DOCX files.
- **Smart Document Processing:**
  - Extracts text from PDF and DOCX files.
  - Performs **OCR (Optical Character Recognition)** on images embedded within documents or scanned PDF pages to extract text.
  - **Intelligent Document Chunking:** Breaks down large documents into smaller, manageable chunks.
  - **Contextual Retrieval:** Employs a basic keyword-based retrieval mechanism to select the most relevant document chunks based on the user's query, ensuring only pertinent information is sent to the AI.
- **Azure OpenAI Integration:** Uses Azure OpenAI's `chat/completions` API for AI responses.
- **Streaming Responses:** Provides a token-by-token (word-by-word) display of AI responses for a dynamic, real-time user experience.
- **Error Handling:** Gracefully handles file processing and API errors.
- **Modern UI:** A clean, responsive design with a sleek dark theme, built with React and Tailwind CSS.

## Technologies Used

### Frontend

- **React.js:** For building the user interface.
- **Tailwind CSS:** For rapid and responsive UI styling.
- **Lucide React (simulated via inline SVG):** For modern, customizable icons.

### Backend

- **Python:** The core language for the backend logic.
- **Azure Functions:** Serverless compute platform for hosting the backend API.
- **Azure OpenAI Service:** Provides the large language model (LLM) capabilities.
- **`openai` library:** Python client for interacting with Azure OpenAI.
- **`PyMuPDF` (fitz):** For efficient PDF text and image extraction.
- **`python-docx`:** For parsing and extracting content from DOCX files.
- **`pytesseract` (with Tesseract-OCR):** For performing OCR on image content within documents.
- **In-memory Storage:** Temporary storage for processed document chunks (for local development only).

## Project Structure

```
MyChatProject/
├── chat-backend/             # Python Azure Function Backend
│   ├── function_app.py       # Main Azure Function logic (API endpoints, OCR, chunking, LLM calls)
│   ├── host.json             # Azure Functions host configuration (e.g., routing prefix)
│   ├── local.settings.json   # Local environment variables (API keys - IGNORED by Git)
│   ├── requirements.txt      # Python dependencies
│   └── .gitignore            # Git ignore rules for Python specific files (venv, __pycache__, etc.)
└── chat-ui/                  # React Frontend
    ├── public/               # Public assets, including index.html with Tailwind CDN
    │   └── index.html
    ├── src/                  # React source code
    │   ├── App.js            # Main React component, chat logic, UI, API calls
    │   ├── App.css           # Custom CSS for specific styling (e.g., scrollbars, base styles)
    │   ├── ...               # Other React boilerplate files (index.js, reportWebVitals.js etc.)
    ├── package.json          # Node.js project metadata and dependencies
    ├── package-lock.json     # Exact dependency versions
    └── .gitignore            # Git ignore rules for Node.js specific files (node_modules, build, etc.)
```

## Setup and Running Locally

### Prerequisites

1.  **Node.js & npm:** [Install Node.js](https://nodejs.org/en/download/) (which includes npm).
2.  **Python 3.10+:** [Install Python](https://www.python.org/downloads/).
3.  **Azure Functions Core Tools v4:** [Install Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local?tabs=v4%2Cwindows%2Ccsharp%2Cportal%2Cbash%2Ck8s&pivots=programming-language-python#install-the-azure-functions-core-tools).
    - `npm install -g azure-functions-core-tools@4 --unsafe-perm true`
4.  **Tesseract-OCR:** [Install Tesseract-OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html). Remember to note down the installation path (e.g., `C:\Program Files\Tesseract-OCR\tesseract.exe` on Windows or `/usr/local/bin/tesseract` on macOS/Linux).
5.  **Azure OpenAI Service:**
    - Access to an Azure subscription.
    - An Azure OpenAI resource with a deployed model (e.g., `gpt-4o-mini`, `gpt-35-turbo`). You'll need its:
      - **API Key**
      - **Endpoint URL** (e.g., `https://YOUR_RESOURCE_NAME.openai.azure.com/`)
      - **Deployment Name** (the name you gave your deployed model)

### Backend Setup (`chat-backend` folder)

1.  **Navigate to the `chat-backend` directory:**
    ```bash
    cd chat-backend
    ```
2.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    ```
3.  **Activate the virtual environment:**
    - **Windows:** `.\venv\Scripts\activate`
    - **macOS/Linux:** `source venv/bin/activate`
4.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Configure environment variables:**
    - Create a file named `local.settings.json` in the `chat-backend` directory (if it doesn't exist).
    - Populate it with your Azure OpenAI details:
      ```json
      {
        "IsEncrypted": false,
        "Values": {
          "FUNCTIONS_WORKER_RUNTIME": "python",
          "AzureWebJobsStorage": "",
          "AZURE_OPENAI_API_KEY": "YOUR_AZURE_OPENAI_API_KEY",
          "AZURE_OPENAI_ENDPOINT": "YOUR_AZURE_OPENAI_ENDPOINT",
          "AZURE_OPENAI_API_VERSION": "2024-02-15", // Or the version you deployed with
          "AZURE_OPENAI_DEPLOYMENT_NAME": "YOUR_AZURE_OPENAI_DEPLOYMENT_NAME"
        }
      }
      ```
      **Important:** Replace `YOUR_AZURE_OPENAI_API_KEY`, `YOUR_AZURE_OPENAI_ENDPOINT`, and `YOUR_AZURE_OPENAI_DEPLOYMENT_NAME` with your actual values.
    - Open `function_app.py` and ensure `pytesseract.pytesseract.tesseract_cmd` is correctly set to your Tesseract installation path:
      ```python
      pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe' # Example
      ```

### Frontend Setup (`chat-ui` folder)

1.  **Navigate to the `chat-ui` directory:**
    ```bash
    cd chat-ui
    ```
2.  **Install Node.js dependencies:**
    ```bash
    npm install
    ```
3.  **Integrate Tailwind CSS CDN:**
    - Open `public/index.html`.
    - Add the following line inside the `<head>` section (e.g., before the `<title>` tag):
      ```html
      <script src="[https://cdn.tailwindcss.com](https://cdn.tailwindcss.com)"></script>
      ```

### Running the Application

1.  **Start the Backend (Azure Function):**

    - Open a **new terminal** or command prompt.
    - Navigate to your `chat-backend` directory.
    - Activate your Python virtual environment: `.\venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux).
    - Run the Azure Function host:
      ```bash
      func start
      ```
    - Keep this terminal open. It will show backend logs.

2.  **Start the Frontend (React App):**
    - Open **another new terminal** or command prompt.
    - Navigate to your `chat-ui` directory.
    - Start the React development server:
      ```bash
      npm start
      ```
    - This will typically open your browser to `http://localhost:3000`.

## Usage

1.  Open your browser to `http://localhost:3000`.
2.  Use the chat input box to send messages to the AI.
3.  To provide document context, drag and drop PDF or DOCX files onto the designated area, or click "click to browse" to select them.
4.  Once files are uploaded (indicated by filename chips), ask questions that refer to their content (e.g., "Summarize the attached document", "What does this file say about X?").
5.  Observe the AI's real-time, streaming responses.

## Future Improvements

- **Advanced RAG (Retrieval Augmented Generation):** Replace the simple keyword-based retrieval with vector embeddings and a dedicated vector database (e.g., Azure Cognitive Search, Pinecone, ChromaDB) for more accurate and semantic context retrieval.
- **Persistent File Storage:** Implement Azure Blob Storage to store uploaded files durably instead of in-memory for production readiness.
- **User Authentication:** Add user login to manage chat history and uploaded files per user.
- **Chat History Persistence:** Store chat history in a database (e.g., Azure Cosmos DB, Azure SQL Database) for continuity across sessions.
- **Scalable Backend:** Optimize the Azure Function for high-concurrency scenarios, potentially using Durable Functions for long-running file processing workflows.
- **More File Types:** Extend support to other document types like TXT, CSV, image files (if not already handled by OCR).
