# agent.py
import json
import re
import requests
import config
from google_services import create_google_form
from docx_generator import generate_docx_file

SYSTEM_PROMPT = """
Anda adalah asisten pembuat soal ujian sekolah dan form survey (SD/SMP/SMK/SMA).
Tugas Anda adalah membaca instruksi user dan membuatkan soal atau form survey berdasarkan permintaan spesifik mereka.

Aturan Pembuatan Konten:
1. Perhatikan tipe soal yang diminta (bisa Pilihan Ganda (PG) saja, Esai saja, atau Campuran keduanya).
2. Jika user meminta soal Pilihan Ganda (PG), perhatikan batas opsinya:
   - Jika untuk SD/SMP biasanya sampai D (A, B, C, D).
   - Jika untuk SMA/SMK atau jika diminta eksplisit, buat sampai E (A, B, C, D, E).
3. Jika tipe soal adalah 'esai', kosongkan properti 'pilihan' (isi array kosong []) dan isi properti 'kunci_jawaban' dengan string kosong "". Karena esai akan dinilai manual oleh guru.
4. Setiap soal WAJIB memiliki properti 'poin' bertipe angka bulat positif.
5. Jika instruksi user menentukan poin tertentu, gunakan angka poin yang sama untuk setiap soal.
6. Untuk soal PG, isi 'kunci_jawaban' dengan huruf opsi yang benar saja, misal "A" atau "C".
7. Jika user meminta survey / survei / kuesioner / non-quiz:
   - jangan buat jawaban benar/salah;
   - kosongkan properti 'kunci_jawaban' untuk semua butir;
   - isi 'poin' dengan angka 1 sebagai placeholder internal;
   - fokus pada butir pertanyaan survey yang natural dan relevan.

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
      "poin": 2,
      "penjelasan": "Alasan mengapa jawaban A benar. Jika soal hitungan seperti matematika/fisika, tulis langkah perhitungan singkat dan jelas sampai hasil akhir."
    },
    {
      "tipe": "esai",
      "pertanyaan": "Teks soal esai di sini?",
      "pilihan": [],
      "kunci_jawaban": "",
      "poin": 2,
      "penjelasan": "Garis besar jawaban yang diharapkan atau poin-poin penilaian."
    }
  ]
}
"""

DEFAULT_POINTS = 1
MAX_AI_ATTEMPTS = 3
MAX_PG_PER_BATCH = 20
MAX_ESAI_PER_BATCH = 5


def detect_content_type(user_prompt):
    lower_prompt = user_prompt.lower()
    survey_keywords = [
        "survey", "survei", "kuesioner", "kuisioner", "questionnaire",
        "non-quiz", "non quiz", "bukan quiz", "tanpa quiz", "tanpa kuis",
        "tidak perlu quiz", "tidak usah quiz", "form biasa", "google form biasa",
        "tanpa poin", "tanpa point", "tanpa kunci jawaban"
    ]
    if any(keyword in lower_prompt for keyword in survey_keywords):
        return "survey"
    return "quiz"

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
    stripped = text_output.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return stripped[first_brace:last_brace + 1].strip()

    return stripped


def parse_json_relaxed(text_output):
    cleaned_text = extract_json(text_output)
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    first_brace = cleaned_text.find("{")
    while first_brace != -1:
        try:
            parsed, _ = decoder.raw_decode(cleaned_text[first_brace:])
            return parsed
        except json.JSONDecodeError:
            first_brace = cleaned_text.find("{", first_brace + 1)

    raise json.JSONDecodeError("Tidak ditemukan object JSON valid.", cleaned_text, 0)

