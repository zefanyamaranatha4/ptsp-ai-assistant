import os, sqlite3, streamlit as st
from groq import Groq
from dotenv import load_dotenv
import urllib.request, urllib.parse, json, re

DB_PATH     = './ptsp_docs.db'
DB_DRIVE_ID = '11aXRiR5N7XDsZuGSKZmp_eVLmFyN0Z25'  # Ganti dengan File ID dari BAB 1.3

if not os.path.exists(DB_PATH):
    with st.spinner('Mengunduh database (hanya sekali, mohon tunggu)...'):
        import gdown
        url = f'https://drive.google.com/uc?id={DB_DRIVE_ID}'
        gdown.download(url, DB_PATH, quiet=False)
    st.success('Database berhasil diunduh!')


load_dotenv()

groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
GROQ_MODEL  = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
DB_PATH     = './ptsp_docs.db'

st.set_page_config(page_title='AI Assistant — PTSP', page_icon='🤖', layout='wide')

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #1E3A5F; }
[data-testid="stSidebar"] * { color: white !important; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.1); color: white !important;
    border: 1px solid rgba(255,255,255,0.2); border-radius: 8px;
    text-align: left; font-size: 13px;
}
[data-testid="stSidebar"] .stButton > button:hover { background: rgba(255,255,255,0.2); }
.source-box { background:#f0f7ff; border-left:3px solid #1E3A5F;
    padding:8px 12px; border-radius:4px; font-size:13px; margin-top:8px; }
.web-box { background:#f0fff4; border-left:3px solid #1A5C3A;
    padding:8px 12px; border-radius:4px; font-size:13px; margin-top:4px; }
</style>
""", unsafe_allow_html=True)

KAMUS = {
    'pompa':'pump','pipa':'pipe','katup':'valve','motor':'motor',
    'listrik':'electrical','pelumas':'lubrication','oli':'oil',
    'tekanan':'pressure','suhu':'temperature','aliran':'flow',
    'perawatan':'maintenance','perbaikan':'repair','jarak':'gap',
    'celah':'gap','ukuran':'dimension','prosedur':'procedure',
    'spesifikasi':'specification','kalibrasi':'calibration',
    'instrumen':'instrument','kompresor':'compressor','turbin':'turbine',
    'generator':'generator','kabel':'cable','keselamatan':'safety',
    'gangguan':'fault','getaran':'vibration','inspeksi':'inspection',
    'pengujian':'testing','penggantian':'replacement','tangki':'tank',
    'pendingin':'cooling','pemanas':'heating','plat':'plate',
    'stator':'stator','rotor':'rotor','shaft':'shaft','roller':'roller',
    'separator':'separator','fan':'fan','belt':'belt','gearbox':'gearbox',
    'bearing':'bearing','seal':'seal','coupling':'coupling',
    'impeller':'impeller','nozzle':'nozzle','filter':'filter',
    'mill':'mill','kiln':'kiln','crusher':'crusher','blower':'blower',
    'conveyor':'conveyor','elevator':'elevator','silo':'silo',
    'standar':'standard','formulir':'form','pemeriksaan':'inspection',
    'pengukuran':'measurement','toleransi':'tolerance','raw':'raw',
    'finish':'finish','cement':'cement','clinker':'clinker',
    'qc':'qc','form':'form','checklist':'checklist','drawing':'drawing',
    'gambar':'drawing','part':'part','daftar':'list',
}

def translate_query(query):
    return [KAMUS.get(w.strip('.,?!()'), w.strip('.,?!()'))
            for w in query.lower().split()]

def web_search(query, max_results=3):
    try:
        encoded = urllib.parse.quote(f"{query} cement plant technical specification")
        url     = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req     = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        results = []
        if data.get('AbstractText'):
            results.append({'title': data.get('Heading','Ref'),
                           'snippet': data['AbstractText'][:400],
                           'url': data.get('AbstractURL','')})
        for topic in data.get('RelatedTopics', [])[:max_results]:
            if isinstance(topic, dict) and topic.get('Text'):
                results.append({'title': topic['Text'][:60],
                               'snippet': topic['Text'][:300],
                               'url': topic.get('FirstURL','')})
        return results[:max_results]
    except:
        return []

def check_db_has_folder_path():
    """Cek apakah DB versi baru (ada kolom folder_path)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('SELECT folder_path FROM docs LIMIT 1')
        conn.close()
        return True
    except:
        return False

