# agent.py
import json
import re
import requests
import config
from google_services import create_google_form
from docx_generator import generate_docx_file

SYSTEM_PROMPT = """
Anda adalah asisten pembuat soal ujian sekolah (SD/SMP/SMK/SMA).
Tugas Anda adalah membaca instruksi user dan membuatkan soal berdasarkan permintaan spesifik mereka.

Aturan Pembuatan Soal:
1. Perhatikan tipe soal yang diminta (bisa Pilihan Ganda (PG) saja, Esai saja, atau Campuran keduanya).
2. Jika user meminta soal Pilihan Ganda (PG), perhatikan batas opsinya:
   - Jika untuk SD/SMP biasanya sampai D (A, B, C, D).
   - Jika untuk SMA/SMK atau jika diminta eksplisit, buat sampai E (A, B, C, D, E).
3. Jika tipe soal adalah 'esai', kosongkan properti 'pilihan' (isi array kosong []) dan isi properti 'kunci_jawaban' dengan string kosong "". Karena esai akan dinilai manual oleh guru.
4. Setiap soal WAJIB memiliki properti 'poin' bertipe angka bulat positif.
5. Jika instruksi user menentukan poin tertentu, gunakan angka poin yang sama untuk setiap soal.
6. Untuk soal PG, isi 'kunci_jawaban' dengan huruf opsi yang benar saja, misal "A" atau "C".

PENTING: Anda HARUS merespon dalam format JSON MURNI di dalam blok markdown ```json ... ``` agar data aman dibaca sistem.
Jangan memberikan teks deskripsi tambahan di luar blok JSON tersebut.

Struktur JSON harus persis seperti ini:
{
  "judul": "Mata Pelajaran - Kelas",
  "soal": [
    {
      "tipe": "pg", 
      "pertanyaan": "Teks soal pilihan ganda di sini?",
      "pilihan": ["A. opsi 1", "B. opsi 2", "C. opsi 3", "D. opsi 4", "E. opsi 5"],
      "kunci_jawaban": "A",
      "poin": 2
    },
    {
      "tipe": "esai",
      "pertanyaan": "Teks soal esai di sini?",
      "pilihan": [],
      "kunci_jawaban": "",
      "poin": 2
    }
  ]
}
"""

DEFAULT_POINTS = 1

def call_owl_alpha(user_prompt):
    """Memanggil model Owl Alpha via OpenRouter"""
    if not config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY belum diatur.")
    if not config.OPENROUTER_API_KEY.startswith("sk-or-v1-"):
        raise ValueError(
            "OPENROUTER_API_KEY terbaca tetapi formatnya tidak valid. "
            "Pastikan value di Vercel adalah API key mentah tanpa kutip."
        )

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": config.MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3  # Diturunkan agar output AI konsisten mengikuti format JSON
    }
    
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
    
    # Cek status HTTP Response untuk mempermudah analisa jika API Key mati/salah model ID
    if response.status_code != 200:
        raise Exception(f"API OpenRouter Error [{response.status_code}]: {response.text}")
        
    try:
        res_json = response.json()
        content = res_json['choices'][0]['message']['content'].strip()
        return content
    except (KeyError, IndexError):
        raise Exception(f"Format respon API OpenRouter tidak sesuai standar: {response.text}")