def extract_requested_points(user_prompt):
    """Mengambil poin default dan poin khusus per tipe soal dari instruksi user."""
    lower_prompt = user_prompt.lower()
    point_config = {
        "default": DEFAULT_POINTS,
        "pg": None,
        "esai": None
    }

    typed_patterns = [
        (r'(pilihan\s*ganda|pg)\s*(?:sebanyak\s*\d+\s*soal\s*)?(?:dengan\s*)?(\d+)\s*(?:poin|point)\b', "pg"),
        (r'(esai|essay)\s*(?:sebanyak\s*\d+\s*soal\s*)?(?:dengan\s*)?(\d+)\s*(?:poin|point)\b', "esai"),
        (r'(\d+)\s*(?:poin|point)\s*(?:untuk|buat)\s*(pilihan\s*ganda|pg)\b', "pg"),
        (r'(\d+)\s*(?:poin|point)\s*(?:untuk|buat)\s*(esai|essay)\b', "esai"),
    ]

    for pattern, question_type in typed_patterns:
        match = re.search(pattern, lower_prompt)
        if match:
            point_value = match.group(2) if len(match.groups()) > 1 and match.group(2).isdigit() else match.group(1)
            point_config[question_type] = max(1, int(point_value))

    general_patterns = [
        r'(\d+)\s*poin\b',
        r'(\d+)\s*point\b',
        r'poin(?:\s+per\s+soal)?\s*(?:nya|adalah|=|:)?\s*(\d+)\b',
        r'point(?:\s+per\s+soal)?\s*(?:nya|adalah|=|:)?\s*(\d+)\b',
    ]
    for pattern in general_patterns:
        match = re.search(pattern, lower_prompt)
        if match:
            point_config["default"] = max(1, int(match.group(1)))
            break

    if point_config["pg"] is None:
        point_config["pg"] = point_config["default"]
    if point_config["esai"] is None:
        point_config["esai"] = point_config["default"]

    return point_config

def extract_requested_counts(user_prompt):
    """Mengambil jumlah soal per tipe dari prompt user bila disebutkan eksplisit."""
    lower_prompt = user_prompt.lower()
    count_config = {
        "pg": None,
        "esai": None
    }

    pg_patterns = [
        r'(\d+)\s*(?:soal\s*)?(?:pilihan\s*ganda|pg)\b',
        r'(?:pilihan\s*ganda|pg)\s*(?:sebanyak\s*)?(\d+)\s*soal\b',
    ]
    esai_patterns = [
        r'(\d+)\s*(?:soal\s*)?(?:esai|essay)\b',
        r'(?:esai|essay)\s*(?:sebanyak\s*)?(\d+)\s*soal\b',
    ]

    for pattern in pg_patterns:
        match = re.search(pattern, lower_prompt)
        if match:
            count_config["pg"] = max(1, int(match.group(1)))
            break

    for pattern in esai_patterns:
        match = re.search(pattern, lower_prompt)
        if match:
            count_config["esai"] = max(1, int(match.group(1)))
            break

    return count_config

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

def build_form_title(user_prompt, ai_title, content_type="quiz"):
    subject = extract_subject(user_prompt) or simplify_ai_title(ai_title)
    grade_label = extract_grade_label(user_prompt)

    if subject and grade_label:
        return f"{subject} - {grade_label}"
    if subject:
        return subject
    if grade_label:
        return f"{'Survey' if content_type == 'survey' else 'Quiz'} - {grade_label}"
    return normalize_whitespace(ai_title) or ("Survey" if content_type == "survey" else "Quiz")

def format_points_summary(point_config, content_type="quiz"):
    if content_type == "survey":
        return "Tidak digunakan (survey)"
    if point_config["pg"] == point_config["esai"]:
        return f"{point_config['pg']} poin per soal"
    return f"PG {point_config['pg']} poin, Esai {point_config['esai']} poin"

def format_counts_summary(count_config):
    parts = []
    if count_config["pg"] is not None:
        parts.append(f"{count_config['pg']} PG")
    if count_config["esai"] is not None:
        parts.append(f"{count_config['esai']} esai")
    return ", ".join(parts)

def should_chunk_large_request(count_config):
    if count_config["pg"] is not None and count_config["pg"] > MAX_PG_PER_BATCH:
        return True
    if count_config["esai"] is not None and count_config["esai"] > MAX_ESAI_PER_BATCH:
        return True
    return False

