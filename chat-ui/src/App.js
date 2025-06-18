import React, { useState, useEffect, useRef } from 'react';
import './App.css'; 
function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFileRefs, setUploadedFileRefs] = useState([]); 
  const [isFileUploading, setIsFileUploading] = useState(false);
  const [isResponding, setIsResponding] = useState(false);
  const [isInputFocused, setIsInputFocused] = useState(false); 
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'; 
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  }, [input]);
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  const addFiles = async (files) => {
    const allowedFiles = files.filter(file =>
      file.type === 'application/pdf' ||
      file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    );
    if (allowedFiles.length > 0) {
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
    filesToUpload.forEach((file) => {
      formData.append("files", file);
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
      setSelectedFiles([]);
      setUploadedFileRefs([]);
    } finally {
      setIsFileUploading(false);
    }
  };
  const handleFileSelect = (event) => {
    addFiles(Array.from(event.target.files));
  };
  const handleRemoveFile = (indexToRemove) => {
      setSelectedFiles(prevSelectedFiles => {
          const fileToRemove = prevSelectedFiles[indexToRemove];
          const newSelectedFiles = prevSelectedFiles.filter((_, index) => index !== indexToRemove);
          setUploadedFileRefs(prevUploadedRefs => {
              const refIdToRemove = prevUploadedRefs.find(ref => ref.name === fileToRemove.name)?.id;
              if (refIdToRemove) {
                  return prevUploadedRefs.filter(ref => ref.id !== refIdToRemove);
              } else {
                  const newRefs = [];
                  let removedOne = false;
                  for (const ref of prevUploadedRefs) {
                      if (!removedOne && ref.name === fileToRemove.name) {
                          removedOne = true;
                      } else {
                          newRefs.push(ref);
                      }
                  }
                  return newRefs;
              }
          });
          return newSelectedFiles;
      });
  };
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
    console.log("DEBUG: Before attachment logic:");
    console.log("  uploadedFileRefs.length:", uploadedFileRefs.length);
    console.log("  selectedFiles:", selectedFiles.map(f => f.name));
    if (uploadedFileRefs.length > 0) {
      const fileNames = selectedFiles.map(f => f.name).join(', ');
      displayMessageContent += (userMessageText ? "\n\n" : "") + `[Files attached: ${fileNames}]`;
    }
    const newUserMessage = { sender: 'user', text: displayMessageContent };
    const updatedMessagesAfterUser = [...messages, newUserMessage];
    setMessages(updatedMessagesAfterUser);
    setInput('');
    setSelectedFiles([]); 
    const payload = {
      conversation: [
        { role: 'system', content: 'You are a helpful and friendly AI assistant. You answer questions concisely and professionally.' },
        ...updatedMessagesAfterUser.map(msg => ({ role: msg.sender === 'user' ? 'user' : 'assistant', content: msg.text }))
      ]
    };
    if (uploadedFileRefs.length > 0) {
      payload.fileRefs = uploadedFileRefs;
    }
    let currentAssistantMessage = { sender: 'assistant', text: '' };
    setMessages(prevMessages => [...prevMessages, currentAssistantMessage]);
    try {
      const response = await fetch('http://localhost:7071/api/chat', {
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
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = JSON.parse(line.substring(6));
              if (eventData.token) {
                accumulatedText += eventData.token;
                setMessages(prevMessages => {
                  const newMessages = [...prevMessages];
                  newMessages[newMessages.length - 1] = { ...newMessages[newMessages.length - 1], text: accumulatedText };
                  return newMessages;
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
    } catch (error) {
      setMessages(prevMessages => {
        const newMessages = [...prevMessages];
        newMessages[newMessages.length - 1] = { ...newMessages[newMessages.length - 1], text: `Oops! Something went wrong: ${error.message}` };
        return newMessages;
      });
    } finally {
      setIsResponding(false); 
    }
  };
  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) { 
      handleSendMessage();
      event.preventDefault();
    }
  };
  const handlePlusButtonClick = () => {
    fileInputRef.current.click(); 
  };
  return (
    <div className="App"> {/* Main container, handled by App.css for full screen */}
      <div className="chat-container"> {/* Main chat window */}
        {/* Messages Display Area */}
        <div className="messages-display scrollbar-thumb-rounded scrollbar-track-rounded scrollbar-thumb-gray-600 scrollbar-track-gray-800">
          {messages.map((msg, index) => (
            <div key={index} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`message ${msg.sender === 'user' ? 'user' : 'assistant'}`}
              >
                {msg.text}
              </div>
            </div>
          ))}
          {/* "Thinking..." indicator for assistant */}
          {isResponding && messages[messages.length - 1]?.sender !== 'assistant' && (
            <div className="flex justify-start">
              <div className="message loading-dots">
                <span className="dot-animation"></span>
                <span className="dot-animation"></span>
                <span className="dot-animation"></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} /> {/* Scroll to bottom reference */}
        </div>
        {/* Input Area Container */}
        <div
          className={`input-area-container ${isDragging ? 'border-blue-500 bg-gray-700' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* File Upload Tray (if files selected) */}
          {selectedFiles.length > 0 && (
            <div className="file-upload-tray">
              {selectedFiles.map((file, index) => (
                <span key={file.name + index} className="file-chip">
                  {file.name}
                  <button onClick={() => handleRemoveFile(index)}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-x"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                  </button>
                </span>
              ))}
            </div>
          )}
          {/* Main Input Wrapper */}
          <div className={`input-wrapper ${isInputFocused || input.length > 0 || selectedFiles.length > 0 ? 'active' : ''}`}>
            {/* Hidden file input */}
            <input
              type="file"
              multiple
              onChange={handleFileSelect}
              id="file-upload"
              accept=".pdf, .docx"
              className="hidden"
              ref={fileInputRef}
            />
            {/* Plus/Attachment Button */}
            <button
              onClick={handlePlusButtonClick}
              disabled={isFileUploading || isResponding}
              className="input-action-button"
              title="Attach files"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-plus-circle"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="M12 8v8"/></svg>
            </button>
            {/* Main Textarea Input */}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              onFocus={() => setIsInputFocused(true)}
              onBlur={() => setIsInputFocused(false)}
              placeholder="Message Azure OpenAI..."
              disabled={isFileUploading || isResponding}
              className="message-input-field"
              rows={1} 
            />
            {/* Send Button */}
            <button
              onClick={handleSendMessage}
              disabled={isFileUploading || isResponding || (input.trim() === '' && uploadedFileRefs.length === 0)}
              className="input-action-button send-button"
              title="Send message"
            >
              {isResponding ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-loader-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-arrow-up"><path d="m5 12 7-7 7 7"/><path d="M12 19V5"/></svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
export default App;