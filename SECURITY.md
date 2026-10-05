# Public source distribution security notes

Run a source checkout only with code and model files you trust, under your normal user. This is a local/trusted-LAN application, not a hosted multi-tenant service or a ready-made Internet deployment.

Use `source.py` and its separate data home; do not point it at a packaged installation. No secret/token is required in the repository. Do not post credentials, cookies, model access tokens, certificate private keys, datasets or private logs in public issues. Report a suspected vulnerability privately using a contact channel independently verified from the project owner's official profile; this candidate does not invent a security email or promise a response SLA.

The static tests are not a security certification. Exact dependency pins and original security gates are retained, not newly certified as advisory-free by this source packaging pass.

---
## Inherited application security documentation


# Sicurezza — candidata 0.1.0.42

Ambito previsto: account amministratore fidato, loopback oppure LAN fidata.
Non esporre direttamente la porta su Internet. HTTPS resta attivo per default.
I certificati locali sono autofirmati; non si installano CA nei trust store.

## Correzioni di questa revisione
- Nomi di file importati portabili, senza traversal/drive/ADS/nomi riservati/link.
- Credenziali scritte atomicamente: permessi POSIX o DACL Windows restrittiva
  per utente corrente, SYSTEM e amministratori. File locali non cifrati.
- Download Vision accodati/attivi inclusi nei controlli di manutenzione.
- Login: richieste massime 16 KiB, campo password massimo 1024 caratteri;
  8 tentativi per peer in 60 s, massimo 60 prenotazioni globali nella finestra.
  Stato persistente SQLite, prenotazione prima del calcolo hash. Successo azzera
  i tentativi del peer. Indirizzi remoti derivati dal socket, non da X-Forwarded-For.
- Cheroot WSGI/TLS per il servizio web pubblico. Flask rimane il framework e
  nessuna pipeline AI cambia. TLS minimo 1.2; nessun fallback a HTTP per errori TLS.
- Runtime GGUF: identità release registrata, confronto SHA-256 upstream obbligatorio
  prima di estrarre/eseguire, limite dimensioni, backup transazionale e avvisi conservati.
- Modifiche firewall con consenso esplicito sull'effetto per altre app Python;
  registro durevole e ripristino controllato dei soli elementi registrati e invariati.

## Limiti espliciti
Non è una certificazione, un penetration test completo o una prova di assenza di
vulnerabilità. L'audit dei pacchetti consulta un feed e lascia UNKNOWN inconcludente.
I manifest delle ZIP non sono firme dell'autore: importare aggiornamenti solo
attraverso canali affidabili dopo controllo della provenienza e consenso.

Non blocchiamo un amministratore locale ostile o il proprietario dell'installazione.
I backup/configurazioni installati possono contenere segreti. Le API Vision esterne
ricevono i contenuti inviati al provider scelto; non descrivere quel flusso come offline.

La libreria Cheroot e le ACL/UAC Windows richiedono collaudo nativo finale. I nuovi
smoke test vengono eseguiti con vere dipendenze sul runtime candidato durante
l'installazione, prima dello switch. Consultare il rapporto corrente per test
saltati qui, differenze rispetto alla .41 e verifiche restanti.

## Ripristino firewall
I nuovi registri sono sotto shared/audits/firewall/<operazione>/journal.json.
`creator-sdxl firewall-restore PERCORSO_JOURNAL` mostra l'anteprima, senza cambiare
regole. Con `--apply` vengono richiesti RESTORE e UAC. Sono riabilitati solo i
Block registrati ancora disabilitati e con proprietà invariate; la regola creata
dall'app viene rimossa soltanto se invariata. Regole estranee o modificate vengono
saltate. Le operazioni anteriori alla .42 non hanno registri ricostruiti a posteriori.
Non è eseguito un reset globale del firewall né un ripristino automatico indiscriminato.