def distribute_count(total, batch_count):
    if total is None:
        return [None] * batch_count
    base, remainder = divmod(total, batch_count)
    distribution = []
    for index in range(batch_count):
        distribution.append(base + (1 if index < remainder else 0))
    return distribution

def build_chunk_count_configs(count_config):
    pg_total = count_config["pg"] or 0
    esai_total = count_config["esai"] or 0
    batch_count = max(
        1,
        (pg_total + MAX_PG_PER_BATCH - 1) // MAX_PG_PER_BATCH if pg_total else 1,
        (esai_total + MAX_ESAI_PER_BATCH - 1) // MAX_ESAI_PER_BATCH if esai_total else 1
    )

    pg_distribution = distribute_count(count_config["pg"], batch_count)
    esai_distribution = distribute_count(count_config["esai"], batch_count)

    chunk_configs = []
    for index in range(batch_count):
        chunk_config = {
            "pg": pg_distribution[index],
            "esai": esai_distribution[index]
        }
        if chunk_config["pg"] or chunk_config["esai"]:
            chunk_configs.append(chunk_config)
    return chunk_configs

def build_ai_prompt(user_input, point_config, count_config, content_type="quiz"):
    count_instructions = ""
    if count_config["pg"] is not None:
        count_instructions += f"- Jumlah soal PG harus tepat {count_config['pg']} butir.\n"
    if count_config["esai"] is not None:
        count_instructions += f"- Jumlah soal esai harus tepat {count_config['esai']} butir.\n"

    if content_type == "survey":
        extra_instructions = (
            f"- Ini adalah form survey/non-quiz, bukan ujian.\n"
            f"- Jangan buat jawaban benar/salah.\n"
            f"- Semua butir wajib memakai 'kunci_jawaban' kosong.\n"
            f"- Isi properti 'poin' dengan angka 1 sebagai placeholder internal.\n"
            f"- Isi properti 'penjelasan' dengan tujuan singkat atau konteks pertanyaan bila relevan.\n"
            f"- Gunakan gaya bahasa yang cocok untuk survey atau kuesioner.\n"
        )
    else:
        extra_instructions = (
            f"- Soal PG harus memakai {point_config['pg']} poin per butir.\n"
            f"- Soal esai harus memakai {point_config['esai']} poin per butir.\n"
            f"- Jika output dibuat untuk Google Form, siapkan soal agar cocok dijadikan quiz.\n"
            f"- Untuk soal PG, isi 'kunci_jawaban' dengan huruf opsi yang benar.\n"
            f"- Untuk soal esai, biarkan 'kunci_jawaban' kosong.\n"
            f"- Setiap butir wajib memiliki properti 'penjelasan'.\n"
            f"- Penjelasan harus menerangkan mengapa jawaban itu benar.\n"
            f"- Khusus soal matematika/angka, penjelasan wajib memuat langkah hitung yang ringkas namun jelas sampai hasil akhir.\n"
        )

    return (
        f"{user_input.strip()}\n\n"
        f"Instruksi sistem tambahan:\n"
        f"- Judul wajib singkat dan sederhana, format utamanya: Mata Pelajaran - Kelas.\n"
        f"- Setiap soal wajib memiliki properti 'poin'.\n"
        f"{count_instructions}"
        f"{extra_instructions}"
    )

