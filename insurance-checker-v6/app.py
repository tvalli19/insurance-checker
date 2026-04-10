"""
🏥 Verifica Copertura Assicurativa — v4.1
"""

import streamlit as st
import json
from pathlib import Path
from pdf_indexer import find_relevant_sections
from ai_analyzer import analyze_query

st.set_page_config(page_title="Verifica Copertura Assicurativa", page_icon="🏥", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://db.onlinewebfonts.com/c/12ff62164c9778917bddb93c6379cf47?family=Aeonik+Pro+Regular');
@import url('https://db.onlinewebfonts.com/c/81c9cfcec66a1bb46e90e184f4d04641?family=Aeonik+Pro+Medium');
@import url('https://db.onlinewebfonts.com/c/362636484f8ad521fec5a297fdc0ab12?family=Aeonik+Pro+Bold');
@import url('https://db.onlinewebfonts.com/c/3fb1f60e59aborede3f9a3068a530457?family=Aeonik+Pro+Light');
:root {
    --text: #1a1a1a; --text-secondary: #555; --text-light: #888;
    --bg: #ffffff; --bg-subtle: #f7f7f7; --border: #e0e0e0;
    --accent: #0066cc; --accent-light: #f0f6ff;
    --font: 'Aeonik Pro Regular', 'Aeonik Pro Medium', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-medium: 'Aeonik Pro Medium', 'Aeonik Pro Regular', sans-serif;
    --font-bold: 'Aeonik Pro Bold', 'Aeonik Pro Medium', sans-serif;
    --font-light: 'Aeonik Pro Light', 'Aeonik Pro Regular', sans-serif;
}
.stApp { font-family: var(--font); color: var(--text); }
#MainMenu, footer, .stDeployButton { display: none !important; }

.hdr { padding: 1.8rem 0 1rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }
.hdr h1 { font-size: 1.6rem; font-family: var(--font-bold); margin: 0 0 .2rem; letter-spacing: -.02em; }
.hdr p { color: var(--text-secondary); font-size: .9rem; margin: 0; font-family: var(--font-light); }

.result-card { border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; }
.result-card h2 { font-size: 1.15rem; font-family: var(--font-bold); margin: 0 0 .2rem; letter-spacing: -.01em; }
.result-card .subtitle { color: var(--text-secondary); font-size: .82rem; margin-bottom: 1rem; font-family: var(--font-light); }

.data-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; margin: .8rem 0; }
.data-row { display: contents; }
.data-label { padding: .65rem .9rem; background: var(--bg-subtle); font-size: .75rem; font-family: var(--font-medium); color: var(--text-secondary); text-transform: uppercase; letter-spacing: .04em; border-bottom: 1px solid var(--border); }
.data-value { padding: .65rem .9rem; font-size: .9rem; font-family: var(--font-medium); border-bottom: 1px solid var(--border); }
.data-grid .data-row:last-child .data-label,
.data-grid .data-row:last-child .data-value { border-bottom: none; }

.section-title { font-size: .8rem; font-family: var(--font-bold); text-transform: uppercase; letter-spacing: .05em; color: var(--text-secondary); margin: 1.2rem 0 .5rem; padding-bottom: .3rem; border-bottom: 1px solid var(--border); }

