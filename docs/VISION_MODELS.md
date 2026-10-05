# Vision: modelli locali e API — guida operativa

## Il modello si sceglie prima della generazione delle caption

In **Modelli Vision → Aggiungi** crea uno o più profili. Il nome è libero: per esempio
“Qwen piccolo GGUF”, “Qwen nativo 4-bit” oppure “Agent LAN”. Salva, usa **Verifica file**,
poi **Test con immagine**. Solo il test con immagine esegue davvero inferenza.
La verifica dei file non certifica la compatibilità, i contenuti dei pesi o la licenza.

Nel dataset seleziona un profilo dalla tendina **Modello Vision**. La scelta viene
salvata nel dataset. I lavori usano una copia della configurazione scelta al momento
in cui partono: cambiare un profilo non cambia in corsa il modello di quel lavoro.

I profili delle due applicazioni sono indipendenti. Puoi **Esportare/Importare** un
profilo JSON: non contiene token né immagini; può contenere percorsi locali, endpoint
e istruzioni personalizzate. I pesi possono restare nella stessa cartella condivisa.
L'import non concede autorizzazioni: la verifica dei termini va confermata nuovamente.

## 1. Locale — Transformers / safetensors

Richiede la cartella COMPLETA del modello multimodale: config.json, tutti gli shard
safetensors con eventuale indice, tokenizer, processor e chat template. Un solo
checkpoint, una LoRA o una torre Vision isolata non costituiscono il modello completo.
Il processor può essere nella stessa cartella o in un percorso separato esplicito.

Il campo **Python del runtime** può puntare al tuo ambiente già compatibile. In
alternativa **Prepara runtime Vision** installa solo le librerie in una nuova cartella
`runtime/vision` dell'app. Non scarica pesi, non aggiorna driver, non tocca il venv SDXL.
Richiede Python 3.10–3.12 e venv. Il bootstrap sceglie PyTorch 2.8.0/torchvision 0.23.0
CUDA 12.8, Transformers 5.13.0, accelerate e bitsandbytes. Serve un driver compatibile;
l'installer opzionale non è stato eseguito su una macchina NVIDIA nuova durante questa build.
Per una configurazione diversa usa un Python separato già preparato da te.

Il caricatore controlla `vision_config` e usa il model_type reale, non il nome della
cartella. Include classi Qwen2.5-VL, Qwen3-VL/dense/MoE e Qwen3.5/dense/MoE, con
fallback agli AutoModel multimodali del runtime. Per Qwen3.6/3.8 o altre varianti vale
la config effettiva e il supporto del Transformers installato: non una promessa basata
sul numero “3.x”. Qwen3.8-27B ufficiale dichiara model_type qwen3_5, ma questa build
non è stata testata con i suoi pesi reali. Una variante text-only è rifiutata.

Precisione: native/auto, float16, bfloat16 o float32. Sono disponibili caricamento
bitsandbytes 4-bit/8-bit su CUDA per modelli non già quantizzati. Per AWQ/GPTQ/FP8 o
altre quantizzazioni predisposte usa Native e un runtime che le supporti; se manca un
backend, l'errore è esplicito. Non si promette il supporto di ogni formato né si tenta
una seconda quantizzazione su un modello già quantizzato.

`trust_remote_code=False`, safetensors e caricamento local-only. Il codice remoto
personalizzato dei repository non viene attivato. Per un modello che lo richiede,
usa un backend esterno da te verificato invece di disattivare le protezioni dell'app.

## 2. Locale — GGUF / llama.cpp

Configura tre percorsi locali:
- file del modello `.gguf`;
- projector `mmproj*.gguf` compatibile con QUELLA conversione/modello;
- eseguibile `llama-server` di una build llama.cpp con supporto multimodale adeguato.

Il programma avvia un processo figlio privato, protetto da chiave e legato a
127.0.0.1, su porta libera. Non usa `-hf`, non scarica pesi e non si collega ad altri
llama-server trovati casualmente. Nessun argomento shell arbitrario o comando remoto.
Il binario deve essere già compilato/installato; questa build non lo scarica né lo
compila. Puoi riutilizzare quello di un'altra app senza modificarne i file, purché
compatibile. Il campo context/layers/threads regola quel processo, non altre app.

Il projector non può essere preso da una famiglia diversa. Un GGUF text-only o un
mmproj isolato non bastano. La spunta “disabilita thinking” richiede una build che
supporti chat-template-kwargs; in caso di incompatibilità il test restituisce l'errore.

## 3. API / Agent

URL base con `/v1` o URL completo `/v1/chat/completions`, identificativo modello,
e token opzionale. Il servizio deve supportare input immagine `image_url`.
HTTPS con verifica certificato; HTTP solo loopback. Per HTTPS self-signed remoto puoi
specificare il file CA attendibile, non un “ignora certificato”. Nessun redirect con
credenziali. Le immagini sono inviate solo dopo conferma della richiesta.

