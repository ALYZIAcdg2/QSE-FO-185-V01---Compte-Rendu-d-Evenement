from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pyppeteer import launch
import uvicorn

app = FastAPI()

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

async def generer_pdf(data: CompteRendu):
    path = f"CRE_{data.escale}.pdf"
    # 1. On ajoute la langue FR dans les arguments de lancement
    browser = await launch(args=[
        '--no-sandbox', 
        '--lang=fr-FR'
    ])
    page = await browser.newPage()
    
    # 2. On force la locale de la page en français
    await page.setExtraHTTPHeaders({'Accept-Language': 'fr-FR'})
    
    await page.goto('http://localhost:10000', {'waitUntil': 'networkidle0'})
    
    # Injection des données
    await page.evaluate(f"""(d) => {{
        const setV = (id, v) => {{ 
            const el = document.getElementById(id);
            if(el) {{
                el.value = v;
                // Forcer le rafraîchissement pour les champs de type 'time'
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }};
        const setT = (id, v) => {{ if(document.getElementById(id)) document.getElementById(id).innerText = v; }};
        const setC = (id, v) => {{ if(document.getElementById(id)) document.getElementById(id).checked = v; }};

        setV('date_cr', d.date_cr);
        setV('heure_locale', d.heure_locale); // L'heure injectée ici sera au format 24h
        // ... reste de vos injections
    }}""", data.model_dump())
    
    await page.pdf({
        'path': path, 
        'format': 'A4', 
        'printBackground': True, 
        'preferCSSPageSize': True
    })
    await browser.close()
    return path

@app.post("/submit")
async def submit(data: CompteRendu):
    p = await generer_pdf(data)
    return FileResponse(p)

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)