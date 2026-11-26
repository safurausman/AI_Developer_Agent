# DevAgent – AI Developer Assistant

DevAgent is an AI-powered developer assistant built with Python, Google Gemini API, and Gradio. It demonstrates how AI agents can interact with tools, manage tasks, maintain persistent memory, and perform useful operations through natural language.

## Features

- **AI-powered conversation:** Interact with DevAgent using Google Gemini.
- **Tool calling:** Execute predefined tools through AI-driven function calling.
- **Task management:** Create, list, and manage tasks.
- **Task completion confirmation:** Human approval before completing tasks.
- **Persistent memory:** Save and recall information across conversations.
- **Calculator:** Perform mathematical calculations.
- **Date and time:** Retrieve current date and time information.
- **SQLite database:** Persist tasks and memories locally.
- **Error handling:** Handle API errors gracefully.

## Technology Stack

- Python
- Google Gemini API
- Gradio
- SQLite
- Google GenAI SDK

## Project Structure

```text
AI_Developer_Agent/
│
├── app.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Getting Started

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd AI_Developer_Agent
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the Gemini API key

Set your API key as an environment variable.

Windows Command Prompt:

```cmd
set GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

Linux/macOS:

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

Never commit your actual API key to GitHub.

### 5. Run the application

```bash
python app.py
```

Open the local Gradio URL displayed in your terminal.

## Database

DevAgent uses SQLite to store tasks and persistent memories. The database is created locally when the application runs.

## Learning Objectives

This project demonstrates practical concepts from AI Agents, Tools and Automation, including:

- AI agent implementation
- LLM integration
- Function and tool calling
- Persistent memory
- Human-in-the-loop workflows
- Database integration
- Error handling

## Security

- API credentials are loaded through environment variables.
- Never publish API keys or other secrets.
- Local databases and virtual environments should not be committed.

## Acknowledgement

Developed as part of Codomax Solutions – Module 05: AI Agents, Tools & Automation.
