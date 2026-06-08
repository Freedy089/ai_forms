# google_services.py
import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

SCOPES = [
    'https://www.googleapis.com/auth/forms',
    'https://www.googleapis.com/auth/drive'
]

def get_google_creds():
    """Menangani otentikasi login Google User"""
    creds = None
    token_payload = config.GOOGLE_TOKEN_JSON.strip()
    if token_payload:
        creds = Credentials.from_authorized_user_info(json.loads(token_payload), SCOPES)
    elif os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_secret_payload = config.GOOGLE_CLIENT_SECRET_JSON.strip()
            if client_secret_payload:
                client_config = json.loads(client_secret_payload)
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            else:
                raise ValueError(
                    "Google OAuth belum dikonfigurasi. Isi GOOGLE_TOKEN_JSON dan "
                    "GOOGLE_CLIENT_SECRET_JSON, atau sediakan token.json dan credentials.json."
                )
            creds = flow.run_local_server(port=0)

        if not token_payload:
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
    return creds

def resolve_correct_option(question):
    """Mengubah kunci jawaban huruf menjadi teks opsi penuh untuk Google Forms."""
    answer_key = str(question.get('kunci_jawaban', '')).strip()
    options = question.get('pilihan') or []
    if not answer_key or not options:
        return None

    normalized_key = answer_key.upper().strip()
    for option in options:
        cleaned_option = option.strip()
        if cleaned_option.upper() == normalized_key:
            return cleaned_option

        prefix = cleaned_option.split('.', 1)[0].split(')', 1)[0].strip().upper()
        if prefix == normalized_key:
            return cleaned_option

    return None

def build_grading(question):
    """Membangun konfigurasi grading untuk Google Forms quiz."""
    points = max(1, int(question.get('poin', 1)))
    grading = {
        'pointValue': points
    }

    if question.get('tipe', '').lower() == 'pg':
        correct_option = resolve_correct_option(question)
        if correct_option:
            grading['correctAnswers'] = {
                'answers': [{'value': correct_option}]
            }

    return grading

def create_google_form(title, questions_list, creds=None):
    """Membuat Google Form quiz berdasarkan campuran soal PG dan Esai dari AI."""
    creds = creds or get_google_creds()
    form_service = build('forms', 'v1', credentials=creds)
    
    clean_title = (title or "").strip() or "Quiz"
    form_body = {
        'info': {
            'title': clean_title,
            'documentTitle': clean_title
        }
    }
    form = form_service.forms().create(body=form_body).execute()
    form_id = form['formId']
    
    requests = []
    requests.append({
        'updateSettings': {
            'settings': {
                'quizSettings': {
                    'isQuiz': True
                }
            },
            'updateMask': 'quizSettings.isQuiz'
        }
    })

    for index, q in enumerate(questions_list):
        question_item = {
            'required': True,
            'grading': build_grading(q)
        }
        
        if q['tipe'].lower() == 'esai':
            question_item['textQuestion'] = {'paragraph': True}
        else:
            question_item['choiceQuestion'] = {
                'type': 'RADIO',
                'options': [{'value': opt} for opt in q['pilihan']]
            }
            
        item = {
            'createItem': {
                'item': {
                    'title': q['pertanyaan'],
                    'questionItem': {
                        'question': question_item
                    }
                },
                'location': {'index': index}
            }
        }
        requests.append(item)
        
    form_service.forms().batchUpdate(formId=form_id, body={'requests': requests}).execute()
    return {
        'form_id': form_id,
        'edit_url': f"https://docs.google.com/forms/d/{form_id}/edit",
        'view_url': form.get('responderUri')
    }