.doc-list, .lim-list { list-style: none; padding: 0; margin: 0; }
.doc-list li, .lim-list li { padding: .4rem 0; font-size: .85rem; border-bottom: 1px solid #f0f0f0; }
.doc-list li:last-child, .lim-list li:last-child { border-bottom: none; }
.doc-list li::before { content: "→ "; color: var(--text-light); }
.lim-list li { color: #7a5a00; }
.lim-list li::before { content: "— "; color: #c0a040; }

.notes-block { background: var(--bg-subtle); border-radius: 6px; padding: 1rem; margin-top: .5rem; font-size: .83rem; color: var(--text-secondary); line-height: 1.55; font-family: var(--font-light); }
.ctx-bar { background: #f8f9fa; border: 1px solid var(--border); border-radius: 6px; padding: .7rem 1rem; margin-top: 1rem; font-size: .82rem; color: var(--text-secondary); font-family: var(--font-light); }
</style>
""", unsafe_allow_html=True)


# ─── API Key ─────────────────────────────────────────────────────────────────
def get_api_key():
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except:
        pass
    return st.session_state.get("admin_api_key", "")

api_key = get_api_key()

with st.sidebar:
    has_secret = False
    try:
        has_secret = bool(st.secrets.get("ANTHROPIC_API_KEY", ""))
    except:
        pass
    if not has_secret:
        st.markdown("### Configurazione")
        admin_key = st.text_input("API Key", type="password")
        if admin_key:
            st.session_state.admin_api_key = admin_key
            api_key = admin_key
    st.markdown("---")
    st.markdown("### Tariffari")
    data_dir = Path("data")
    for f in sorted(data_dir.glob("*.index.json")) if data_dir.exists() else []:
        try:
            idx = json.loads(f.read_text(encoding="utf-8"))
            st.markdown(f"✅ {idx.get('name', f.stem)}")
        except:
            pass


# ─── Dati ────────────────────────────────────────────────────────────────────
@st.cache_data
def load_indices():
    d = Path("data")
    indices = {}
    if d.exists():
        for f in sorted(d.glob("*.index.json")):
            try:
                idx = json.loads(f.read_text(encoding="utf-8"))
                key = f.stem.replace('.pdf.index', '').replace('.index', '')
                indices[key] = idx
            except:
                pass
    return indices

indices = load_indices()

if not indices:
    st.error("Nessun tariffario disponibile.")
    st.stop()
if not api_key:
    st.warning("Servizio temporaneamente non disponibile.")
    st.stop()


# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hdr">
    <h1>Verifica Copertura Assicurativa</h1>
    <p>Cerca una prestazione sanitaria e scopri le condizioni di rimborso della tua assicurazione</p>
</div>""", unsafe_allow_html=True)


# ─── Assicurazione ───────────────────────────────────────────────────────────
if len(indices) > 1:
    ins_options = {k: v.get('name', k) for k, v in indices.items()}
    sel_id = st.selectbox("Assicurazione", list(ins_options.keys()), format_func=lambda x: ins_options[x])
else:
    sel_id = list(indices.keys())[0]
    st.markdown(f"**Assicurazione:** {indices[sel_id].get('name', sel_id)}")


# ─── Percorsi tematici ───────────────────────────────────────────────────────
THEMATIC_PATHS = {
    "gravidanza": {
        "title": "Gravidanza e Parto",
        "desc": "Ecografie, visite, parto, allattamento",
        "queries": ["ecografia ostetrica", "parto e assistenza ostetrica", "allattamento artificiale",
                     "visita ginecologica", "amniocentesi", "villocentesi", "monitoraggio in gravidanza"]
    },
    "odontoiatria": {
        "title": "Odontoiatria",
        "desc": "Pulizia, otturazioni, estrazioni, impianti, protesi",
        "queries": ["igiene dentale e pulizia denti", "otturazione e cura carie", "estrazione dente",
                     "impianto dentale", "corona e protesi dentale", "ortodonzia e apparecchio", "devitalizzazione"]
    },
    "diagnostica": {
        "title": "Diagnostica per Immagini",
        "desc": "Ecografie, RMN, TAC, radiografie",
        "queries": ["ecografia", "risonanza magnetica RMN", "TAC tomografia computerizzata",
                     "radiografia", "mammografia", "densitometria ossea MOC"]
    },
    "prevenzione": {
        "title": "Prevenzione",
        "desc": "Screening, check-up, vaccinazioni",
        "queries": ["prevenzione e screening", "mammografia", "pap test", "analisi del sangue check-up"]
    },
    "psicologia": {
        "title": "Psicologia",
        "desc": "Psicoterapia, visite psichiatriche",
        "queries": ["psicoterapia seduta", "visita psichiatrica"]
    },
    "fisioterapia": {
        "title": "Fisioterapia",
        "desc": "Terapie fisiche, riabilitazione, osteopatia",
        "queries": ["fisioterapia", "riabilitazione", "osteopatia chiropratica",
                     "tecarterapia", "laserterapia", "onde d'urto"]
    }
}


# ─── State management ────────────────────────────────────────────────────────
if "active_query" not in st.session_state:
    st.session_state.active_query = None
if "search_key" not in st.session_state:
    st.session_state.search_key = 0

def set_query(q):
    st.session_state.active_query = q

def clear_query():
    st.session_state.active_query = None
    st.session_state.pop("active_theme", None)
    st.session_state.search_key += 1


# ─── Ricerca ─────────────────────────────────────────────────────────────────
search_input = st.text_input(
    "Cerca una prestazione",
    placeholder="Es: ecografia addome, visita oculistica, risonanza magnetica ginocchio...",
    key=f"srch_{st.session_state.search_key}",
)

if search_input:
    st.session_state.active_query = search_input

active_query = st.session_state.active_query


# ─── Se non c'è query: mostra percorsi tematici ─────────────────────────────
if not active_query:
    st.markdown("**Oppure esplora per tema:**")
    cols = st.columns(3)
    for i, (key, theme) in enumerate(THEMATIC_PATHS.items()):
        with cols[i % 3]:
            if st.button(theme["title"], key=f"theme_{key}", use_container_width=True,
                         help=theme["desc"]):
                st.session_state.active_theme = key
                st.rerun()

    # Se un tema è stato selezionato, mostra le sotto-voci
    if "active_theme" in st.session_state and st.session_state.active_theme:
        theme = THEMATIC_PATHS[st.session_state.active_theme]
        st.markdown(f"### {theme['title']}")
        st.caption(theme["desc"])

        if st.button("← Torna indietro"):
            st.session_state.active_theme = None
            st.rerun()

        for tq in theme["queries"]:
            if st.button(f"→  {tq}", key=f"tq_{tq}", use_container_width=True):
                st.session_state.active_query = tq
                st.session_state.active_theme = None
                st.rerun()

    st.stop()


# ─── Bottone per tornare alla home ───────────────────────────────────────────
st.markdown("---")
col_back, col_spacer = st.columns([1, 3])
with col_back:
    if st.button("← Nuova ricerca", use_container_width=True):
        clear_query()
        st.rerun()


# ─── Esegui ricerca ──────────────────────────────────────────────────────────
index = indices[sel_id]
relevant = find_relevant_sections(index, active_query, max_sections=5)

if not relevant:
    st.info(f"Nessuna sezione trovata per \"{active_query}\". Prova con un altro termine.")
    st.stop()

with st.spinner("Analisi in corso..."):
    result = analyze_query(active_query, relevant, api_key)


# ─── Non trovato ─────────────────────────────────────────────────────────────
if not result.get("found", False):
    st.markdown(f"**Nessun risultato** per \"{active_query}\"")
    reason = result.get("reason", "")
    if reason:
        st.caption(reason)
    suggestions = result.get("suggestions", [])
    if suggestions:
        st.markdown("**Prova con:**")
        for s in suggestions:
            if st.button(f"→  {s}", key=f"sug_{s}"):
                set_query(s)
                st.rerun()
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
#  RISULTATO
# ═══════════════════════════════════════════════════════════════════════════════

proc_name = result.get("procedure_name", active_query)
reimb = result.get("reimbursement", {})
rx = result.get("prescription", {})
limit = result.get("annual_limit", {})

st.markdown(f'<div class="result-card"><h2>{proc_name}</h2>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitle">Contesto: {result.get("context", "ambulatoriale")}</div>', unsafe_allow_html=True)

# ── Griglia dati ─────────────────────────────────────────────────────────
reimb_display = reimb.get("display", "Da verificare")
reimb_notes = reimb.get("notes", "")
reimb_type = reimb.get("type", "")

limit_display = "Nessun limite specificato"
if limit.get("detail"):
    limit_display = limit["detail"]
elif limit.get("max_per_year"):
    limit_display = f"{limit['max_per_year']} per anno civile"

rx_display = "Non specificato"
if rx.get("required") is True:
    rx_display = rx.get("detail", "Sì, necessaria")
elif rx.get("required") is False:
    rx_display = "Non richiesta"

grid = '<div class="data-grid">'
grid += f'<div class="data-row"><div class="data-label">Rimborso</div><div class="data-value"><strong>{reimb_display}</strong></div></div>'
if reimb_type:
    grid += f'<div class="data-row"><div class="data-label">Tipo</div><div class="data-value">{reimb_type}</div></div>'
if reimb_notes:
    grid += f'<div class="data-row"><div class="data-label">Note importo</div><div class="data-value">{reimb_notes}</div></div>'
grid += f'<div class="data-row"><div class="data-label">Limite annuale</div><div class="data-value">{limit_display}</div></div>'
grid += f'<div class="data-row"><div class="data-label">Prescrizione</div><div class="data-value">{rx_display}</div></div>'
grid += '</div>'
st.markdown(grid, unsafe_allow_html=True)

# ── Documenti ────────────────────────────────────────────────────────────
docs = result.get("required_documents", [])
if docs:
    st.markdown('<div class="section-title">Documenti per il rimborso</div>', unsafe_allow_html=True)
    html = '<ul class="doc-list">' + ''.join(f'<li>{d}</li>' for d in docs) + '</ul>'
    st.markdown(html, unsafe_allow_html=True)

# ── Limitazioni ──────────────────────────────────────────────────────────
lims = result.get("limitations", [])
if lims:
    st.markdown('<div class="section-title">Limitazioni</div>', unsafe_allow_html=True)
    html = '<ul class="lim-list">' + ''.join(f'<li>{l}</li>' for l in lims) + '</ul>'
    st.markdown(html, unsafe_allow_html=True)

# ── Copertura ────────────────────────────────────────────────────────────
cov = result.get("coverage", {})
if cov and cov.get("who"):
    st.markdown('<div class="section-title">Copertura</div>', unsafe_allow_html=True)
    st.markdown(f"{cov['who']}")
    if cov.get("geographic"):
        st.caption(f"Validità: {cov['geographic']}")

# ── Disposizioni particolari ─────────────────────────────────────────────
rules = result.get("section_rules_summary", "")
notes = result.get("important_notes", [])
if rules or notes:
    st.markdown('<div class="section-title">Disposizioni particolari</div>', unsafe_allow_html=True)
    parts = []
    if rules:
        parts.append(rules)
    if notes:
        parts.append("<br>".join(f"• {n}" for n in notes))
    st.markdown(f'<div class="notes-block">{"<br><br>".join(parts)}</div>', unsafe_allow_html=True)

# ── Come ottenere il rimborso ────────────────────────────────────────────
guide = result.get("reimbursement_guide", {})
if guide and guide.get("steps"):
    st.markdown('<div class="section-title">Come ottenere il rimborso</div>', unsafe_allow_html=True)

    # Steps
    steps_html = '<ul class="doc-list">'
    for step in guide["steps"]:
        steps_html += f'<li>{step}</li>'
    steps_html += '</ul>'
    st.markdown(steps_html, unsafe_allow_html=True)

    # Info compatte
    info_parts = []
    if guide.get("forms_needed"):
        info_parts.append(f"<strong>Moduli:</strong> {', '.join(guide['forms_needed'])}")
    if guide.get("send_to"):
        info_parts.append(f"<strong>Dove presentare:</strong> {guide['send_to']}")
    if guide.get("deadline"):
        info_parts.append(f"<strong>Scadenza:</strong> {guide['deadline']}")
    if guide.get("minimum_amount"):
        info_parts.append(f"<strong>Importo minimo pratica:</strong> {guide['minimum_amount']}")
    if guide.get("deduction"):
        info_parts.append(f"<strong>Detrazione:</strong> {guide['deduction']}")
    if guide.get("verification_needed"):
        info_parts.append(f"<strong>Verifica professionista:</strong> {guide['verification_needed']}")

    if info_parts:
        st.markdown(f'<div class="notes-block">{"<br>".join(info_parts)}</div>', unsafe_allow_html=True)

    # Link moduli
    links = guide.get("forms_links", {})
    if links:
        for form_name, url in links.items():
            st.markdown(f"[📄 Scarica modulo {form_name}]({url})")

    # Regole speciali
    special = guide.get("special_rules", [])
    if special:
        lims_html = '<ul class="lim-list">'
        for r in special:
            lims_html += f'<li>{r}</li>'
        lims_html += '</ul>'
        st.markdown(lims_html, unsafe_allow_html=True)

# ── Contesto ─────────────────────────────────────────────────────────────
ctx_note = result.get("context_note", "")
deg_note = result.get("degenza_note", "")
if ctx_note or deg_note:
    text = " ".join(filter(None, [ctx_note, deg_note]))
    st.markdown(f'<div class="ctx-bar">{text}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ── Prestazioni correlate (cliccabili) ───────────────────────────────────
related = result.get("related_procedures", [])
if related:
    st.markdown("---")
    st.markdown("**Prestazioni correlate**")
    for r in related:
        name = r.get("name", "")
        reimb_r = r.get("reimbursement", "")
        label = f"{name}  —  {reimb_r}" if reimb_r else name
        if st.button(f"→  {label}", key=f"rel_{name}_{hash(str(r))}"):
            set_query(name)
            st.rerun()

# ── Footer ───────────────────────────────────────────────────────────────
st.markdown("---")
col_b2, col_s2 = st.columns([1, 3])
with col_b2:
    if st.button("← Nuova ricerca ", use_container_width=True):  # space to make unique key
        clear_query()
        st.rerun()
st.caption("Le informazioni sono generate da AI sulla base del tariffario ufficiale. Per conferme contattare la propria assicurazione.")
