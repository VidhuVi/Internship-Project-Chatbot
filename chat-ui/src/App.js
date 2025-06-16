import React, { useState, useEffect, useRef } from 'react';
import './App.css'; // Keep existing CSS for general layout/overrides

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false); // Re-introduced for drag-and-drop
  const [uploadedFileRefs, setUploadedFileRefs] = useState([]);
  const [isFileUploading, setIsFileUploading] = useState(false);
  const [isResponding, setIsResponding] = useState(false);

  const fileInputRef = useRef(null); // Ref for the hidden file input

  // Auto-scrolling to the bottom of the chat
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const addFiles = async (files) => {
    const allowedFiles = files.filter(file =>
      file.type === 'application/pdf' ||
      file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    );

    if (allowedFiles.length > 0) {
      // Add new files to existing selected files (for display)
      setSelectedFiles(prevFiles => {
        const newFiles = [...prevFiles];
        allowedFiles.forEach(file => {
          if (!newFiles.some(f => f.name === file.name && f.size === file.size)) {
            newFiles.push(file);
          }
        });
        return newFiles;
      });

      await uploadFilesToBackend(allowedFiles);
    }
  };

  const uploadFilesToBackend = async (filesToUpload) => {
    setIsFileUploading(true);
    const formData = new FormData();
    filesToUpload.forEach((file, index) => {
      formData.append(`file${index}`, file);
    });

    try {
      const response = await fetch('http://localhost:7071/api/upload-file', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      if (data.fileRefs && Array.isArray(data.fileRefs)) {
        setUploadedFileRefs(prevRefs => [...prevRefs, ...data.fileRefs]);
        // Clear the actual file input's value after successful upload
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      } else {
        console.error("Backend did not return valid file references:", data);
        alert("Error: Backend did not return valid file references.");
      }
    } catch (error) {
      console.error("Error uploading files to backend:", error);
      alert(`Error uploading files: ${error.message}`);
    } finally {
      setIsFileUploading(false);
    }
  };

  const handleFileSelect = (event) => {
    // Use event.target.files directly, as we're managing selectedFiles separately now
    addFiles(Array.from(event.target.files));
  };

  const handleRemoveFile = (indexToRemove) => {
    setSelectedFiles(prevFiles => {
      const newSelectedFiles = prevFiles.filter((_, index) => index !== indexToRemove);
      // Also remove the corresponding uploadedFileRefs
      setUploadedFileRefs(newUploadedFileRefs => newUploadedFileRefs.filter((ref, index) => {
        // Find the ref that matches the removed file's original name and ID (if possible)
        // This is a simplistic match; for robustness, match by file_id from backend
        return !prevFiles[indexToRemove] || ref.name !== prevFiles[indexToRemove].name;
      }));
      return newSelectedFiles;
    });
  };

  // Drag and Drop Handlers (re-enabled)
  const handleDragOver = (event) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  };

  const handleSendMessage = async () => {
    if (input.trim() === '' && uploadedFileRefs.length === 0) return;

    setIsResponding(true);

    const userMessageText = input.trim();
    let displayMessageContent = userMessageText;
    if (uploadedFileRefs.length > 0) {
      const fileNames = selectedFiles.map(f => f.name).join(', ');
      displayMessageContent += (userMessageText ? "\n\n" : "") + `[Files attached: ${fileNames}]`;
    }
    const newUserMessage = { sender: 'user', text: displayMessageContent };
    const updatedMessagesAfterUser = [...messages, newUserMessage];
    setMessages(updatedMessagesAfterUser);

    setInput('');
    setSelectedFiles([]); // Clear selected file chips from UI after sending message

    const payload = {};
    const conversationHistory = updatedMessagesAfterUser.map(msg => {
      if (msg.sender === 'user') {
        return { role: 'user', content: msg.text };
      } else if (msg.sender === 'assistant') {
        return { role: 'assistant', content: msg.text };
      }
      return null;
    }).filter(Boolean);

    const fullOpenAIMessages = [
      { role: 'system', content: 'You are a helpful and friendly AI assistant. You answer questions concisely and professionally.' },
      ...conversationHistory
    ];
    payload.conversation = fullOpenAIMessages;

    if (uploadedFileRefs.length > 0) {
      payload.fileRefs = uploadedFileRefs;
    }

    let currentAssistantMessage = { sender: 'assistant', text: '' };
    setMessages(prevMessages => [...prevMessages, currentAssistantMessage]);

    try {
      const response = await fetch('http://localhost:7071/api/HttpExample', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(`HTTP error! status: ${response.status} - ${errorData.message || 'Unknown error'}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let accumulatedText = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const eventData = JSON.parse(line.substring(6));
                    if (eventData.token) {
                        accumulatedText += eventData.token;
                        setMessages(prevMessages => {
                            const lastMsgIndex = prevMessages.length - 1;
                            if (lastMsgIndex >= 0 && prevMessages[lastMsgIndex].sender === 'assistant') {
                                const newMessages = [...prevMessages];
                                newMessages[lastMsgIndex] = { ...newMessages[lastMsgIndex], text: accumulatedText };
                                return newMessages;
                            }
                            return prevMessages;
                        });
                        await new Promise(resolve => setTimeout(resolve, 30));
                    }
                } catch (e) {
                    console.error("Error parsing SSE data:", e, line);
                }
            } else if (line.startsWith('event: end')) {
                reader.cancel();
                break;
            }
        }
      }
      decoder.decode(new Uint8Array(), { stream: false });


    } catch (error) {
      console.error("Error during streaming response:", error);
      setMessages(prevMessages => {
        const lastMsgIndex = prevMessages.length - 1;
        if (lastMsgIndex >= 0 && prevMessages[lastMsgIndex].sender === 'assistant' && prevMessages[lastMsgIndex].text === '') {
            const newMessages = [...prevMessages];
            newMessages[lastMsgIndex] = { ...newMessages[lastMsgIndex], text: `Oops! Something went wrong: ${error.message}` };
            return newMessages;
        }
        return [...prevMessages, { sender: 'assistant', text: `Oops! Something went wrong: ${error.message}` }];
      });
    } finally {
      setUploadedFileRefs([]); // Clear file refs after sending, regardless of success/fail
      setIsResponding(false);
    }
  };

  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      handleSendMessage();
      event.preventDefault();
    }
  };

  return (
    <div className="flex justify-center items-center min-h-screen bg-gray-900 font-inter text-gray-100">
      <div className="flex flex-col w-full max-w-xl h-[90vh] md:h-[700px] bg-gray-800 rounded-xl shadow-2xl overflow-hidden border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between p-4 bg-gradient-to-r from-gray-900 to-gray-700 text-white shadow-md">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-message-square-text"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="13" x2="11" y1="11" y2="11"/><line x1="17" x2="11" y1="15" y2="15"/></svg>
            ChatBot
          </h1>
        </div>

        {/* Messages Display Area */}
        <div className="flex-1 p-4 overflow-y-auto flex flex-col gap-3 bg-gray-850 scrollbar-thumb-rounded scrollbar-track-rounded scrollbar-thumb-gray-600 scrollbar-track-gray-800">
          {messages.map((msg, index) => (
            <div key={index} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] p-3 rounded-xl shadow-sm text-sm break-words leading-snug
                  ${msg.sender === 'user'
                    ? 'bg-blue-700 text-white rounded-br-md'
                    : 'bg-gray-700 text-gray-200 rounded-bl-md'
                  }`
                }
              >
                {msg.text}
              </div>
            </div>
          ))}
          {isResponding && messages[messages.length - 1]?.sender !== 'assistant' && (
            <div className="flex justify-start">
              <div className="max-w-[80%] p-3 rounded-xl shadow-sm text-sm break-words leading-snug bg-gray-700 text-gray-200 rounded-bl-md animate-pulse">
                <span>Thinking...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* File Upload Area */}
        <div
          className={`p-4 bg-gray-800 border-t border-gray-700 flex flex-col gap-2 ${isDragging ? 'border-blue-500 bg-gray-700' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div
            className={`flex flex-col items-center justify-center border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors duration-200
              ${selectedFiles.length > 0 ? 'border-blue-600 bg-gray-700' : 'border-gray-600 bg-gray-700 hover:bg-gray-750'}
              ${isFileUploading ? 'animate-pulse bg-gray-600 border-blue-500' : ''}`
            }
          >
            <input
              type="file"
              multiple
              onChange={handleFileSelect}
              id="file-upload"
              accept=".pdf, .docx"
              className="hidden"
              ref={fileInputRef} 
            />
            <label htmlFor="file-upload" className="flex items-center gap-2 font-semibold text-blue-400 cursor-pointer">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-paperclip"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.49"/></svg>
              {isFileUploading ? 'Uploading files...' : 'Drag & Drop files here or click to browse'}
            </label>
            {/* Display selected file chips */}
            {selectedFiles.length > 0 && (
              <div className="flex flex-wrap justify-center gap-2 mt-2">
                {selectedFiles.map((file, index) => (
                  <span key={file.name + index} className="flex items-center gap-1 bg-blue-700 text-blue-100 text-xs px-3 py-1 rounded-full border border-blue-600 shadow-sm">
                    {file.name}
                    <button onClick={() => handleRemoveFile(index)} className="ml-1 text-blue-300 hover:text-blue-100 rounded-full p-0.5 -mr-1 transition-colors duration-200">
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-x"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Message Input Area */}
        <div className="p-4 border-t border-gray-700 bg-gray-800 flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message..."
            disabled={isFileUploading || isResponding}
            className="flex-1 px-4 py-2 border border-gray-600 bg-gray-700 text-gray-100 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 text-sm placeholder:text-gray-400"
          />
          <button
            onClick={handleSendMessage}
            disabled={isFileUploading || isResponding}
            className="inline-flex items-center justify-center whitespace-nowrap rounded-full text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none h-10 px-4 py-2 bg-blue-600 text-white hover:bg-blue-700 shadow-md transform active:scale-95 duration-150 ease-in-out"
          >
            {isResponding ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-loader-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-send"><path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M15 15 22 2"/></svg>
            )}
            <span className="ml-2">{isResponding ? 'Sending...' : 'Send'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;