def search_db(query, top_k=6):
    try:
        conn      = sqlite3.connect(DB_PATH)
        words     = translate_query(query)
        has_fp    = check_db_has_folder_path()
        results, seen = [], set()

        # Tentukan SELECT berdasarkan versi DB
        if has_fp:
            SELECT = 'SELECT file_name, file_path, content, folder_path FROM docs'
        else:
            SELECT = 'SELECT file_name, file_path, content, "" as folder_path FROM docs'

        def add(rows):
            for r in rows:
                key = r[0] + r[2][:60]
                if key not in seen:
                    seen.add(key)
                    results.append({
                        'file_name':   r[0],
                        'file_path':   r[1],
                        'content':     r[2],
                        'folder_path': r[3] if len(r) > 3 else ''
                    })

        # Cari berdasarkan folder_path jika ada keyword folder
        folder_keywords = ['qc', 'qc-form', 'qcform', 'drawing', 'manual',
                          'spesifikasi', 'specification', 'part list', 'partlist']
        query_lower = query.lower()
        folder_hint = next((k for k in folder_keywords if k in query_lower), None)

        if has_fp and folder_hint:
            folder_map = {
                'qc': 'QC-FORM', 'qc-form': 'QC-FORM', 'qcform': 'QC-FORM',
                'drawing': 'Drawing', 'manual': 'Manual & Spesifikasi',
                'spesifikasi': 'Manual & Spesifikasi',
                'specification': 'Manual & Spesifikasi',
                'part list': 'Part List', 'partlist': 'Part List',
            }
            target_folder = folder_map.get(folder_hint, '')
            if target_folder:
                try:
                    rows = conn.execute(
                        f"{SELECT} WHERE folder_path LIKE ? ORDER BY rank LIMIT ?",
                        (f'%{target_folder}%', top_k * 2)
                    ).fetchall()
                    add(rows)
                except:
                    pass

        # Prioritas 1: frasa 3 kata
        for i in range(len(words) - 2):
            phrase = ' '.join(words[i:i+3])
            try:
                add(conn.execute(
                    f"{SELECT} WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                    (f'"{phrase}"', top_k)
                ).fetchall())
            except: pass

        # Prioritas 2: frasa 2 kata
        for i in range(len(words) - 1):
            phrase = ' '.join(words[i:i+2])
            try:
                add(conn.execute(
                    f"{SELECT} WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                    (f'"{phrase}"', top_k)
                ).fetchall())
            except: pass

        # Prioritas 3: kata tunggal terpanjang
        if len(results) < 3:
            for word in sorted(set(words), key=len, reverse=True)[:4]:
                if len(word) < 3: continue
                try:
                    add(conn.execute(
                        f"{SELECT} WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                        (word, top_k)
                    ).fetchall())
                except: pass

        conn.close()
        return results[:top_k]
    except Exception as e:
        return []

@st.cache_resource
def get_db_stats():
    if not os.path.exists(DB_PATH): return 0, 0
    conn   = sqlite3.connect(DB_PATH)
    files  = conn.execute('SELECT COUNT(*) FROM indexed_files').fetchone()[0]
    chunks = conn.execute('SELECT COUNT(*) FROM docs').fetchone()[0]
    conn.close()
    return files, chunks

files_count, chunks_count = get_db_stats()