def extract_json(text_output):
    """Mengekstrak teks JSON yang bersih meskipun terbungkus markdown ```json ... ```"""
    match = re.search(r'```json\s*(.*?)\s*```', text_output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text_output.strip()

def extract_requested_points(user_prompt):
    """Mengambil poin per soal dari instruksi user, fallback ke default."""
    patterns = [
        r'(\d+)\s*poin\b',
        r'(\d+)\s*point\b',
        r'poin(?:\s+per\s+soal)?\s*(?:nya|adalah|=|:)?\s*(\d+)\b',
        r'point(?:\s+per\s+soal)?\s*(?:nya|adalah|=|:)?\s*(\d+)\b',
    ]
    lower_prompt = user_prompt.lower()
    for pattern in patterns:
        match = re.search(pattern, lower_prompt)
        if match:
            return max(1, int(match.group(1)))
    return DEFAULT_POINTS

def normalize_whitespace(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()

def title_case_subject(subject):
    normalized_subject = normalize_whitespace(subject)
    if not normalized_subject:
        return normalized_subject

    uppercase_words = {'ipa', 'ips', 'pjok', 'pai', 'tik', 'bk'}
    parts = []
    for word in normalized_subject.split(' '):
        lower_word = word.lower()
        if lower_word in uppercase_words:
            parts.append(lower_word.upper())
        else:
            parts.append(lower_word.capitalize())
    return ' '.join(parts)

def extract_subject(user_prompt):
    patterns = [
        r'mata pelajaran\s+([a-zA-Z0-9&\/\-\s]+?)(?:\s+dengan|\s+untuk|\s+kelas|\s+materi|,|\.|$)',
        r'mapel\s+([a-zA-Z0-9&\/\-\s]+?)(?:\s+dengan|\s+untuk|\s+kelas|\s+materi|,|\.|$)',
        r'pelajaran\s+([a-zA-Z0-9&\/\-\s]+?)(?:\s+dengan|\s+untuk|\s+kelas|\s+materi|,|\.|$)',
    ]
    prompt = normalize_whitespace(user_prompt)
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return title_case_subject(match.group(1))
    return ""

def extract_grade_label(user_prompt):
    prompt = normalize_whitespace(user_prompt.lower())
    match = re.search(r'kelas\s+([0-9]{1,2}|xii|xi|x)\s*(sd|smp|sma|smk)?', prompt, re.IGNORECASE)
    if match:
        grade = match.group(1).upper()
        school_type = (match.group(2) or '').upper()
        return normalize_whitespace(f"{grade} {school_type}".strip())

    match = re.search(r'\b([0-9]{1,2}|xii|xi|x)\s*(sd|smp|sma|smk)\b', prompt, re.IGNORECASE)
    if match:
        grade = match.group(1).upper()
        school_type = match.group(2).upper()
        return f"{grade} {school_type}"

    return ""

def simplify_ai_title(ai_title):
    cleaned_title = normalize_whitespace(ai_title)
    if not cleaned_title:
        return cleaned_title

    base_title = re.split(r'\s*[-|:]\s*', cleaned_title, maxsplit=1)[0]
    return title_case_subject(base_title)

def build_form_title(user_prompt, ai_title):
    subject = extract_subject(user_prompt) or simplify_ai_title(ai_title)
    grade_label = extract_grade_label(user_prompt)

    if subject and grade_label:
        return f"{subject} - {grade_label}"
    if subject:
        return subject
    return normalize_whitespace(ai_title)

def build_ai_prompt(user_input, points_per_question):
    return (
        f"{user_input.strip()}\n\n"
        f"Instruksi sistem tambahan:\n"
        f"- Judul wajib singkat dan sederhana, format utamanya: Mata Pelajaran - Kelas.\n"
        f"- Setiap soal wajib memiliki properti 'poin' dengan nilai {points_per_question}.\n"
        f"- Jika output dibuat untuk Google Form, siapkan soal agar cocok dijadikan quiz.\n"
        f"- Untuk soal PG, isi 'kunci_jawaban' dengan huruf opsi yang benar.\n"
        f"- Untuk soal esai, biarkan 'kunci_jawaban' kosong.\n"
    )

def normalize_questions(questions, points_per_question):
    """Menjamin setiap butir soal punya bentuk data yang konsisten untuk downstream."""
    normalized_questions = []
    for question in questions:
        normalized_question = {
            'tipe': str(question.get('tipe', 'esai')).strip().lower(),
            'pertanyaan': str(question.get('pertanyaan', '')).strip(),
            'pilihan': question.get('pilihan') or [],
            'kunci_jawaban': str(question.get('kunci_jawaban', '')).strip(),
            'poin': max(1, int(question.get('poin', points_per_question)))
        }
        normalized_questions.append(normalized_question)
    return normalized_questions

def generate_quiz_from_prompt(user_input, output_mode=None, google_creds=None):
    """Menjalankan alur utama pembuatan soal agar bisa dipakai CLI dan Telegram."""
    points_per_question = extract_requested_points(user_input)
    mode = output_mode or "form"
    if output_mode is None and ("word" in user_input.lower() or "docx" in user_input.lower()):
        mode = "word"

    ai_response = call_owl_alpha(build_ai_prompt(user_input, points_per_question))
    cleaned_json_text = extract_json(ai_response)
    quiz_data = json.loads(cleaned_json_text)

    title = build_form_title(user_input, quiz_data.get('judul', 'Quiz'))
    questions = normalize_questions(quiz_data['soal'], points_per_question)
    result = {
        'title': title,
        'questions': questions,
        'mode': mode,
        'points_per_question': points_per_question
    }

    if mode == "form":
        result['form_links'] = create_google_form(title, questions, creds=google_creds)
    else:
        result['file_path'] = generate_docx_file(title, questions)

    return result

def main():
    print("=== Hermes Quiz Builder Agent v2.1 ===")
    user_input = input("\nMasukkan perintah Anda:\n> ")
        
    print("\n[1/3] Menghubungi Hermes Agent (Owl Alpha) untuk merancang soal...")
    try:
        result = generate_quiz_from_prompt(user_input)
        title = result['title']
        questions = result['questions']
        mode = result['mode']
        points_per_question = result['points_per_question']
        
        print(f"[2/3] Soal berhasil dibuat: '{title}' ({len(questions)} butir soal ditemukan).")
        
        if mode == "form":
            print(f"[3/3] Menghubungkan ke Google API untuk generate Quiz Form dengan {points_per_question} poin per soal...")
            form_links = result['form_links']
            print(f"\n✨ BERHASIL! Google Quiz Form telah dibuat di akun Anda.")
            print(f"🛠️ Link Editor Google Form: {form_links['edit_url']}")
            print(f"🔗 Link View/Responder Google Form: {form_links['view_url']}")
            
        else:
            print("[3/3] Membuat file Word (.docx) di local device...")
            file_path = result['file_path']
            print(f"\n✨ BERHASIL! File Word telah disimpan di lokal device Anda.")
            print(f"📂 Lokasi file: {file_path}")
            
    except json.JSONDecodeError:
        print("\n❌ Gagal: AI tidak mengembalikan format data JSON yang bersih.")
        print("Pastikan struktur prompt jelas atau coba ulangi perintah.")
    except Exception as e:
        print(f"\n❌ Terjadi kesalahan sistem: {e}")

if __name__ == "__main__":
    main()
