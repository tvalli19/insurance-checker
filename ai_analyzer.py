"""
🤖 Analizzatore AI — con guide rimborso FASDAC integrate.
"""

import json
import re
import urllib.request
import urllib.error
from pathlib import Path

ANALYSIS_PROMPT = """\
Sei un consulente FASDAC. Un paziente chiede di una prestazione. Analizza il testo del tariffario fornito e rispondi in JSON.

REGOLE:
- Sez 1-5 = degenza. Sez 6 + Allegati 2-4 = ambulatoriale. ASSUMI ambulatoriale se non specificato.
- Cerca nella colonna DESCRIZIONE delle tabelle CODICE|DESCRIZIONE|RIMBORSO. Il paziente può usare abbreviazioni o termini parziali.
- Leggi TUTTE le PREMESSE e DISPOSIZIONI PARTICOLARI — contengono documenti, limiti annuali, esclusioni, chi eroga.
- Rimborso diretto = struttura convenzionata, l'assicurazione paga. Indiretto = paziente anticipa e chiede rimborso.
- Massimale = max rimborsabile. Franchigia = quota fissa a carico paziente. Scoperto = % a carico paziente.
- Se trovi più prestazioni correlate, elencale in related_procedures.
- NON inventare dati. Importi ESATTI dal tariffario. Se manca un dato, usa null.
- Se fornite le GUIDE RIMBORSO, usa quelle info per compilare la sezione "reimbursement_guide" con i passi pratici per ottenere il rimborso (moduli, documenti, scadenze, dove presentare).

RISPONDI SOLO con JSON valido:
{
  "found": true,
  "procedure_name": "nome esatto dal tariffario",
  "context": "ambulatoriale",
  "context_note": "nota sul contesto degenza se rilevante",
  "reimbursement": {"display": "€ X" o "X% della spesa", "amount": numero|null, "percentage": "X%"|null, "type": "tipo rimborso", "notes": "note importo"},
  "prescription": {"required": true|false|null, "detail": "tipo prescrizione"},
  "annual_limit": {"max_per_year": numero|null, "detail": "dettaglio testuale"},
  "coverage": {"who": "chi è coperto", "employee": true, "spouse": true, "children": true, "geographic": "dove"},
  "required_documents": ["doc1", "doc2"],
  "limitations": ["limitazione1"],
  "section_rules_summary": "sintesi disposizioni particolari rilevanti",
  "important_notes": ["nota1"],
  "related_procedures": [{"name": "nome", "code": "codice", "reimbursement": "€ X"}],
  "degenza_note": "nota se esiste in contesto degenza",
  "reimbursement_guide": {
    "practice_type": "odontoiatrica|medica|ticket",
    "forms_needed": ["P01/D", "P01/M", etc],
    "forms_links": {"P01/D": "https://...", etc},
    "steps": ["Passo 1: ...", "Passo 2: ...", "etc"],
    "send_to": "Associazione Territoriale Manageritalia",
    "deadline": "6 mesi dal primo documento di spesa",
    "minimum_amount": "€ 51,65",
    "deduction": "€ 51,65 detrazione fissa (se applicabile)",
    "special_rules": ["regola1", "regola2"],
    "verification_needed": "descrizione verifica professionista se necessaria"
  }
}

Se NON trovata: {"found": false, "reason": "perché", "suggestions": ["alternative"]}"""


