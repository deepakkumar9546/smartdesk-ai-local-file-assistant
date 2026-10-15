import os
import threading
import queue
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import requests
from pypdf import PdfReader

APP_NAME = "SmartDesk AI – Local File Assistant"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"
MAX_CONTEXT_CHARS = 24000


class SmartDeskAI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1000x720")
        self.root.minsize(760, 560)

        self.document_path = None
        self.document_text = ""
        self.conversation = []
        self.events = queue.Queue()
        self.busy = False

        self._configure_style()
        self._build_ui()
        self.root.after(100, self._process_events)

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Subheader.TLabel", font=("Segoe UI", 10))
        style.configure("Action.TButton", padding=(10, 7))
        style.configure("Status.TLabel", padding=(8, 4))

    def _build_ui(self):
        # Use grid so the conversation expands while the question box and
        # action buttons always retain their own visible rows.
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="SmartDesk AI", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="Ask questions about local documents — powered by Ollama on your computer.",
            style="Subheader.TLabel",
        ).pack(anchor=tk.W, pady=(3, 0))

        doc_frame = ttk.LabelFrame(outer, text="Document", padding=10)
        doc_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        doc_frame.columnconfigure(0, weight=1)
        self.doc_label = ttk.Label(doc_frame, text="No document selected", wraplength=700)
        self.doc_label.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(
            doc_frame, text="Choose PDF / TXT", style="Action.TButton",
            command=self.choose_document
        ).grid(row=0, column=1, sticky="e")

        chat_frame = ttk.LabelFrame(outer, text="Conversation", padding=8)
        chat_frame.grid(row=2, column=0, sticky="nsew")
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat = tk.Text(
            chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Segoe UI", 10),
            padx=10, pady=10, background="#ffffff", foreground="#202124",
            relief=tk.FLAT
        )
        scrollbar = ttk.Scrollbar(chat_frame, orient=tk.VERTICAL, command=self.chat.yview)
        self.chat.configure(yscrollcommand=scrollbar.set)
        self.chat.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.chat.tag_configure("user", foreground="#155eef", font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("assistant", foreground="#16794b", font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("system", foreground="#666666", font=("Segoe UI", 9, "italic"))
        self.chat.tag_configure("body", foreground="#202124", spacing3=8)

        input_frame = ttk.Frame(outer)
        input_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        input_frame.columnconfigure(0, weight=1)
        self.question = tk.Text(input_frame, height=3, wrap=tk.WORD, font=("Segoe UI", 10))
        self.question.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.question.bind("<Control-Return>", self._ctrl_enter)
        self.ask_button = ttk.Button(
            input_frame, text="Ask", style="Action.TButton", command=self.ask_question
        )
        self.ask_button.grid(row=0, column=1, sticky="s")

        actions = ttk.Frame(outer)
        actions.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.summary_button = ttk.Button(
            actions, text="Summarize document", command=self.summarize_document
        )
        self.summary_button.pack(side=tk.LEFT)
        self.save_button = ttk.Button(
            actions, text="Save conversation", command=self.save_conversation
        )
        self.save_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="Clear chat", command=self.clear_chat).pack(side=tk.LEFT, padx=(8, 0))
        self.status_var = tk.StringVar(value="Ready. Select a PDF or TXT document to begin.")
        ttk.Label(actions, textvariable=self.status_var, style="Status.TLabel").pack(
            side=tk.RIGHT, fill=tk.X, expand=True
        )

        self._append_message(
            "SmartDesk AI",
            "Welcome! Choose a PDF or TXT file, then ask a question or summarize it. "
            "Your document text is sent only to the Ollama service running on this computer.",
            "assistant",
        )

    def _ctrl_enter(self, _event):
        self.ask_question()
        return "break"

    def _append_message(self, speaker, text, kind="body"):
        self.chat.configure(state=tk.NORMAL)
        tag = "user" if kind == "user" else "assistant" if kind == "assistant" else "system"
        self.chat.insert(tk.END, f"{speaker}\n", tag)
        self.chat.insert(tk.END, f"{text}\n\n", "body")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def choose_document(self):
        path = filedialog.askopenfilename(
            title="Select a document",
            filetypes=[("Supported documents", "*.pdf *.txt"), ("PDF files", "*.pdf"), ("Text files", "*.txt")],
        )
        if not path:
            return
        try:
            text = self._extract_text(Path(path))
            if not text.strip():
                raise ValueError(
                    "No readable text was found. If this is a scanned PDF, OCR is needed; "
                    "this version reads text-based PDFs."
                )
            self.document_path = Path(path)
            self.document_text = text
            self.doc_label.configure(text=f"{self.document_path.name}  •  {len(text):,} characters")
            self._append_message(
                "System",
                f"Loaded: {self.document_path.name}\nExtracted {len(text):,} characters.",
                "system",
            )
            self.status_var.set("Document loaded.")
        except Exception as exc:
            messagebox.showerror("Could not read document", str(exc))
            self.status_var.set("Document could not be loaded.")

    @staticmethod
    def _extract_text(path):
        suffix = path.suffix.lower()
        if suffix == ".txt":
            # Try common encodings to support ordinary Windows text files.
            for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
                try:
                    return path.read_text(encoding=encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError("This text file's encoding could not be read.")
        if suffix == ".pdf":
            reader = PdfReader(str(path))
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                pages.append(f"[Page {number}]\n{page.extract_text() or ''}")
            return "\n\n".join(pages)
        raise ValueError("Unsupported file type. Please select a PDF or TXT file.")

    def ask_question(self):
        question = self.question.get("1.0", tk.END).strip()
        if not question:
            messagebox.showinfo("Question required", "Please type a question first.")
            return
        if not self.document_text:
            messagebox.showinfo("Select a document", "Choose a PDF or TXT document before asking questions.")
            return
        self.question.delete("1.0", tk.END)
        self._append_message("You", question, "user")
        self.conversation.append(("You", question))
        prompt = self._build_qa_prompt(question)
        self._run_ai(prompt, "answer")

    def summarize_document(self):
        if not self.document_text:
            messagebox.showinfo("Select a document", "Choose a PDF or TXT document first.")
            return
        prompt = (
            "Summarize the following document clearly. Include the main purpose, key points, "
            "important facts or figures, conclusions, and any action items if present. "
            "Do not invent facts. If the provided text is incomplete, say so.\n\n"
            f"DOCUMENT:\n{self._document_for_prompt()}"
        )
        self._append_message("You", "Please summarize the selected document.", "user")
        self.conversation.append(("You", "Please summarize the selected document."))
        self._run_ai(prompt, "summary")

    def _document_for_prompt(self):
        text = self.document_text
        if len(text) > MAX_CONTEXT_CHARS:
            return (
                text[:MAX_CONTEXT_CHARS]
                + "\n\n[NOTE: The document was longer than the context limit and was truncated. "
                  "The response can only use the text shown above.]"
            )
        return text

    def _build_qa_prompt(self, question):
        return (
            "You are SmartDesk AI, a careful assistant that answers questions about a local document. "
            "Use only the document text below. If the answer is not in the document, clearly say "
            "you could not find it in the provided document. Do not make up facts. Keep the answer "
            "useful and mention page numbers when the text includes them.\n\n"
            f"DOCUMENT:\n{self._document_for_prompt()}\n\n"
            f"USER QUESTION:\n{question}\n\nANSWER:"
        )

    def _run_ai(self, prompt, mode):
        if self.busy:
            messagebox.showinfo("Please wait", "An AI request is already running.")
            return
        self.busy = True
        self._set_busy(True)
        self.status_var.set("Ollama is generating a response…")
        threading.Thread(target=self._ai_worker, args=(prompt, mode), daemon=True).start()

    def _ai_worker(self, prompt, mode):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=(5, 300),
            )
            response.raise_for_status()
            answer = response.json().get("response", "").strip()
            if not answer:
                raise RuntimeError("Ollama returned an empty response.")
            self.events.put(("success", mode, answer))
        except requests.exceptions.ConnectionError:
            self.events.put((
                "error", "Ollama is not reachable.\n\n"
                "Make sure Ollama is installed and running, then try again. "
                "You can test it with: ollama list"
            ))
        except requests.exceptions.Timeout:
            self.events.put(("error", "Ollama took too long to respond. Try again or use a smaller document."))
        except requests.exceptions.HTTPError as exc:
            detail = ""
            try:
                detail = response.text[:500]
            except Exception:
                pass
            self.events.put(("error", f"Ollama returned an HTTP error: {exc}\n{detail}"))
        except Exception as exc:
            self.events.put(("error", f"Could not generate a response: {exc}"))

    def _process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "success":
                    _, mode, answer = event
                    label = "Summary" if mode == "summary" else "SmartDesk AI"
                    self._append_message(label, answer, "assistant")
                    self.conversation.append((label, answer))
                    self.status_var.set("Summary complete." if mode == "summary" else "Answer ready.")
                else:
                    self._append_message("Error", event[1], "system")
                    messagebox.showerror("AI request failed", event[1])
                    self.status_var.set("AI request failed.")
                self.busy = False
                self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _set_busy(self, busy):
        state = tk.DISABLED if busy else tk.NORMAL
        self.ask_button.configure(state=state)
        self.summary_button.configure(state=state)
        self.save_button.configure(state=tk.NORMAL)

    def save_conversation(self):
        if not self.conversation:
            messagebox.showinfo("Nothing to save", "There are no questions or answers to save yet.")
            return
        default_name = f"SmartDesk_conversation_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path = filedialog.asksaveasfilename(
            title="Save conversation",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Text files", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(f"{APP_NAME}\n")
                file.write(f"Saved: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                if self.document_path:
                    file.write(f"Document: {self.document_path}\n")
                file.write("=" * 72 + "\n\n")
                for speaker, content in self.conversation:
                    file.write(f"{speaker}:\n{content}\n\n")
            messagebox.showinfo("Conversation saved", f"Saved conversation to:\n{path}")
            self.status_var.set("Conversation saved.")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save the conversation:\n{exc}")

    def clear_chat(self):
        if self.busy:
            messagebox.showinfo("Please wait", "Wait for the current AI request to finish before clearing chat.")
            return
        if self.conversation and not messagebox.askyesno(
            "Clear conversation", "Clear the conversation from this window? Save it first if you need a copy."
        ):
            return
        self.conversation.clear()
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
        self._append_message("SmartDesk AI", "Chat cleared. Your selected document is still loaded.", "assistant")
        self.status_var.set("Chat cleared.")


def main():
    root = tk.Tk()
    SmartDeskAI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