with st.sidebar:
    st.markdown("### 🤖 AI Assistant PTSP")
    st.markdown("*Unit Evaluasi Proses dan Energi*")
    st.divider()
    st.markdown("**📊 Database**")
    st.metric("File Terindeks", f"{files_count:,}")
    st.metric("Total Chunks", f"{chunks_count:,}")
    st.divider()
    st.markdown("**💡 Contoh Pertanyaan**")
    examples = [
        "QC Form raw mill standar apa saja?",
        "Berapa clearance bearing roller raw mill?",
        "Drawing separator raw mill",
        "Part list gearbox raw mill",
        "Hydraulic pressure setting vertical mill",
        "Troubleshooting vibration high pada mill",
        "Manual & spesifikasi OK mill",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state['pending'] = ex
    st.divider()
    use_web = st.toggle("🌐 Web search fallback", value=True)
    if st.button("🗑️ Reset chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("🤖 AI Assistant — PTSP")
st.caption("Dokumen: Drawing | Manual & Spesifikasi | Part List | QC-FORM")

if 'messages' not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg['role']):
        st.markdown(msg['content'], unsafe_allow_html=True)

query = st.session_state.pop('pending', None) or st.chat_input(
    "Tanya dalam Bahasa Indonesia atau Inggris..."
)

if query:
    st.session_state.messages.append({'role': 'user', 'content': query})
    with st.chat_message('user'):
        st.markdown(query)

    with st.chat_message('assistant'):
        with st.spinner('Mencari...'):
            docs        = search_db(query)
            web_results = []

            if use_web and len(docs) < 2:
                web_query   = ' '.join(translate_query(query))
                web_results = web_search(web_query)

            # Bangun konteks dengan folder path
            ctx_parts = []
            if docs:
                ctx_parts.append("=== DOKUMEN INTERNAL PTSP ===")
                for d in docs:
                    header = f"[{d['file_name']}]"
                    if d.get('folder_path'):
                        header += f" (📁 {d['folder_path']})"
                    ctx_parts.append(f"{header}\n{d['content']}")
            else:
                ctx_parts.append("=== DOKUMEN INTERNAL ===\nTidak ada dokumen relevan.")

            if web_results:
                ctx_parts.append("\n=== REFERENSI TEKNIS INTERNET ===")
                for w in web_results:
                    ctx_parts.append(f"[{w['title']}]\n{w['snippet']}")

            context = '\n\n---\n\n'.join(ctx_parts)

            system_prompt = """Anda adalah AI Assistant teknis untuk Unit Evaluasi Proses dan Energi PTSP (pabrik semen Indarung VI).

STRUKTUR FOLDER DATABASE:
- Drawing        → gambar teknis, P&ID, GA drawing
- Manual & Spesifikasi → manual operasi, spesifikasi teknik
- Part List      → daftar part/spare part equipment
- QC-FORM        → form pemeriksaan & quality control tiap equipment

ATURAN:
1. Prioritaskan DOKUMEN INTERNAL. Sebutkan nama file dan folder sumbernya.
2. Jika user tanya QC Form → cari di folder QC-FORM
3. Jika user tanya drawing/gambar → cari di folder Drawing
4. Jika user tanya spesifikasi/manual → cari di Manual & Spesifikasi
5. Jika user tanya part/spare → cari di Part List
6. Referensi internet hanya untuk konteks teknis jika dokumen tidak ada
7. Jawab Bahasa Indonesia, teknis dan formal
8. Terjemahkan dokumen Inggris ke Indonesia dalam jawaban
9. Jika dokumen tidak ditemukan, katakan terus terang dan sarankan folder yang tepat"""

            try:
                completion = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': f"Konteks:\n{context}\n\nPertanyaan: {query}"}
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
                answer = completion.choices[0].message.content
                st.markdown(answer)

                if docs:
                    html = '<div class="source-box">📄 <b>Sumber:</b><br>'
                    for d in docs:
                        label = d['file_name']
                        if d.get('folder_path'):
                            label += f" <i>({d['folder_path']})</i>"
                        if d['file_path']:
                            html += f'• <a href="{d["file_path"]}" target="_blank">{label}</a><br>'
                        else:
                            html += f'• {label}<br>'
                    html += '</div>'
                    st.markdown(html, unsafe_allow_html=True)

                if web_results:
                    whtml = '<div class="web-box">🌐 <b>Referensi Internet:</b><br>'
                    for w in web_results:
                        if w['url']:
                            whtml += f'• <a href="{w["url"]}" target="_blank">{w["title"][:70]}</a><br>'
                    whtml += '</div>'
                    st.markdown(whtml, unsafe_allow_html=True)

                full = answer
                if docs:
                    full += '\n\n**Sumber:** ' + ', '.join(
                        f"{d['file_name']} ({d.get('folder_path','')})" for d in docs
                    )
                st.session_state.messages.append({'role': 'assistant', 'content': full})

            except Exception as e:
                err = f'❌ Error: {e}'
                st.error(err)
                st.session_state.messages.append({'role': 'assistant', 'content': err})