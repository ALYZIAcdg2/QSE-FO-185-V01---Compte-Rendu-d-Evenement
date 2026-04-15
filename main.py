import os
import base64
import httpx
import asyncio
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pyppeteer import launch
import uvicorn

app = FastAPI()

# --- MODÈLE DE DONNÉES ---
class CompteRendu(BaseModel):
    date_cr: str; entite: str; escale: str
    retard: bool; reclam_cie: bool; impact_secu: bool; dysfonc: bool
    compagnie: str; num_vol: str; immat: str; date_evenement: str
    heure_locale: str; lieu: str; jour_nuit: str; meteo: str
    desc_succincte: str; desc_detaillee: str
    sig_redacteur_nom: str; sig_redacteur_box: str
    analyse_encadrement: str; diff_qse: bool; diff_cie: bool; diff_aeroport: bool
    sig_encadre_nom: str; sig_encadre_box: str
    analyse_qse_text: str; cl_ev: bool; cl_inc: bool; cl_inc_g: bool; cl_acc: bool
    st_clos_s: bool; st_ouvert: bool; st_clos_d: bool
    dsac: bool; bea: bool; nav_air: bool; autre: bool
    sig_qse_nom: str; sig_qse_box: str

# --- FONCTION D'ENVOI VIA SENDGRID ---
async def envoyer_email_sendgrid(fichier_path, data):
    API_KEY = os.environ.get("SENDGRID_API_KEY")
    if not API_KEY:
        print("Erreur : SENDGRID_API_KEY manquante sur Render.")
        return False

    with open(fichier_path, "rb") as f:
        encoded_pdf = base64.b64encode(f.read()).decode()

    # Liste des destinataires (facile à modifier plus tard)
    destinataires = [
        {"email": "xavier.oliere@alyzia.com"}
    ]

    payload = {
        "personalizations": [{"to": destinataires}],
        "from": {"email": "alyzia.cdg2@gmail.com", "name": "CRE- ALYZIA"},
        "subject": f"CRE ALYZIA - {data.escale.upper()} - {data.compagnie.upper()}",
        "content": [{"type": "text/plain", "value": f"Nouveau CRE rédigé par {data.sig_redacteur_nom}."}],
        "attachments": [{
            "content": encoded_pdf,
            "filename": os.path.basename(fichier_path),
            "type": "application/pdf",
            "disposition": "attachment"
        }]
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        )
        return r.status_code < 400

# --- GÉNÉRATION DU PDF AVEC INJECTION ---
async def generer_pdf_cre(data: CompteRendu):
    fichier = f"CRE_{data.escale}.pdf"
    data_json = data.model_dump_json()
    
    # Lancement du navigateur (force la langue FR pour les dates/heures)
    browser = await launch(args=['--no-sandbox', '--disable-setuid-sandbox', '--lang=fr-FR'])
    try:
        page = await browser.newPage()
        await page.setExtraHTTPHeaders({'Accept-Language': 'fr-FR'})
        
        # URL locale de Render (port 10000)
        await page.goto('http://localhost:10000', {'waitUntil': 'networkidle0', 'timeout': 60000})
        
        # Injection des données et correctif visuel pour l'heure
        await page.evaluate(f"""(d_str) => {{
            const d = JSON.parse(d_str);

            // Correctif pour que l'heure ne soit pas coupée (supprime l'icône horloge native)
            const style = document.createElement('style');
            style.innerHTML = `
                input[type="time"]::-webkit-calendar-picker-indicator {{ display: none !important; }}
                input[type="time"] {{ width: 100% !important; border: none !important; font-size: 10pt !important; padding: 0 !important; }}
            `;
            document.head.appendChild(style);

            const setV = (id, v) => {{ 
                const el = document.getElementById(id);
                if(el) {{ 
                    el.value = v; 
                    el.dispatchEvent(new Event('input', {{ bubbles: true }})); 
                }} 
            }};
            const setC = (id, v) => {{ 
                const el = document.getElementById(id);
                if(el) {{ el.checked = v; el.dispatchEvent(new Event('change', {{ bubbles: true }})); }} 
            }};
            const setT = (id, v) => {{ 
                const el = document.getElementById(id);
                if(el) {{ el.innerText = v; }} 
            }};

            // Remplissage des champs texte/date
            setV('date_cr', d.date_cr);
            setV('entite', d.entite);
            setV('escale', d.escale);
            setV('compagnie', d.compagnie);
            setV('num_vol', d.num_vol);
            setV('immat', d.immat);
            setV('date_evenement', d.date_evenement);
            setV('heure_locale', d.heure_locale);
            setV('lieu', d.lieu);
            setV('jour_nuit', d.jour_nuit);
            setV('meteo', d.meteo);
            setV('desc_succincte', d.desc_succincte);
            setV('desc_detaillee', d.desc_detaillee);
            setV('sig_redacteur_nom', d.sig_redacteur_nom);
            setT('sig_redacteur_box', d.sig_redacteur_box);
            
            // Remplissage des cases à cocher
            setC('retard', d.retard);
            setC('reclam_cie', d.reclam_cie);
            setC('impact_secu', d.impact_secu);
            setC('dysfonc', d.dysfonc);
            
            // Partie Analyse et signatures
            setV('analyse_encadrement', d.analyse_encadrement);
            setV('sig_encadre_nom', d.sig_encadre_nom);
            setT('sig_encadre_box', d.sig_encadre_box);
            setV('analyse_qse_text', d.analyse_qse_text);
            setC('cl_ev', d.cl_ev); setC('cl_inc', d.cl_inc); setC('cl_inc_g', d.cl_inc_g); setC('cl_acc', d.cl_acc);
            setC('st_clos_s', d.st_clos_s); setC('st_ouvert', d.st_ouvert); setC('st_clos_d', d.st_clos_d);
            setV('sig_qse_nom', d.sig_qse_nom); setT('sig_qse_box', d.sig_qse_box);
        }}""", data_json)

        # Attente pour s'assurer que le rendu est fini
        await asyncio.sleep(1)

        await page.pdf({
            'path': fichier,
            'format': 'A4',
            'printBackground': True,
            'margin': {'top': '0px', 'right': '0px', 'bottom': '0px', 'left': '0px'}
        })
    finally:
        await browser.close()
    return fichier

# --- ROUTES API ---
@app.post("/submit")
async def submit(data: CompteRendu, action: str = Query("pdf")):
    pdf_path = await generer_pdf_cre(data)
    
    if action == "email":
        success = await envoyer_email_sendgrid(pdf_path, data)
        if os.path.exists(pdf_path):
            os.remove(pdf_path) # Supprime le fichier après envoi
        if success:
            return {"status": "success"}
        else:
            return JSONResponse(status_code=500, content={"status": "error"})

    return FileResponse(pdf_path)

# Montage des fichiers statiques (HTML, CSS, JS)
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)