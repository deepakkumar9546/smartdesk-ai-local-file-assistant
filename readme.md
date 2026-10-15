# SmartDesk AI – Local File Assistant

A Windows desktop assistant built with Python, Tkinter, and Ollama. It reads text from local PDF and TXT files, answers document questions, summarizes documents, and saves conversations to a local text file.

## Requirements
- Python 3.11+
- Ollama for Windows
- Ollama model `llama3.2`

## Setup (PowerShell)
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ollama pull llama3.2
python app.py
```

If Ollama is already installed and the model downloaded, the `ollama pull` step can be skipped.

## Features
- Tkinter desktop GUI; no browser required
- PDF and TXT document selection
- Document question answering and summarization using the local Ollama API
- Conversation export to a local TXT file
- Background AI requests to keep the UI responsive
- User-friendly errors for unavailable Ollama or failed requests

## Privacy
The application sends the document text in the prompt to the Ollama service at `http://localhost:11434` on the same computer. It does not call a cloud LLM API. Ollama itself should be installed and running locally.

## Limitations
- Scanned/image-only PDFs need OCR; this version extracts embedded PDF text.
- Very long documents are truncated to a 24,000-character prompt limit, and the app warns the model in the prompt.
