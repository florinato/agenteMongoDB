const userInput = document.getElementById('user-input');
const modelOutput = document.getElementById('model-output');
const sendButton = document.getElementById('send-button');
const consoleLog = document.getElementById('console-log');

let sessionId = null;
const API_BASE_URL = 'http://127.0.0.1:8000'; // Assuming default FastAPI port

// --- Helper Function to Add Log Entries ---
function addLogEntry(message, className = 'log-status') {
    const entry = document.createElement('div');
    entry.classList.add('log-entry', className);
    entry.textContent = message;
    consoleLog.appendChild(entry);
    // Scroll to the bottom
    consoleLog.scrollTop = consoleLog.scrollHeight;
}

// --- Auto-Resize Textarea Function ---
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto'; // Reset height to recalculate
    textarea.style.height = textarea.scrollHeight + 'px'; // Set height based on content
}

// --- Start Conversation Function ---
async function startConversation() {
    addLogEntry('Starting new conversation...');
    try {
        const response = await fetch(`${API_BASE_URL}/start_conversation`, {
            method: 'POST',
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`API Error (${response.status}): ${errorData.detail || 'Failed to start session'}`);
        }
        const data = await response.json();
        sessionId = data.session_id;
        addLogEntry(`Session started: ${sessionId}`, 'log-status');
        return true;
    } catch (error) {
        console.error("Error starting conversation:", error);
        addLogEntry(`Error starting session: ${error.message}`, 'log-error');
        modelOutput.value = `Failed to start session: ${error.message}`;
        return false;
    }
}

