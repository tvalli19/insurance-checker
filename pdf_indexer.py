"""
📄 Indicizzatore PDF per tariffari assicurativi.
Estrae il testo, lo spezza in sezioni, e permette ricerche rapide
per trovare i chunk rilevanti da mandare a Claude.
"""

import json
import re
import hashlib
from pathlib import Path


def extract_and_index(pdf_path: str, skip_pages: int = 5) -> dict:
    """
    Estrae testo dal PDF e lo indicizza in sezioni.
    Ritorna un dizionario con metadati e lista di sezioni.
    """
    import pdfplumber

    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i < skip_pages:
                continue
            t = page.extract_text()
            if t:
                pages_text.append(t)

    full_text = '\n\n'.join(pages_text)

    # Spezza in sezioni logiche
    sections = _split_into_sections(full_text)

    # Calcola hash per cache
    file_hash = hashlib.md5(full_text[:10000].encode()).hexdigest()[:12]

    return {
        "file_hash": file_hash,
        "total_chars": len(full_text),
        "total_sections": len(sections),
        "full_text": full_text,
        "sections": sections
    }


def _split_into_sections(text: str) -> list:
    """Spezza il testo in sezioni logiche basandosi sulle intestazioni."""
    patterns = [
        (r'^(Sezione\s+\d+\.\d+)\s+(.+?)$', 'section'),
        (r'^(SEZIONE\s+\d+)\s+(.+?)$', 'major'),
        (r'^(ALLEGATO\s+\d+)\s+(.+?)$', 'allegato'),
        (r'^(\d{2}\s*[–-]\s*.+)$', 'numbered'),
    ]

    # Sotto-intestazioni dentro allegati (branche mediche)
    branch_patterns = [
        r'^(Analisi cliniche)\s*$',
        r'^(Angiografia)\s*$',
        r'^(Ecografia)\s*$',
        r'^(Radiodiagnostica[^$]*)\s*$',
        r'^(Tomografia computerizzata[^$]*)\s*$',
        r'^(Risonanza[^$]*)\s*$',
        r'^(Termografia)\s*$',
        r'^(Allergologia)\s*$',
        r'^(Angiologia)\s*$',
        r'^(Cardiologia)\s*$',
        r'^(Dermatologia)\s*$',
        r'^(Fisiatria)\s*$',
        r'^(Gastroenterologia)\s*$',
        r'^(Geriatria)\s*$',
        r'^(Ginecologia[^$]*)\s*$',
        r'^(Neurologia)\s*$',
        r'^(Oculistica)\s*$',
        r'^(Ortopedia)\s*$',
        r'^(Otorinolaringoiatria)\s*$',
        r'^(Pneumologia)\s*$',
        r'^(Urologia)\s*$',
        r'^(Radiologia)\s*$',
        r'^(Conservativa ed Endodonzia)\s*$',
        r'^(Chirurgia Orale)\s*$',
        r'^(Parodontologia)\s*$',
        r'^(Protesi)\s*$',
        r'^(Implantologia)\s*$',
        r'^(Ortodonzia[^$]*)\s*$',
    ]

    lines = text.split('\n')
    headers = []

    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) < 3:
            continue

        # Pattern principali
        for pat, htype in patterns:
            if re.match(pat, s):
                headers.append({'line': i, 'title': s, 'type': htype})
                break
        else:
            # Pattern branche mediche
            for bp in branch_patterns:
                if re.match(bp, s, re.IGNORECASE):
                    headers.append({'line': i, 'title': s, 'type': 'branch'})
                    break

    # Costruisci sezioni
    sections = []
    for idx, h in enumerate(headers):
        start = h['line']
        end = headers[idx + 1]['line'] if idx + 1 < len(headers) else len(lines)
        chunk = '\n'.join(lines[start:end]).strip()

        if len(chunk) < 30:
            continue

        # Determina contesto
        title_lower = h['title'].lower()
        if any(k in title_lower for k in ['sezione 1.', 'sezione 2.', 'sezione 3.', 'sezione 4.', 'sezione 5.',
                                            'sezione 1 ', 'sezione 2 ', 'sezione 3 ', 'sezione 4 ', 'sezione 5 ']):
            context = "degenza"
        elif 'allegato 1' in title_lower:
            context = "degenza"
        else:
            context = "ambulatoriale"

        sections.append({
            "title": h['title'],
            "context": context,
            "text": chunk,
            "char_count": len(chunk),
            "has_table": bool(re.search(r'(?:CODICE.*DESCRIZIONE|OD/\d)', chunk)),
            "has_rules": bool(re.search(r'DISPOSIZIONI PARTICOLARI|PREMESSE', chunk, re.IGNORECASE)),
            # Parole chiave per ricerca
            "keywords": _extract_keywords(chunk)
        })

    return sections