def _load_guides() -> str:
    """Carica le guide rimborso FASDAC come testo compatto per il contesto."""
    guide_path = Path("data/fasdac_guide_rimborsi.json")
    if not guide_path.exists():
        return ""

    try:
        guides = json.loads(guide_path.read_text(encoding="utf-8"))
        # Comprimi in formato leggibile ma compatto
        parts = []
        for g in guides:
            title = g.get("page_title", "")
            gtype = g.get("type", "")
            moduli = g.get("moduli_obbligatori", [])
            docs = g.get("documenti_obbligatori", [])
            soglia = g.get("soglia_ingresso_euro")
            detrazione = g.get("detrazione_fissa_euro")
            rimb_pct = g.get("rimborso_percentuale")
            regole = g.get("regole_speciali", [])
            links = g.get("link_utili", {})
            scadenza = g.get("scadenza_presentazione", {})
            verifica = g.get("verifica_professionista", {})

            part = f"GUIDA: {title} (tipo: {gtype})\n"
            part += f"  Moduli: {', '.join(moduli)}\n"
            part += f"  Documenti: {', '.join(docs)}\n"
            if soglia:
                part += f"  Soglia minima: € {soglia}\n"
            if detrazione:
                part += f"  Detrazione fissa: € {detrazione}\n"
            if rimb_pct:
                part += f"  Rimborso: {rimb_pct}%\n"
            if scadenza:
                if isinstance(scadenza, dict) and scadenza.get("valore"):
                    part += f"  Scadenza: {scadenza['valore']} {scadenza.get('tipo','')}\n"
            if verifica and verifica.get("albo"):
                part += f"  Verifica professionista: {verifica['albo']} ({verifica.get('link_verifica','')})\n"
            if regole:
                part += f"  Regole: {'; '.join(regole)}\n"
            if links:
                for lname, lurl in links.items():
                    part += f"  Link {lname}: {lurl}\n"

            # Semestri per ticket
            semestri = g.get("semestri", [])
            if semestri:
                for s in semestri:
                    part += f"  Semestre {s['periodo']}: spese {s['date_spesa']} → invio entro {s['scadenza_invio']}\n"

            # Documenti condizionali
            doc_cond = g.get("documenti_condizionali", {})
            if doc_cond:
                for cond, doc in doc_cond.items():
                    part += f"  Se {cond}: {doc}\n"

            parts.append(part)

        return "\n".join(parts)
    except Exception:
        return ""


def _determine_guide_type(query: str, sections: list) -> str:
    """Determina quale guida rimborso è rilevante per la query."""
    q = query.lower()
    for s in sections:
        t = s.get("title", "").lower()
        if any(k in t for k in ["odontoiatri", "conservativa", "chirurgia orale", "implantologia", "protesi", "ortodonzia", "parodontologia"]):
            return "odontoiatrica"
        if any(k in t for k in ["fisiche", "riabilitative"]):
            return "fisioterapia"
        if any(k in t for k in ["altre prestazioni sanitarie"]):
            return "professionisti_sanitari"
        if any(k in t for k in ["farmaci"]):
            return "farmaci"
        if any(k in t for k in ["ticket", "compartecipazione"]):
            return "ticket"
    # Fallback su query
    if any(k in q for k in ["dent", "ottur", "estraz", "impiant", "pulizia", "igiene", "ortodon"]):
        return "odontoiatrica"
    if any(k in q for k in ["fisio", "riabil", "osteo", "tecar"]):
        return "fisioterapia"
    if any(k in q for k in ["farmac", "omeopat"]):
        return "farmaci"
    if "ticket" in q:
        return "ticket"
    return "medica"


def analyze_query(query: str, relevant_sections: list, api_key: str,
                  model: str = "claude-sonnet-4-20250514") -> dict:

    # Costruisci contesto tariffario
    sections_text = ""
    for i, section in enumerate(relevant_sections):
        sections_text += f"\n\n===== {section['title']} ({section['context']}) =====\n"
        sections_text += section['text']

    # Aggiungi guida rimborso rilevante
    guides_text = _load_guides()
    guide_type = _determine_guide_type(query, relevant_sections)

    user_message = f'Prestazione cercata: "{query}"\n\nTariffario FASDAC:\n{sections_text}'

    if guides_text:
        user_message += f"\n\n===== GUIDE PRATICHE RIMBORSO FASDAC =====\n{guides_text}"
        user_message += f"\n\nLa prestazione cercata è di tipo: {guide_type}. Usa la guida corrispondente per compilare reimbursement_guide."

    if len(user_message) > 22000:
        user_message = user_message[:22000] + "\n[troncato]"

    payload = json.dumps({
        "model": model,
        "max_tokens": 2048,
        "system": ANALYSIS_PROMPT,
        "messages": [{"role": "user", "content": user_message}]
    })

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload.encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        return json.loads(text)

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')[:300] if e.fp else ""
        return {"found": False, "reason": f"Errore API: HTTP {e.code}", "error": body}
    except json.JSONDecodeError as e:
        return {"found": False, "reason": f"Errore nella risposta AI", "error": str(e)}
    except Exception as e:
        return {"found": False, "reason": f"Errore: {str(e)}"}
