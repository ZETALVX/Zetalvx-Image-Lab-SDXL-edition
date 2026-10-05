/* 0.1.0.26 — UI refinements, Italian/English; other locales fall back to English. */
(()=>{const additions=[
  {"sources":["SDXL generation model"],"text":{"en":"SDXL generation model","it":"Modello di generazione SDXL"}},
  {"sources":["InstantID generates through the selected SDXL checkpoint."],"text":{"en":"InstantID generates through the selected SDXL checkpoint.","it":"InstantID genera attraverso il checkpoint SDXL selezionato."}},
  {"sources":["SDXL refinement model"],"text":{"en":"SDXL refinement model","it":"Modello di rifinitura SDXL"}},
  {"sources":["This checkpoint is used only for the optional Img2Img refinement after the face swap."],"text":{"en":"This checkpoint is used only for the optional Img2Img refinement after the face swap.","it":"Questo checkpoint viene usato solo dalla rifinitura Img2Img opzionale dopo il Face Swap."}},
  {"sources":["Pure Face Swap uses InsightFace/ONNX and does not use an SDXL checkpoint. Enable the optional SDXL refine below only if you want an additional Img2Img finishing pass."],"text":{"en":"Pure Face Swap uses InsightFace/ONNX and does not use an SDXL checkpoint. Enable the optional SDXL refine below only if you want an additional Img2Img finishing pass.","it":"Il Face Swap puro usa InsightFace/ONNX e non usa alcun checkpoint SDXL. Attiva la rifinitura SDXL opzionale solo se vuoi un passaggio Img2Img finale aggiuntivo."}},
  {"sources":["Optional SDXL refinement after Face Swap"],"text":{"en":"Optional SDXL refinement after Face Swap","it":"Rifinitura SDXL opzionale dopo Face Swap"}},
  {"sources":["Off = pure Face Swap, no SDXL checkpoint is used. On = the swapped image receives a low-denoise Img2Img finishing pass using the checkpoint, LoRA and prompt below."],"text":{"en":"Off = pure Face Swap, no SDXL checkpoint is used. On = the swapped image receives a low-denoise Img2Img finishing pass using the checkpoint, LoRA and prompt below.","it":"Disattivato = Face Swap puro, nessun checkpoint SDXL viene usato. Attivato = l’immagine sostituita riceve una rifinitura Img2Img a basso denoise usando checkpoint, LoRA e prompt qui sotto."}},

  {"sources":["Download queue"],"text":{"en":"Download queue","it":"Coda download"}},
  {"sources":["Simultaneous downloads"],"text":{"en":"Simultaneous downloads","it":"Download simultanei"}},
  {"sources":["1 · Recommended"],"text":{"en":"1 · Recommended","it":"1 · Consigliato"}},
  {"sources":["One download at a time."],"text":{"en":"One download at a time.","it":"Un download alla volta."}},
  {"sources":["You can add Checkpoints, LoRAs, VAE, Vision GGUF/mmproj and Transformers repositories while other downloads are running. Extra jobs stay queued on the server."],"text":{"en":"You can add Checkpoints, LoRAs, VAE, Vision GGUF/mmproj and Transformers repositories while other downloads are running. Extra jobs stay queued on the server.","it":"Puoi aggiungere Checkpoint, LoRA, VAE, Vision GGUF/mmproj e repository Transformers mentre altri download sono in corso. I lavori aggiuntivi restano in coda sul server."}},
  {"sources":["Queue position"],"text":{"en":"Queue position","it":"Posizione coda"}},
  {"sources":["running"],"text":{"en":"running","it":"in corso"}},
  {"sources":["queued"],"text":{"en":"queued","it":"in coda"}},
  {"sources":["simultaneous"],"text":{"en":"simultaneous","it":"simultanei"}},
  {"sources":["Downloads","Download"],"text":{"en":"Downloads","it":"Download"}},
  {"sources":["Downloads continue on the server when you close the popup, change page or close the browser."],"text":{"en":"Downloads continue on the server when you close the popup, change page or close the browser.","it":"I download continuano sul server quando chiudi il popup, cambi pagina o chiudi il browser."}},
  {"sources":["All"],"text":{"en":"All","it":"Tutti"}},
  {"sources":["Active"],"text":{"en":"Active","it":"Attivi"}},
  {"sources":["Finished"],"text":{"en":"Finished","it":"Completati"}},
  {"sources":["Model downloads"],"text":{"en":"Model downloads","it":"Download modelli"}},
  {"sources":["Server-side jobs continue when the browser is closed."],"text":{"en":"Server-side jobs continue when the browser is closed.","it":"I lavori lato server continuano anche quando il browser viene chiuso."}},
  {"sources":["Open Download Manager"],"text":{"en":"Open Download Manager","it":"Apri Download Manager"}},
  {"sources":["You can close this window: the download continues on the server."],"text":{"en":"You can close this window: the download continues on the server.","it":"Puoi chiudere questa finestra: il download continua sul server."}},
  {"sources":["Log and verification"],"text":{"en":"Log and verification","it":"Registro e verifica"}},
  {"sources":["No downloads recorded."],"text":{"en":"No downloads recorded.","it":"Nessun download registrato."}},
  {"sources":["Cancel this download? The incomplete temporary file will be removed."],"text":{"en":"Cancel this download? The incomplete temporary file will be removed.","it":"Annullare questo download? Il file temporaneo incompleto verrà rimosso."}},
  {"sources":["Queued"],"text":{"en":"Queued","it":"In coda"}},
  {"sources":["Downloading"],"text":{"en":"Downloading","it":"Download"}},
  {"sources":["Validating"],"text":{"en":"Validating","it":"Verifica"}},
  {"sources":["Installing"],"text":{"en":"Installing","it":"Installazione"}},
  {"sources":["Cancelling…"],"text":{"en":"Cancelling…","it":"Annullamento…"}},
  {"sources":["Confirmation required"],"text":{"en":"Confirmation required","it":"Conferma necessaria"}},
  {"sources":["Complete"],"text":{"en":"Complete","it":"Completato"}},
  {"sources":["Failed"],"text":{"en":"Failed","it":"Errore"}},
  {"sources":["Cancelled"],"text":{"en":"Cancelled","it":"Annullato"}},
  {"sources":["Interrupted"],"text":{"en":"Interrupted","it":"Interrotto"}},
  {
    "sources": [
      "Main navigation",
      "Navigazione principale"
    ],
    "text": {
      "en": "Main navigation",
      "it": "Navigazione principale"
    }
  },
  {
    "sources": [
      "Video · frames",
      "Video · fotogrammi"
    ],
    "text": {
      "en": "Video · frames",
      "it": "Video · fotogrammi"
    }
  },
  {
    "sources": [
      "First, last or a selected time",
      "Primo, ultimo o un istante scelto"
    ],
    "text": {
      "en": "First, last or a selected time",
      "it": "Primo, ultimo o un istante scelto"
    }
  },
  {
    "sources": [
      "Upload once, choose in the player or enter a time. Save the exact PNG shown in the preview.",
      "Carica una volta, scegli dal player o inserisci un istante. Salva il PNG esatto mostrato nell’anteprima."
    ],
    "text": {
      "en": "Upload once, choose in the player or enter a time. Save the exact PNG shown in the preview.",
      "it": "Carica una volta, scegli dal player o inserisci un istante. Salva il PNG esatto mostrato nell’anteprima."
    }
  },
  {
    "sources": [
      "Choose video",
      "Scegli video"
    ],
    "text": {
      "en": "Choose video",
      "it": "Scegli video"
    }
  },
  {
    "sources": [
      "No file",
      "Nessun file"
    ],
    "text": {
      "en": "No file",
      "it": "Nessun file"
    }
  },
  {
    "sources": [
      "Load video",
      "Carica video"
    ],
    "text": {
      "en": "Load video",
      "it": "Carica video"
    }
  },
  {
    "sources": [
      "Limit: 120 MiB · 1 hour. Local FFmpeg processing on this server, no external services.",
      "Massimo 120 MiB · 1 ora. Elaborazione locale sul server con FFmpeg, senza servizi esterni."
    ],
    "text": {
      "en": "Limit: 120 MiB · 1 hour. Local FFmpeg processing on this server, no external services.",
      "it": "Massimo 120 MiB · 1 ora. Elaborazione locale sul server con FFmpeg, senza servizi esterni."
    }
  },
  {
    "sources": [
      "Video player",
      "Player video"
    ],
    "text": {
      "en": "Video player",
      "it": "Player video"
    }
  },
  {
    "sources": [
      "This browser cannot play this format. You can still select a time and preview frames with FFmpeg.",
      "Il browser non riproduce questo formato. Puoi comunque scegliere l’istante e vedere i fotogrammi tramite FFmpeg."
    ],
    "text": {
      "en": "This browser cannot play this format. You can still select a time and preview frames with FFmpeg.",
      "it": "Il browser non riproduce questo formato. Puoi comunque scegliere l’istante e vedere i fotogrammi tramite FFmpeg."
    }
  },
  {
    "sources": [
      "PNG to save",
      "PNG da salvare"
    ],
    "text": {
      "en": "PNG to save",
      "it": "PNG da salvare"
    }
  },
  {
    "sources": [
      "Select a frame to see the preview.",
      "Scegli un fotogramma per vedere l’anteprima."
    ],
    "text": {
      "en": "Select a frame to see the preview.",
      "it": "Scegli un fotogramma per vedere l’anteprima."
    }
  },
  {
    "sources": [
      "Selected frame preview",
      "Anteprima del fotogramma selezionato"
    ],
    "text": {
      "en": "Selected frame preview",
      "it": "Anteprima del fotogramma selezionato"
    }
  },
  {
    "sources": [
      "Position",
      "Posizione"
    ],
    "text": {
      "en": "Position",
      "it": "Posizione"
    }
  },
  {
    "sources": [
      "Video position",
      "Posizione nel video"
    ],
    "text": {
      "en": "Video position",
      "it": "Posizione nel video"
    }
  },
  {
    "sources": [
      "Time · seconds or HH:MM:SS",
      "Istante · secondi o HH:MM:SS"
    ],
    "text": {
      "en": "Time · seconds or HH:MM:SS",
      "it": "Istante · secondi o HH:MM:SS"
    }
  },
  {
    "sources": [
      "First frame",
      "Primo frame"
    ],
    "text": {
      "en": "First frame",
      "it": "Primo frame"
    }
  },
  {
    "sources": [
      "Last frame",
      "Ultimo frame"
    ],
    "text": {
      "en": "Last frame",
      "it": "Ultimo frame"
    }
  },
  {
    "sources": [
      "Preview time",
      "Anteprima istante"
    ],
    "text": {
      "en": "Preview time",
      "it": "Anteprima istante"
    }
  },
  {
    "sources": [
      "Save PNG to library",
      "Salva PNG in libreria"
    ],
    "text": {
      "en": "Save PNG to library",
      "it": "Salva PNG in libreria"
    }
  },
  {
    "sources": [
      "Close video",
      "Chiudi video"
    ],
    "text": {
      "en": "Close video",
      "it": "Chiudi video"
    }
  },
  {
    "sources": [
      "Enter seconds or HH:MM:SS.mmm.",
      "Usa secondi oppure HH:MM:SS.mmm."
    ],
    "text": {
      "en": "Enter seconds or HH:MM:SS.mmm.",
      "it": "Usa secondi oppure HH:MM:SS.mmm."
    }
  },
  {
    "sources": [
      "The selected time is past the end of the video.",
      "L’istante scelto è oltre la fine del video."
    ],
    "text": {
      "en": "The selected time is past the end of the video.",
      "it": "L’istante scelto è oltre la fine del video."
    }
  },
  {
    "sources": [
      "Preparing preview…",
      "Preparazione anteprima…"
    ],
    "text": {
      "en": "Preparing preview…",
      "it": "Preparazione anteprima…"
    }
  },
  {
    "sources": [
      "Preview did not load. Try again.",
      "Anteprima non caricata. Riprova."
    ],
    "text": {
      "en": "Preview did not load. Try again.",
      "it": "Anteprima non caricata. Riprova."
    }
  },
  {
    "sources": [
      "Exact last frame",
      "Ultimo frame esatto"
    ],
    "text": {
      "en": "Exact last frame",
      "it": "Ultimo frame esatto"
    }
  },
  {
    "sources": [
      "Preview ready. This PNG will be saved.",
      "Anteprima pronta. Verrà salvato questo PNG."
    ],
    "text": {
      "en": "Preview ready. This PNG will be saved.",
      "it": "Anteprima pronta. Verrà salvato questo PNG."
    }
  },
  {
    "sources": [
      "Open a project first.",
      "Apri prima un progetto."
    ],
    "text": {
      "en": "Open a project first.",
      "it": "Apri prima un progetto."
    }
  },
  {
    "sources": [
      "Video exceeds 120 MiB.",
      "Video oltre 120 MiB."
    ],
    "text": {
      "en": "Video exceeds 120 MiB.",
      "it": "Video oltre 120 MiB."
    }
  },
  {
    "sources": [
      "Loading…",
      "Caricamento…"
    ],
    "text": {
      "en": "Loading…",
      "it": "Caricamento…"
    }
  },
  {
    "sources": [
      "Uploading video to the server…",
      "Caricamento video sul server…"
    ],
    "text": {
      "en": "Uploading video to the server…",
      "it": "Caricamento video sul server…"
    }
  },
  {
    "sources": [
      "Pause to select the frame.",
      "Metti in pausa per scegliere il fotogramma."
    ],
    "text": {
      "en": "Pause to select the frame.",
      "it": "Metti in pausa per scegliere il fotogramma."
    }
  },
  {
    "sources": [
      "Release the slider to update the preview.",
      "Rilascia il cursore per aggiornare l’anteprima."
    ],
    "text": {
      "en": "Release the slider to update the preview.",
      "it": "Rilascia il cursore per aggiornare l’anteprima."
    }
  },
  {
    "sources": [
      "Update the preview before saving.",
      "Aggiorna l’anteprima prima di salvare."
    ],
    "text": {
      "en": "Update the preview before saving.",
      "it": "Aggiorna l’anteprima prima di salvare."
    }
  },
  {
    "sources": [
      "Saving PNG…",
      "Salvataggio PNG…"
    ],
    "text": {
      "en": "Saving PNG…",
      "it": "Salvataggio PNG…"
    }
  },
  {
    "sources": [
      "Frame saved to the project library.",
      "Fotogramma salvato nella libreria del progetto."
    ],
    "text": {
      "en": "Frame saved to the project library.",
      "it": "Fotogramma salvato nella libreria del progetto."
    }
  },
  {
    "sources": [
      "Images · resize, convert or edit",
      "Immagini · ridimensiona, converti o modifica"
    ],
    "text": {
      "en": "Images · resize, convert or edit",
      "it": "Immagini · ridimensiona, converti o modifica"
    }
  },
  {
    "sources": [
      "Images from the active project library.",
      "Immagini dalla libreria del progetto attivo."
    ],
    "text": {
      "en": "Images from the active project library.",
      "it": "Immagini dalla libreria del progetto attivo."
    }
  },
  {
    "sources": [
      "Outputs are saved in the active project library.",
      "I risultati vengono salvati nella libreria del progetto attivo."
    ],
    "text": {
      "en": "Outputs are saved in the active project library.",
      "it": "I risultati vengono salvati nella libreria del progetto attivo."
    }
  },
  {
    "sources": [
      "Project",
      "Progetto"
    ],
    "text": {
      "en": "Project",
      "it": "Progetto"
    }
  },
  {
    "sources": [
      "Library project",
      "Progetto della libreria"
    ],
    "text": {
      "en": "Library project",
      "it": "Progetto della libreria"
    }
  },
  {
    "sources": [
      "Opening project…",
      "Apertura progetto…"
    ],
    "text": {
      "en": "Opening project…",
      "it": "Apertura progetto…"
    }
  },
  {
    "sources": [
      "Invalid project response",
      "Risposta progetto non valida"
    ],
    "text": {
      "en": "Invalid project response",
      "it": "Risposta progetto non valida"
    }
  },
  {
    "sources": [
      "Reset queue",
      "Ripristina coda"
    ],
    "text": {
      "en": "Reset queue",
      "it": "Ripristina coda"
    }
  },
  {
    "sources": [
      "Resetting…",
      "Ripristino…"
    ],
    "text": {
      "en": "Resetting…",
      "it": "Ripristino…"
    }
  },
  {
    "sources": [
      "Queue reset. Cancelled jobs: {n}",
      "Coda ripristinata. Lavori annullati: {n}"
    ],
    "text": {
      "en": "Queue reset. Cancelled jobs: {n}",
      "it": "Coda ripristinata. Lavori annullati: {n}"
    }
  },
  {
    "sources": [
      "Only for stuck jobs: cancels queued or running jobs and restarts workers. Confirmation required.",
      "Solo per lavori bloccati: annulla i lavori in coda o in esecuzione e riavvia i worker. Richiede conferma."
    ],
    "text": {
      "en": "Only for stuck jobs: cancels queued or running jobs and restarts workers. Confirmation required.",
      "it": "Solo per lavori bloccati: annulla i lavori in coda o in esecuzione e riavvia i worker. Richiede conferma."
    }
  },
  {
    "sources": [
      "SDXL paths and options",
      "Percorsi usati e opzioni SDXL"
    ],
    "text": {
      "en": "SDXL paths and options",
      "it": "Percorsi usati e opzioni SDXL"
    }
  },
  {
    "sources": [
      "Licenses · Open source",
      "Licenze · Open source"
    ],
    "text": {
      "en": "Licenses · Open source",
      "it": "Licenze · Open source"
    }
  },
  {
    "sources": [
      "SDXL denoise: lower values preserve more of the input.",
      "Denoise SDXL: valori più bassi preservano maggiormente l’immagine iniziale."
    ],
    "text": {
      "en": "SDXL denoise: lower values preserve more of the input.",
      "it": "Denoise SDXL: valori più bassi preservano maggiormente l’immagine iniziale."
    }
  }
];
 const catalog=window.ZETALVX_LOCALES.entries;
 for(const entry of additions){
  const previous=catalog.filter(old=>old.sources.some(key=>entry.sources.includes(key)));
  entry.text=Object.assign({},...previous.map(old=>old.text),entry.text);
  catalog.push(entry);
 }
})();