// --- Send Confirmed Command Function ---
async function sendConfirmedCommand(command) {
    if (!sessionId) {
        addLogEntry('Error: Session ID is missing.', 'log-error');
        sendButton.disabled = false; // Re-enable button
        return;
    }

    // Keep the button disabled while processing the confirmed command
    sendButton.disabled = true;
    addLogEntry(`Sending confirmed command: ${command}`, 'log-status');

    try {
        const response = await fetch(`${API_BASE_URL}/chat/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            // Send the confirmed command, null for user_query
            body: JSON.stringify({ user_query: null, confirmed_command: command }),
        });

        const data = await response.json(); // Always try to parse JSON

        if (!response.ok) {
             throw new Error(`API Error (${response.status}): ${data.detail || 'Unknown API error during confirmation'}`);
        }

        // Process the response AFTER confirmation (could be completed or error)
        if (data.status === 'completed') {
            modelOutput.value = data.response;
            addLogEntry(`Agent (after confirmation): ${data.response}`, 'log-agent');
        } else if (data.status === 'error') {
             modelOutput.value = `Error after confirmation: ${data.response}`;
             addLogEntry(`Error after confirmation: ${data.response}`, 'log-error');
        }
        // It's unlikely but possible to get another confirmation request here
        else if (data.status === 'confirmation_required') {
             addLogEntry(`Agent: Another confirmation required for: ${data.command_to_confirm}`, 'log-agent-confirm'); // Added new class
             const userConfirmedAgain = window.confirm(`Another authorization required for command:\n\n${data.command_to_confirm}\n\nExecute anyway?`);
             if (userConfirmedAgain) {
                 await sendConfirmedCommand(data.command_to_confirm); // Recursive call
                 return; // Exit here as the recursive call will handle re-enabling the button
             } else {
                 addLogEntry('Authorization denied by user.', 'log-status');
                 modelOutput.value = 'Action cancelled by user.';
             }
        }
        else {
             modelOutput.value = `Unexpected status after confirmation: ${data.status}\nResponse: ${data.response || 'N/A'}`;
             addLogEntry(`Unexpected Status after confirmation: ${data.status}`, 'log-error');
        }
         autoResizeTextarea(modelOutput);

    } catch (error) {
        console.error("Error sending confirmed command:", error);
        const errorMessage = `Network or API Error during confirmation: ${error.message}`;
        modelOutput.value = errorMessage;
        addLogEntry(errorMessage, 'log-error');
        autoResizeTextarea(modelOutput);
    } finally {
        // Re-enable the send button ONLY after the confirmed command flow is fully resolved
        sendButton.disabled = false;
    }
}


// --- Send Chat Message Function ---
async function sendMessage() {
    const query = userInput.value.trim();
    if (!query) return;

    sendButton.disabled = true;
    modelOutput.value = ''; // Clear previous output
    addLogEntry(`You: ${query}`, 'log-user');

    // Start session if not already started
    if (!sessionId) {
        const success = await startConversation();
        if (!success) {
            sendButton.disabled = false;
            return; // Stop if session start failed
        }
    }

    try {
        const response = await fetch(`${API_BASE_URL}/chat/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            // Send null for confirmed_command initially
            body: JSON.stringify({ user_query: query, confirmed_command: null }),
        });

        const data = await response.json(); // Always try to parse JSON

        if (!response.ok) {
             // Handle HTTP errors (like 404, 409, 500) using detail from FastAPI
             throw new Error(`API Error (${response.status}): ${data.detail || 'Unknown API error'}`);
        }

        // Process successful response based on status
        if (data.status === 'confirmation_required') {
            const commandToConfirm = data.command_to_confirm;
            addLogEntry(`Agent: Authorization required for command: ${commandToConfirm}`, 'log-agent-confirm'); // Added new class

            // Use window.confirm for the prompt
            const userConfirmed = window.confirm(`Authorization required for command:\n\n${commandToConfirm}\n\nExecute anyway?`);

            if (userConfirmed) {
                addLogEntry('Authorization granted by user. Sending confirmation...', 'log-status');
                // Call the new function to handle sending the confirmed command
                // IMPORTANT: await this call, but don't re-enable the button here.
                // sendConfirmedCommand will handle re-enabling it in its finally block.
                await sendConfirmedCommand(commandToConfirm);
            } else {
                addLogEntry('Authorization denied by user.', 'log-status');
                modelOutput.value = 'Action cancelled by user.';
                autoResizeTextarea(modelOutput);
                sendButton.disabled = false; // Re-enable button if cancelled here
            }
        } else if (data.status === 'completed') {
            modelOutput.value = data.response;
            addLogEntry(`Agent: ${data.response}`, 'log-agent');
            autoResizeTextarea(modelOutput);
            sendButton.disabled = false; // Re-enable on completion
        } else if (data.status === 'error') {
             modelOutput.value = `Error: ${data.response}`;
             addLogEntry(`Error: ${data.response}`, 'log-error');
             autoResizeTextarea(modelOutput);
             sendButton.disabled = false; // Re-enable on error
        }
        // Remove the old 'cancelled' status check if it existed
        else {
             modelOutput.value = `Unexpected status: ${data.status}\nResponse: ${data.response || 'N/A'}`;
             addLogEntry(`Unexpected Status: ${data.status}`, 'log-error');
             autoResizeTextarea(modelOutput);
             sendButton.disabled = false; // Re-enable on unexpected status
        }

    } catch (error) {
        console.error("Error sending message:", error);
        const errorMessage = `Network or API Error: ${error.message}`;
        modelOutput.value = errorMessage;
        addLogEntry(errorMessage, 'log-error');
        autoResizeTextarea(modelOutput); // Resize output textarea after setting error
        sendButton.disabled = false; // Re-enable button on catch
    } finally {
        // Clear input field ONLY if not waiting for confirmation
        // The button re-enabling is handled within the specific status blocks or in sendConfirmedCommand's finally block
        if (document.getElementById('send-button').disabled === false) { // Check if button is already re-enabled
             userInput.value = ''; // Clear input field
             autoResizeTextarea(userInput); // Reset user input height
        }
    }
}

// --- Event Listener ---
sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (event) => {
    // Allow sending with Enter key (optional: Shift+Enter for newline)
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault(); // Prevent default newline behavior
        sendMessage();
    }
});

// Add input listener for user textarea resizing
userInput.addEventListener('input', () => autoResizeTextarea(userInput));

// Initial log message
addLogEntry('UI Initialized. Enter your query and click Send.');

// Initial resize for textareas based on placeholder/content
autoResizeTextarea(userInput);
autoResizeTextarea(modelOutput);