def normalize_questions(questions, point_config, content_type="quiz"):
    """Menjamin setiap butir soal punya bentuk data yang konsisten untuk downstream."""
    if not isinstance(questions, list):
        raise ValueError("Format 'soal' dari AI tidak valid. Data soal harus berupa array/list.")

    normalized_questions = []
    for index, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            raise ValueError(
                f"Format soal nomor {index} tidak valid. Setiap butir soal harus berupa object JSON."
            )

        question_type = str(question.get('tipe', 'esai')).strip().lower()
        fallback_points = point_config["pg"] if question_type == "pg" else point_config["esai"]
        raw_choices = question.get('pilihan') or []
        if isinstance(raw_choices, str):
            raw_choices = [choice.strip() for choice in re.split(r'\n|;', raw_choices) if choice.strip()]
        elif not isinstance(raw_choices, list):
            raw_choices = []

        normalized_question = {
            'tipe': question_type,
            'pertanyaan': str(question.get('pertanyaan', '')).strip(),
            'pilihan': [str(choice).strip() for choice in raw_choices if str(choice).strip()],
            'kunci_jawaban': str(question.get('kunci_jawaban', '')).strip(),
            'poin': max(1, int(question.get('poin', fallback_points))),
            'penjelasan': str(question.get('penjelasan', '')).strip()
        }
        if content_type == "survey":
            normalized_question['kunci_jawaban'] = ""
            normalized_question['poin'] = 1
        if not normalized_question['penjelasan']:
            if content_type == "survey":
                normalized_question['penjelasan'] = "Pertanyaan ini digunakan untuk mengumpulkan pendapat atau informasi responden."
            elif question_type == "esai":
                normalized_question['penjelasan'] = "Gunakan jawaban yang memuat konsep utama yang diminta pada soal."
            else:
                normalized_question['penjelasan'] = "Jawaban ini dipilih karena paling sesuai dengan konsep yang diuji pada soal."
        if not normalized_question['pertanyaan']:
            raise ValueError(f"Soal nomor {index} tidak memiliki teks pertanyaan.")
        normalized_questions.append(normalized_question)
    return normalized_questions

def validate_question_counts(questions, count_config):
    actual_pg = sum(1 for question in questions if question["tipe"] == "pg")
    actual_esai = sum(1 for question in questions if question["tipe"] == "esai")

    if count_config["pg"] is not None and actual_pg != count_config["pg"]:
        raise ValueError(
            f"Jumlah soal PG tidak sesuai. Diminta {count_config['pg']}, tetapi AI membuat {actual_pg}."
        )
    if count_config["esai"] is not None and actual_esai != count_config["esai"]:
        raise ValueError(
            f"Jumlah soal esai tidak sesuai. Diminta {count_config['esai']}, tetapi AI membuat {actual_esai}."
        )

def build_batch_user_prompt(user_input, batch_count_config, batch_index, total_batches):
    batch_parts = []
    if batch_count_config["pg"]:
        batch_parts.append(f"{batch_count_config['pg']} soal PG")
    if batch_count_config["esai"]:
        batch_parts.append(f"{batch_count_config['esai']} soal esai")
    batch_summary = " dan ".join(batch_parts)

    return (
        f"{user_input.strip()}\n\n"
        f"Batch {batch_index} dari {total_batches}. "
        f"Untuk batch ini, buat tepat {batch_summary}. "
        f"Hindari pengulangan soal yang terlalu mirip antar batch."
    )

def generate_single_batch_quiz_data(user_input, point_config, count_config, content_type="quiz"):
    last_error = None
    current_prompt = user_input

    for attempt in range(MAX_AI_ATTEMPTS):
        ai_response = call_owl_alpha(build_ai_prompt(current_prompt, point_config, count_config, content_type))
        try:
            quiz_data = parse_json_relaxed(ai_response)
        except json.JSONDecodeError as exc:
            last_error = exc
            if attempt == MAX_AI_ATTEMPTS - 1:
                raise ValueError(
                    "AI mengembalikan JSON yang tidak valid. "
                    "Coba ulangi permintaan atau sederhanakan prompt."
                ) from exc
            current_prompt = (
                f"{user_input.strip()}\n\n"
                f"Perbaiki output sebelumnya. JSON Anda tidak valid untuk dibaca sistem. "
                f"Kembalikan hanya satu blok ```json``` yang berisi object JSON murni tanpa teks tambahan. "
                f"Pastikan seluruh object JSON selesai ditutup sampai kurung kurawal terakhir."
            )
            continue
        questions = normalize_questions(quiz_data['soal'], point_config, content_type)

        try:
            validate_question_counts(questions, count_config)
            return quiz_data, questions
        except ValueError as exc:
            last_error = exc
            if attempt == MAX_AI_ATTEMPTS - 1:
                raise
            current_prompt = (
                f"{user_input.strip()}\n\n"
                f"Perbaiki output sebelumnya. {exc} "
                f"Pastikan jumlah soal persis sesuai permintaan."
            )

    if last_error:
        raise last_error

