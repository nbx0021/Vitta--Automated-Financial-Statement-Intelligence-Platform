const chatFab = document.getElementById('chatFab');
const chatSidebar = document.getElementById('chatSidebar');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSend = document.getElementById('chatSend');

function toggleChat() {
  chatSidebar.classList.toggle('open');
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  // Add user message
  chatInput.value = '';
  chatInput.style.height = '';
  appendMessage(text, 'user-msg');
  
  // Add an empty AI message block to append to
  const aiMsgDiv = appendMessage('', 'ai-msg');
  aiMsgDiv.innerHTML = '<div class="typing-indicator">Thinking<span>.</span><span>.</span><span>.</span></div>';
  
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        query: text, 
        ticker: window.location.pathname.split('/').pop().replace('.NS', '') // e.g. "TCS"
      })
    });
    
    if (!response.ok) {
      aiMsgDiv.innerHTML = 'Error: Could not connect to AI.';
      return;
    }
    
    // Process SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let aiContent = '';
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'THOUGHT') {
              aiMsgDiv.innerHTML = `<div class="thought-bubble">${data.content}</div>`;
            } else if (data.type === 'FINAL_RESPONSE') {
              if (!aiContent) {
                aiMsgDiv.innerHTML = ''; // clear thought/typing
              }
              aiContent += data.content;
              aiMsgDiv.innerHTML = renderMarkdown(aiContent);
            } else if (data.type === 'ERROR') {
              aiMsgDiv.innerHTML = `<div class="error-msg">${data.content}</div>`;
            }
          } catch(e) {}
        }
      }
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  } catch (err) {
    aiMsgDiv.innerHTML = 'Network error. Please try again.';
  }
}

function appendMessage(text, className) {
  const div = document.createElement('div');
  div.className = `message ${className}`;
  div.innerText = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

// Basic markdown-like renderer since we want it lightweight
function renderMarkdown(text) {
  let html = text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br/>');
  return html;
}

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
