import streamlit as st
import sqlite3
import hashlib
import smtplib
import random
import requests
import json
import re
import os
import io
import time
import csv
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# ADVANCED STRUCTURAL VISUAL LAYER (CUSTOM UI & FONTS)
# ==========================================
st.set_page_config(page_title="Audit Assistant Engine", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0d1117 !important;
        color: #c9d1d9 !important;
        font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif !important;
    }
    [data-testid="stSidebar"] {
        background-color: #161b22 !important;
        border-right: 1px solid #30363d !important;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] {
        background-color: #161b22 !important; border: 1px solid #30363d !important;
        border-radius: 6px 6px 0px 0px !important; padding: 10px 20px !important;
        color: #8b949e !important; font-weight: 600 !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #21262d !important; color: #58a6ff !important;
        border-bottom: 2px solid #58a6ff !important;
    }
    .stTextInput input, .stFileUploader {
        background-color: #161b22 !important; border: 1px solid #30363d !important;
        color: #f0f6fc !important; border-radius: 6px !important;
    }
    .stTextInput input:focus {
        border-color: #58a6ff !important;
        box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15) !important;
    }
    .stButton>button {
        background: linear-gradient(135deg, #1f6feb 0%, #0d44a5 100%) !important;
        color: #ffffff !important; border: none !important; padding: 8px 18px !important;
        border-radius: 6px !important; font-weight: 600 !important;
    }
    .stButton>button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(31, 111, 235, 0.3) !important;
    }
    @keyframes cardSlideIn {
        0% { opacity: 0; transform: translateY(10px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    .data-not-found-card {
        padding: 16px; background: linear-gradient(90deg, rgba(248, 81, 73, 0.1) 0%, rgba(0, 0, 0, 0) 100%);
        border-left: 4px solid #f85149; border-radius: 6px; color: #ff7b72;
        font-weight: 500; margin: 12px 0px; animation: cardSlideIn 0.3s ease;
    }
    .system-success-card {
        padding: 16px; background: linear-gradient(90deg, rgba(56, 139, 60, 0.1) 0%, rgba(0, 0, 0, 0) 100%);
        border-left: 4px solid #388b3c; border-radius: 6px; color: #56d364;
        font-weight: 500; margin: 12px 0px; animation: cardSlideIn 0.3s ease;
    }
    /* Chat UI enhancements */
    .stChatMessage {
        background-color: #161b22 !important;
        border: 1px solid #30363d !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# CONFIG & SECRETS 
# ==========================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.getenv("SENDER_APP_PASSWORD")

CSV_STORAGE_DIR = "extracted_csvs"
os.makedirs(CSV_STORAGE_DIR, exist_ok=True)

# ==========================================
# EMAIL CONFIGURATION
# ==========================================
def send_email(receiver_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send email. Error: {e}")
        return False

# ==========================================
# PERMANENT STORAGE FUNCTIONS (JSON)
# ==========================================
USER_DATA_FILE = "users_data.json"

def load_users():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

def save_users(users_dict):
    with open(USER_DATA_FILE, "w") as file:
        json.dump(users_dict, file, indent=4)

# ==========================================
# DATABASE MIGRATION ENGINE (SQLite Layer)
# ==========================================
def init_db():
    conn = sqlite3.connect("audit_assistant.db")
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS documents 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, doc_name TEXT, 
                  upload_time TEXT, file_hash TEXT, extracted_data TEXT, raw_text TEXT, csv_paths TEXT)''')
    
    c.execute("PRAGMA table_info(documents)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    if "file_hash" not in existing_columns: c.execute("ALTER TABLE documents ADD COLUMN file_hash TEXT")
    if "extracted_data" not in existing_columns: c.execute("ALTER TABLE documents ADD COLUMN extracted_data TEXT")
    if "raw_text" not in existing_columns: c.execute("ALTER TABLE documents ADD COLUMN raw_text TEXT")
    if "csv_paths" not in existing_columns: c.execute("ALTER TABLE documents ADD COLUMN csv_paths TEXT")
        
    conn.commit()
    conn.close()

init_db()

def get_file_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()

# ==========================================
# PDF EXTRACTION & CSV TABLE EXPORT
# ==========================================
def extract_text_from_pdf(file_bytes):
    extracted_text = ""
    extraction_method = ""
    
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                extracted_text += f"\n--- Page {page_num + 1} ---\n{text}"
        doc.close()
        if extracted_text.strip():
            return extracted_text.strip(), "PyMuPDF"
    except: pass
    
    try:
        from pypdf import PdfReader
        pdf_reader = PdfReader(io.BytesIO(file_bytes))
        for page_num, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            if text and text.strip():
                extracted_text += f"\n--- Page {page_num + 1} ---\n{text}"
        if extracted_text.strip():
            return extracted_text.strip(), "pypdf"
    except: pass
    
    return "", "No extraction method available"

def extract_tables_from_pdf(file_bytes, doc_name, username):
    csv_paths = []
    tables_found = 0
    
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for table_idx, table in enumerate(tables):
                    if table and len(table) > 0:
                        tables_found += 1
                        cleaned_table = []
                        for row in table:
                            if row:
                                cleaned_row = [str(cell).strip().replace('\n', ' ') if cell else "" for cell in row]
                                cleaned_table.append(cleaned_row)
                        
                        if len(cleaned_table) > 1:
                            csv_filename = f"{username}_{doc_name.replace('.pdf', '')}_p{page_num+1}_t{table_idx+1}.csv"
                            csv_path = os.path.join(CSV_STORAGE_DIR, csv_filename)
                            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                                writer = csv.writer(csvfile)
                                writer.writerows(cleaned_table)
                            csv_paths.append(csv_path)
        return csv_paths, tables_found
    except Exception as e:
        return [], 0

def extract_text_from_txt(file_bytes):
    try: return file_bytes.decode("utf-8"), "UTF-8 Decode"
    except: return file_bytes.decode("latin-1", errors="ignore"), "Latin-1 Decode"

def clean_extracted_text(text):
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def convert_csv_to_context(csv_path):
    try:
        df = pd.read_csv(csv_path)
        context = f"Table from {os.path.basename(csv_path)}:\nColumns: {', '.join(df.columns)}\nData:\n"
        for idx, row in df.head(30).iterrows():
            context += " | ".join([f"{col}: {row[col]}" for col in df.columns]) + "\n"
        if len(df) > 30: context += f"... ({len(df) - 30} more rows)\n"
        return context
    except: return ""

# ==========================================
# COMPUTATIONAL COGNITION AGENTS (GROQ)
# ==========================================
def analyze_document_with_ai(text_content, doc_name):
    max_chunk_size = 6000
    chunks = []
    
    if len(text_content) > max_chunk_size:
        paragraphs = text_content.split('\n\n')
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 < max_chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk: chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        if current_chunk: chunks.append(current_chunk.strip())
    else:
        chunks = [text_content.strip()]
    
    if len(chunks) > 5: chunks = chunks[:5]
    
    all_analyses = []
    for i, chunk in enumerate(chunks):
        prompt = f"""You are an expert computational audit assistant. Analyze document "{doc_name}" (Part {i+1}/{len(chunks)}).
Extract FINANCIAL DATA (Revenue, Expenses, Assets, Liabilities), DATES, KEY METRICS, and TRANSACTIONS.
Format with clear sections and bullet points.

Document Content:
{chunk}"""
        
        try:
            response = requests.post(
                url="https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                data=json.dumps({
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3, "max_tokens": 1500
                })
            )
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                all_analyses.append(result['choices'][0]['message']['content'])
            else:
                all_analyses.append(f"Part {i+1} failed.")
            if i < len(chunks) - 1: time.sleep(5)
        except: pass
    
    return "\n\n".join(all_analyses) if all_analyses else "Analysis failed."

def chat_with_ai(chat_history, knowledge_base, user_question):
    """
    Interactive Chatbot AI: Classifies questions, asks for clarification, or answers precisely.
    """
    # Format recent history (last 6 messages to save tokens)
    history_text = ""
    for msg in chat_history[-6:]:
        role = "User" if msg['role'] == 'user' else "Auditor"
        history_text += f"{role}: {msg['content']}\n"
    
    prompt = f"""You are an expert, interactive computational Auditor. You have access to the user's uploaded financial documents.

Your goal is to provide absolute precision. However, if the user's question is vague, ambiguous, or lacks specific parameters (like timeframes, specific entities, or categories), DO NOT guess. Instead, ASK clarifying questions to narrow down exactly what they need.

Examples of when to ask for clarification:
- User: "give me revenue" -> You: "I can help with that. Are you looking for total annual revenue, a quarterly breakdown, or revenue for a specific product/service line?"
- User: "compare expenses" -> You: "Which two periods would you like to compare (e.g., Q1 vs Q2, or 2020 vs 2021)?"
- User: "liabilities" -> You: "Are you referring to short-term (current) liabilities or long-term debt obligations?"

Once you have enough context, or if the question is already specific, provide a detailed, math-based analytical response using ONLY the provided Knowledge Base. Cite specific documents or tables when referencing information.

KNOWLEDGE BASE (Extracted from user's documents):
{knowledge_base}

CONVERSATION HISTORY:
{history_text}

USER'S LATEST MESSAGE: {user_question}
"""
    
    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4, "max_tokens": 1500
            })
        )
        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            return "I'm currently experiencing a processing delay. Could you rephrase your question?"
    except Exception as e:
        return "I encountered a network issue. Please try again in a moment."

# ==========================================
# Initialize Session State
# ==========================================
if 'users' not in st.session_state: st.session_state.users = load_users()
if 'page' not in st.session_state: st.session_state.page = 'login'
if 'otp' not in st.session_state: st.session_state.otp = None
if 'otp_email' not in st.session_state: st.session_state.otp_email = None
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'chat_history' not in st.session_state: st.session_state.chat_history = []

def go_to(page):
    st.session_state.page = page
    st.rerun()

# ==========================================
# AUTHENTICATION PAGES
# ==========================================
def signup_page():
    st.markdown("<h1 style='color: #f0f6fc;'>AUDIT ASSISTANT ENGINE</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #c9d1d9;'>Create New Account</h3>", unsafe_allow_html=True)
    
    with st.form("signup_form"):
        name = st.text_input("Full Name")
        username = st.text_input("Username")
        email = st.text_input("Gmail / Email Address")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        
        if st.form_submit_button("Sign Up"):
            if not all([name, username, email, password, confirm_password]):
                st.error("All fields are required.")
            elif not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$", password):
                st.error("Password must be 8+ chars, with 1 uppercase, 1 lowercase, 1 number, 1 special char.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            elif email in st.session_state.users:
                st.error("Email already exists.")
            else:
                st.session_state.users[email] = {"name": name, "username": username, "password": password}
                save_users(st.session_state.users)
                st.success("Account created! Redirecting...")
                go_to('login')
    if st.button("Already have an account? Login"): go_to('login')

def login_page():
    st.markdown("<h1 style='color: #f0f6fc;'>AUDIT ASSISTANT ENGINE</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #c9d1d9;'>Account Access Terminal</h3>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        email = st.text_input("Email Address")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if email in st.session_state.users and st.session_state.users[email]["password"] == password:
                st.session_state.current_user = email
                go_to('dashboard')
            else:
                st.error("Invalid credentials.")
    if st.button("Forgot Password?"): go_to('forgot_password')
    if st.button("Don't have an account? Sign Up"): go_to('signup')

def forgot_password_page():
    st.markdown("<h1 style='color: #f0f6fc;'>Credential Recovery</h1>", unsafe_allow_html=True)
    email = st.text_input("Enter your registered Email")
    
    if st.button("Send OTP"):
        if email in st.session_state.users:
            otp = str(random.randint(100000, 999999))
            st.session_state.otp = otp
            st.session_state.otp_email = email
            if send_email(email, "Your OTP", f"Your OTP is: {otp}"):
                st.success("OTP sent to your email!")
        else: st.error("Email not found.")
    
    if st.session_state.otp and st.session_state.otp_email == email:
        entered_otp = st.text_input("Enter OTP")
        if st.button("Verify OTP"):
            if entered_otp == st.session_state.otp:
                pwd = st.session_state.users[email]["password"]
                send_email(email, "Your Password", f"Your password is: {pwd}")
                st.success("Password sent to email!")
                st.session_state.otp = None
                go_to('login')
            else: st.error("Invalid OTP.")
    if st.button("Back to Login"): go_to('login')

# ==========================================
# MAIN DASHBOARD (After Login)
# ==========================================
def dashboard_page():
    user_email = st.session_state.current_user
    user_name = st.session_state.users[user_email]['name']
    
    st.sidebar.markdown(f"<h3 style='color: #58a6ff;'>{user_name}</h3>", unsafe_allow_html=True)
    if st.sidebar.button("Logout Session"):
        st.session_state.current_user = None
        st.session_state.chat_history = []
        go_to('login')
    
    menu = ["Upload Document", "Uploaded Documents & History", "View Extracted Tables", "Interactive AI Auditor (Chat)"]
    choice = st.sidebar.selectbox("Infrastructure Action", menu)
    
    conn = sqlite3.connect("audit_assistant.db")
    c = conn.cursor()
    
    # ==========================================
    # UPLOAD DOCUMENT
    # ==========================================
    if choice == "Upload Document":
        st.markdown("<h2 style='color: #f0f6fc;'>Upload Document Pipeline</h2>", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Upload PDF or TXT", type=["pdf", "txt"])
        
        if uploaded_file:
            file_bytes = uploaded_file.read()
            file_hash = get_file_hash(file_bytes)
            
            c.execute("SELECT * FROM documents WHERE username=? AND file_hash=?", (user_email, file_hash))
            if c.fetchone():
                st.error("This document already exists in your archive.")
            else:
                with st.spinner("Extracting text and tables..."):
                    if uploaded_file.name.endswith('.pdf'):
                        extracted_text, method = extract_text_from_pdf(file_bytes)
                        csv_paths, tables_found = extract_tables_from_pdf(file_bytes, uploaded_file.name, user_email)
                    else:
                        extracted_text, method = extract_text_from_txt(file_bytes)
                        csv_paths, tables_found = [], 0
                
                cleaned_text = clean_extracted_text(extracted_text)
                st.success(f"Extracted using {method}. Tables found: {tables_found}")
                
                with st.spinner("🤖 AI Analyzing document..."):
                    processed_analysis = analyze_document_with_ai(cleaned_text, uploaded_file.name)
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    c.execute("INSERT INTO documents (username, doc_name, upload_time, file_hash, extracted_data, raw_text, csv_paths) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (user_email, uploaded_file.name, current_time, file_hash, processed_analysis, cleaned_text, json.dumps(csv_paths)))
                    conn.commit()
                    
                    st.success("Document mapped and stored successfully!")
                    with st.expander("🤖 AI Analysis"): st.markdown(processed_analysis)

    # ==========================================
    # HISTORY
    # ==========================================
    elif choice == "Uploaded Documents & History":
        st.markdown("<h2 style='color: #f0f6fc;'>Document Archive</h2>", unsafe_allow_html=True)
        c.execute("SELECT id, doc_name, upload_time, csv_paths FROM documents WHERE username=? ORDER BY upload_time DESC", (user_email,))
        documents = c.fetchall()
        
        for doc_id, doc_name, upload_time, csv_paths_json in documents:
            csv_count = len(json.loads(csv_paths_json)) if csv_paths_json else 0
            with st.expander(f"📄 {doc_name} ({upload_time}) {'📊' if csv_count > 0 else ''}"):
                c.execute("SELECT extracted_data FROM documents WHERE id=?", (doc_id,))
                st.markdown(c.fetchone()[0])
                if st.button("🗑️ Delete", key=f"del_{doc_id}"):
                    if csv_paths_json:
                        for p in json.loads(csv_paths_json):
                            if os.path.exists(p): os.remove(p)
                    c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
                    conn.commit()
                    st.rerun()

    # ==========================================
    # VIEW CSVs
    # ==========================================
    elif choice == "View Extracted Tables":
        st.markdown("<h2 style='color: #f0f6fc;'>Extracted Tables (CSV)</h2>", unsafe_allow_html=True)
        csvs = [f for f in os.listdir(CSV_STORAGE_DIR) if f.startswith(user_email)]
        if not csvs:
            st.info("No CSV tables extracted yet.")
        else:
            for f in csvs:
                with st.expander(f"📊 {f}"):
                    df = pd.read_csv(os.path.join(CSV_STORAGE_DIR, f))
                    st.dataframe(df, use_container_width=True)

    # ==========================================
    # 🌟 INTERACTIVE AI CHATBOT 🌟
    # ==========================================
    elif choice == "Interactive AI Auditor (Chat)":
        st.markdown("<h2 style='color: #f0f6fc;'>Interactive AI Auditor</h2>", unsafe_allow_html=True)
        
        # 1. Context Configuration Bar
        with st.expander("⚙️ Configure Chat Context (Select Documents & Data Sources)", expanded=False):
            c.execute("SELECT doc_name, extracted_data, raw_text, csv_paths FROM documents WHERE username=?", (user_email,))
            all_docs = c.fetchall()
            
            if not all_docs:
                st.warning("Please upload documents first to start chatting.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    doc_names = [doc[0] for doc in all_docs]
                    selected_docs = st.multiselect("Select documents to reference:", doc_names, default=doc_names)
                with col2:
                    data_source = st.radio("Data Source:", ["AI Analysis (Structured)", "CSV Tables (Financials)", "Combined (Best)"], index=2)
                
                if st.button("🔄 Update Chat Context"):
                    # Build Knowledge Base
                    kb = ""
                    for doc_name, ext_data, raw_text, csv_paths_json in all_docs:
                        if doc_name in selected_docs:
                            kb += f"\n--- DOCUMENT: {doc_name} ---\n"
                            if "AI Analysis" in data_source or "Combined" in data_source:
                                kb += ext_data + "\n"
                            if "CSV Tables" in data_source or "Combined" in data_source:
                                if csv_paths_json:
                                    for path in json.loads(csv_paths_json):
                                        if os.path.exists(path):
                                            kb += convert_csv_to_context(path) + "\n"
                    
                    # Truncate if too large to respect TPM
                    if len(kb) > 12000:
                        kb = kb[:12000] + "\n[... Context Truncated for API Limits ...]"
                    
                    st.session_state.chat_knowledge_base = kb
                    st.success("Context loaded into chatbot memory!")
                    st.rerun()

        # 2. Chat Interface
        if 'chat_knowledge_base' not in st.session_state or not st.session_state.chat_knowledge_base:
            st.info("👆 Please open 'Configure Chat Context' above and click **Update Chat Context** to load your documents into the AI's memory.")
        else:
            st.caption(f"Context loaded: {len(st.session_state.chat_knowledge_base):,} characters of document data.")
            
            # Display Chat History
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"], avatar="👤" if message["role"]=="user" else "🤖"):
                    st.markdown(message["content"])
            
            # Clear Chat Button
            col1, col2 = st.columns([6, 1])
            with col2:
                if st.button("🗑️ Clear Chat"):
                    st.session_state.chat_history = []
                    st.rerun()

            # Chat Input
            if prompt := st.chat_input("Ask a question (e.g., 'What was the Q1 revenue?', 'Compare liabilities to assets')..."):
                # Add user message to history and display
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with st.chat_message("user", avatar="👤"):
                    st.markdown(prompt)
                
                # Generate and display AI response
                with st.chat_message("assistant", avatar="🤖"):
                    with st.spinner("Analyzing documents and formulating response..."):
                        response = chat_with_ai(
                            st.session_state.chat_history, 
                            st.session_state.chat_knowledge_base, 
                            prompt
                        )
                    st.markdown(response)
                
                # Add AI response to history
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.rerun() # Rerun to render the new messages properly via the loop

    conn.close()

# ==========================================
# MAIN ROUTER
# ==========================================
def main():
    if st.session_state.current_user and st.session_state.page != 'dashboard':
        st.session_state.page = 'dashboard'
    
    if st.session_state.page == 'signup': signup_page()
    elif st.session_state.page == 'login': login_page()
    elif st.session_state.page == 'forgot_password': forgot_password_page()
    elif st.session_state.page == 'dashboard':
        if st.session_state.current_user: dashboard_page()
        else: go_to('login')

if __name__ == "__main__":
    main()