def generate_quiz_data(user_input, point_config, count_config, content_type="quiz"):
    if not should_chunk_large_request(count_config):
        return generate_single_batch_quiz_data(user_input, point_config, count_config, content_type)

    chunk_count_configs = build_chunk_count_configs(count_config)
    all_questions = []
    batch_title = None

    for index, chunk_count_config in enumerate(chunk_count_configs, 1):
        batch_prompt = build_batch_user_prompt(user_input, chunk_count_config, index, len(chunk_count_configs))
        quiz_data, questions = generate_single_batch_quiz_data(batch_prompt, point_config, chunk_count_config, content_type)
        if not batch_title:
            batch_title = quiz_data.get("judul", "Survey" if content_type == "survey" else "Quiz")
        all_questions.extend(questions)

    validate_question_counts(all_questions, count_config)
    return {"judul": batch_title, "soal": all_questions}, all_questions

def generate_quiz_from_prompt(user_input, output_mode=None, google_creds=None):
    """Menjalankan alur utama pembuatan soal agar bisa dipakai CLI dan Telegram."""
    content_type = detect_content_type(user_input)
    point_config = extract_requested_points(user_input)
    count_config = extract_requested_counts(user_input)
    chunked_generation = should_chunk_large_request(count_config)
    mode = output_mode or "form"
    if output_mode is None and ("word" in user_input.lower() or "docx" in user_input.lower()):
        mode = "word"

    quiz_data, questions = generate_quiz_data(user_input, point_config, count_config, content_type)
    title = build_form_title(user_input, quiz_data.get('judul', 'Survey' if content_type == 'survey' else 'Quiz'), content_type)
    result = {
        'title': title,
        'questions': questions,
        'mode': mode,
        'content_type': content_type,
        'point_config': point_config,
        'points_summary': format_points_summary(point_config, content_type),
        'counts_summary': format_counts_summary(count_config),
        'chunked_generation': chunked_generation
    }

    if mode == "form":
        result['form_links'] = create_google_form(title, questions, creds=google_creds, as_quiz=(content_type == "quiz"))
    else:
        result['word_files'] = generate_docx_file(title, questions)

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
        points_summary = result['points_summary']
        
        print(f"[2/3] Konten berhasil dibuat: '{title}' ({len(questions)} butir ditemukan, tipe: {result['content_type']}).")
        if result['chunked_generation']:
            print("[Info] Permintaan besar diproses dalam beberapa batch AI lalu digabung.")
        
        if mode == "form":
            form_kind = "Quiz Form" if result["content_type"] == "quiz" else "Survey Form"
            print(f"[3/3] Menghubungkan ke Google API untuk generate {form_kind} dengan skema poin {points_summary}...")
            form_links = result['form_links']
            print(f"\n✨ BERHASIL! Google {form_kind} telah dibuat di akun Anda.")
            print(f"🛠️ Link Editor Google Form: {form_links['edit_url']}")
            print(f"🔗 Link View/Responder Google Form: {form_links['view_url']}")
            
        else:
            print("[3/3] Membuat file Word (.docx) di local device...")
            word_files = result['word_files']
            print(f"\n✨ BERHASIL! File Word telah disimpan di lokal device Anda.")
            print(f"📂 File soal: {word_files['questions_file_path']}")
            print(f"📂 File kunci jawaban: {word_files['answer_key_file_path']}")
            
    except json.JSONDecodeError:
        print("\n❌ Gagal: AI tidak mengembalikan format data JSON yang bersih.")
        print("Pastikan struktur prompt jelas atau coba ulangi perintah.")
    except Exception as e:
        print(f"\n❌ Terjadi kesalahan sistem: {e}")

if __name__ == "__main__":
    main()