def _extract_keywords(text: str) -> list:
    """Estrae parole chiave dal testo per la ricerca."""
    text_lower = text.lower()
    keywords = set()

    # Estrai nomi dalle righe CODICE/DESCRIZIONE
    for line in text.split('\n'):
        line = line.strip()
        # Righe tabellari con codice
        m = re.match(r'^[A-Z]{2}\s+[A-Z]{2}\s+N\d+\s+(.+?)(?:\d+[.,]\d{2}|$)', line)
        if m:
            desc = m.group(1).strip().lower()
            keywords.update(w for w in desc.split() if len(w) > 3)
        # Righe odontoiatria
        m = re.match(r'^OD/\d+\s+(.+?)(?:\d+[.,]\d{2}|$)', line)
        if m:
            desc = m.group(1).strip().lower()
            keywords.update(w for w in desc.split() if len(w) > 3)

    # Aggiungi parole dal titolo
    for w in text.split('\n')[0].lower().split():
        if len(w) > 3:
            keywords.add(w)

    return list(keywords)[:50]  # Limita


def find_relevant_sections(index: dict, query: str, max_sections: int = 3) -> list:
    """
    Trova le sezioni più rilevanti per una query del paziente.
    Ottimizzato per costo: manda massimo 3 sezioni, tronca quelle troppo lunghe.
    """
    MAX_SECTION_CHARS = 8000  # Tronca sezioni oltre questa soglia

    query_lower = query.lower().strip()
    query_words = set(query_lower.split())

    # Sinonimi comuni per espandere la query
    # Chiave = quello che il paziente potrebbe cercare
    # Valori = termini che appaiono nei titoli/keywords delle sezioni dell'indice
    synonyms = {
        # Visite specialistiche — il paziente cerca lo specialista, il tariffario ha la branca
        "oculista": ["oculistica", "occhio", "vista", "oftalmologia"],
        "visita oculistica": ["oculistica", "occhio", "vista", "visite mediche"],
        "dentista": ["odontoiatri", "endodonzia", "conservativa", "implantologia", "protesi", "ortodonzia", "parodontologia", "chirurgia orale"],
        "cardiologo": ["cardiologia", "cuore", "ecg", "elettrocardiogramma", "visite mediche"],
        "visita cardiologica": ["cardiologia", "visite mediche", "cuore"],
        "dermatologo": ["dermatologia", "pelle", "cute"],
        "ortopedico": ["ortopedia", "ossa", "muscol", "articol"],
        "ginecologo": ["ginecologia", "ostetricia", "gravidanza", "parto"],
        "urologo": ["urologia"],
        "neurologo": ["neurologia"],
        "gastroenterologo": ["gastroenterologia"],
        "pneumologo": ["pneumologia"],
        "otorinolaringoiatra": ["otorinolaringoiatria", "otorino"],
        "otorino": ["otorinolaringoiatria"],
        "allergologo": ["allergologia"],
        "visita specialistica": ["visite mediche", "ambulatoriali"],
        "visita medica": ["visite mediche", "ambulatoriali"],

        # Psicologia — il paziente cerca "psicologo", il tariffario dice "psicoterapie"
        "psicologo": ["psicoterapie", "psicoterapeutica", "psicoterapia"],
        "psicoterapia": ["psicoterapie", "psicoterapeutica"],
        "psichiatra": ["psichiatrica", "neuropsichiatrica", "visite mediche"],

        # Fisioterapia
        "fisioterapia": ["fisiche", "riabilitative", "riabilitazione", "fisiokinesiterapia", "fkt", "ambulatoriali"],
        "fisioterapista": ["fisiche", "riabilitative", "riabilitazione"],
        "osteopatia": ["osteopati", "chiropratici", "chiroterapisti"],
        "chiropratica": ["chiropratici", "chiroterapisti", "osteopati"],
        "riabilitazione": ["riabilitative", "fisiche", "terapie"],
        "massaggio": ["massoterapia", "fisiche", "riabilitative"],

        # Diagnostica per immagini
        "ecografia": ["ecografi", "ultrasuoni", "eco", "diagnostica"],
        "eco": ["ecografi", "ecografia"],
        "risonanza": ["risonanza", "magnetica", "rmn", "rm"],
        "rmn": ["risonanza", "magnetica"],
        "tac": ["tomografia", "computerizzata"],
        "radiografia": ["radiodiagnostica", "raggi", "rx", "radiologia"],
        "raggi x": ["radiodiagnostica", "radiografia", "rx"],
        "mammografia": ["mammella", "seno", "screening"],
        "moc": ["densitometria", "mineralometria", "ossea"],
        "densitometria": ["mineralometria", "densitometria", "ossea"],

        # Analisi — il paziente cerca "esame sangue", il tariffario ha "analisi cliniche"
        "analisi": ["laboratorio", "cliniche", "sangue", "emocromo"],
        "esame sangue": ["analisi", "cliniche", "laboratorio", "sangue"],
        "esami sangue": ["analisi", "cliniche", "laboratorio", "sangue"],
        "analisi sangue": ["analisi", "cliniche", "laboratorio"],
        "transaminasi": ["analisi", "cliniche", "laboratorio", "sangue"],
        "emocromo": ["analisi", "cliniche", "laboratorio", "sangue"],
        "colesterolo": ["analisi", "cliniche", "laboratorio", "sangue"],
        "glicemia": ["analisi", "cliniche", "laboratorio", "sangue"],
        "esame urine": ["analisi", "cliniche", "laboratorio"],

        # Odontoiatria — mappature specifiche
        "pulizia denti": ["parodontologia", "igiene", "ablazione", "tartaro", "odontoiatri"],
        "igiene dentale": ["parodontologia", "igiene", "ablazione", "tartaro", "odontoiatri"],
        "otturazione": ["conservativa", "carie", "endodonzia", "odontoiatri"],
        "carie": ["conservativa", "endodonzia", "odontoiatri"],
        "estrazione": ["chirurgia orale", "avulsione", "odontoiatri"],
        "estrazione dente": ["chirurgia orale", "avulsione", "odontoiatri"],
        "devitalizzazione": ["endodonzia", "conservativa", "odontoiatri"],
        "impianto": ["implantologia", "odontoiatri"],
        "impianto dentale": ["implantologia", "odontoiatri"],
        "corona": ["protesi", "capsula", "odontoiatri"],
        "corona dentale": ["protesi", "odontoiatri"],
        "apparecchio": ["ortodonzia", "gnatologia", "odontoiatri"],
        "apparecchio ortodontico": ["ortodonzia", "gnatologia"],
        "protesi dentale": ["protesi", "odontoiatri"],
        "ponte dentale": ["protesi", "bridge", "odontoiatri"],

        # Ricovero e chirurgia
        "ricovero": ["degenza", "ospedalier", "ricoveri", "assistenza"],
        "chirurgia": ["chirurgic", "interventi", "operazione"],
        "intervento": ["chirurgic", "interventi", "operazione"],
        "day hospital": ["degenza", "day hospital", "day surgery"],

        # Gravidanza
        "gravidanza": ["ginecologia", "ostetricia", "parto", "ostetric"],
        "parto": ["ostetricia", "ginecologia", "ostetric"],
        "ecografia gravidanza": ["ginecologia", "ostetricia", "ecografia"],

        # Varie
        "farmaci": ["farmaco", "farmaceutic"],
        "lenti": ["vista", "occhiali", "correttive"],
        "occhiali": ["lenti", "vista", "correttive"],
        "apparecchio acustico": ["acustico", "protesi acustica", "udito"],
        "prevenzione": ["prevenzione", "screening"],
        "ticket": ["compartecipazione", "ssn"],
        "trasporto": ["autoambulanza", "trasporto"],
        "funerarie": ["funerarie", "spese"],
    }

    # Espandi query con sinonimi
    expanded = set(query_words)
    for key, syns in synonyms.items():
        if key in query_lower or any(w in query_lower for w in key.split()):
            expanded.update(syns)

    scored = []
    for section in index["sections"]:
        score = 0
        title_lower = section["title"].lower()
        kws = set(section.get("keywords", []))

        # Match sul titolo (peso alto) — usa substring matching
        for w in expanded:
            if len(w) >= 4 and w in title_lower:
                score += 15
            elif len(w) >= 4 and any(w[:4] in t for t in title_lower.split()):
                score += 10  # match parziale (es. "psicoterapia" matcha "psicoterapie")

        # Match sulle keywords (peso medio)
        for w in expanded:
            if len(w) >= 4:
                if w in kws or any(w[:4] in k for k in kws):
                    score += 3

        # Match nel testo solo se già c'è un match minimo (evita sezioni enormi irrilevanti)
        if score > 0:
            text_sample = section["text"][:2000].lower()
            text_matches = sum(1 for w in expanded if len(w) >= 4 and w in text_sample)
            score += text_matches * 1

        if score > 0:
            scored.append((score, section))

    # Ordina per score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Prendi i migliori, tronca testo se troppo lungo
    results = []
    for _, section in scored[:max_sections]:
        s = dict(section)  # copia
        if len(s["text"]) > MAX_SECTION_CHARS:
            s["text"] = s["text"][:MAX_SECTION_CHARS] + "\n\n[...sezione troncata per lunghezza...]"
            s["char_count"] = MAX_SECTION_CHARS
        results.append(s)

    return results


def save_index(index: dict, output_path: str):
    """Salva l'indice su disco (senza full_text per risparmiare spazio)."""
    to_save = {k: v for k, v in index.items() if k != "full_text"}
    Path(output_path).write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")


def load_index(path: str) -> dict:
    """Carica un indice salvato."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