Un endpoint valido non significa che quel servizio includa Vision. Il test esegue
una richiesta con immagine, non solo un ping. Nessun account dell'Agent è obbligatorio
per i backend locali. Il token resta in secrets/ con permessi 0600, non cifrato: non
condividere quella cartella. Non è restituito alla GUI o incluso nell'export profili.

## Trigger automatico

Il training usa il TESTO delle caption. Il campo trigger da solo non è un nuovo token.
- **All'inizio**: aggiunge `itapigna, ...` solo se il trigger manca.
- **Alla fine**: aggiunge `..., itapigna` solo se manca.
- **Nel contesto**: chiede al modello di inserire l'esatta parola nella frase; effettua
  un solo nuovo tentativo se manca. Se manca ancora, conserva il risultato e lo marca
  per revisione. Le ripetizioni sono segnalate, non cancellate silenziosamente.

Non serve premere Inserisci per ogni immagine. Se il trigger è già nella frase non
viene duplicato o spostato. Caption già compilate restano intatte; una caption composta
solo dal trigger può essere completata. Una modifica manuale fatta mentre il modello
lavora viene preservata. Se cambi trigger/posizione durante inferenza la vecchia risposta
non sovrascrive il dato: viene segnalata e può essere rigenerata.

La GUI traduce le etichette, non prompt/caption/trigger/nome file. Per default il prompt
caption è in inglese e conciso, modificabile in Advanced. Caption troppo lunghe possono
essere troncate nel Training SDXL: controlla i token nel Training, non soltanto le parole.

## Lavori e memoria GPU

I lavori vengono eseguiti uno alla volta e continuano chiudendo il browser. Annullare
può attendere la chiamata corrente fino al timeout. Dopo un arresto del server il job
risulta interrotto: rilancia solo le caption mancanti. I processi locali della app sono
scaricati dalla memoria dopo il batch/test per default; puoi modificarlo in Advanced.

Nel Zetalvx Image Lab — SDXL Edition il captioning locale usa il proprio blocco GPU e scarica i propri
worker prima di caricare Vision. La Dataset Studio separata non controlla GPU o processi
di altre app: prima di caricare un grande modello locale, libera la VRAM nel Creator.
Nessuna operazione deve uccidere un processo appartenente a un'altra app.

## API dell'app (autenticate)

Le app non espongono un nuovo server pubblico OpenAI-compatible. Il loro backend è
richiamabile tramite le API dell'app, con sessione login e token CSRF:

- GET `/api/vision/models`: lista profili + stato runtime, mai token.
- POST `/api/vision/models`: crea; PUT/DELETE `/api/vision/models/<id>`: modifica/rimuove
  la configurazione, non i pesi sul disco.
- POST `/api/vision/models/<id>/inspect`: verifica i file.
- POST `/api/vision/caption`: `{model_id, image: "BASE64_PNG_O_JPEG_SENZA_PREFISSO_DATA", prompt: "...", confirm: true}`.
  Avvia un test/caption asincrono; leggere GET `/api/vision/actions` fino al risultato.
- POST `/api/vision/unload`: scarica il processo locale quando non è occupato.

Nel Creator usa GET `/api/vision/session` e header `X-CSRF-Token`; nel Dataset il token
viene da GET `/api/session`. Il login è quello locale dell'app. Non memorizzare password
nei progetti. La web UI implementa questi flussi e offre esempi di richiesta nei sorgenti.

## Licenze e fonti

Il codice integrativo dell'app resta Apache-2.0. Il runtime Transformers e il codice
llama.cpp hanno licenze proprie; le revisioni del modello, le quantizzazioni, il
projector e i termini dell'API vanno verificati separatamente. Avere un path locale,
un token valido o il codice aperto non concede diritti commerciali sul modello.
Il pannello registra fonte/licenza annotata e la conferma dell'utente, non certifica
un'autorizzazione. Nessun peso Vision o Identity viene incluso in questi pacchetti.

Fonti primarie consultate il 20 settembre 2026:
- https://huggingface.co/docs/transformers/model_doc/qwen3_vl
- https://huggingface.co/docs/transformers/model_doc/qwen3_5
- https://huggingface.co/Qwen/Qwen3.8-27B
- https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md
- https://github.com/huggingface/transformers/blob/main/LICENSE
- https://github.com/ggml-org/llama.cpp/blob/master/LICENSE


## Aggiornamento 0.1.0.12: test e cronologia

Ogni test usa una snapshot del profilo e mostra i percorsi effettivi. La finestra
segue il suo ID: un vecchio errore resta nella cronologia e non sovrascrive il
risultato nuovo. I profili sono conservati; nessun path o modello deve essere
riscaricato per questo aggiornamento.


## Runtime GGUF gestito (0.1.0.41)
Per GGUF Zetalvx Image Lab può preparare esplicitamente una build binaria ufficiale di llama.cpp da `ggml-org/llama.cpp` sotto `runtime/llama.cpp`. Il download avviene solo dopo conferma dell’utente; il profilo può lasciare vuoto `llama_path` per usare questo runtime. Un percorso manuale resta disponibile nelle opzioni avanzate. I modelli e i relativi termini restano separati dal runtime.
