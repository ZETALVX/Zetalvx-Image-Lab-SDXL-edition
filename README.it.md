# Zetalvx Image Lab — SDXL Edition

**Zetalvx Labs**

*Workspace locale per generazione, modifica, training, Identity e Vision con SDXL.*

> **Distribuzione sorgente:** questo repository contiene il codice dell’applicazione. Non include pesi AI, dataset, credenziali, driver NVIDIA/CUDA, binari FFmpeg o ambienti Python preassemblati.

**Licenza:** Apache-2.0 per il codice dell’app. Software di terze parti, modelli e contenuti forniti dall’utente mantengono le rispettive licenze.

---

## Panoramica

Zetalvx Image Lab — SDXL Edition è un workspace locale accessibile dal browser che riunisce i principali flussi Stable Diffusion XL in un’unica interfaccia.

Funzioni principali:

- generazione Text-to-Image con SDXL;
- Img2Img e Inpainting;
- checkpoint e LoRA;
- preset utente e test di parametri;
- dataset e caption;
- training LoRA SDXL;
- caption assistite da Vision;
- InstantID / Face Consistency;
- Face Swap con rifinitura SDXL opzionale;
- progetti, libreria immagini, code e cronologia;
- strumenti media e integrazione FFmpeg dove configurata;
- accesso locale o LAN fidata tramite HTTPS.

I modelli AI non sono inclusi nel repository.

## Installazione

La versione Source usa ambienti Python separati e una cartella dati distinta dalle build installabili.

- [Guida Linux](docs/INSTALL_LINUX.md)
- [Guida Windows](docs/INSTALL_WINDOWS.md)
- [Uso della versione Source](docs/SOURCE_OPERATION.md)

### Cartella dati Source

Linux:

```text
~/.local/share/CreatorStudioSDXL-Source
```

Windows:

```text
%LOCALAPPDATA%\CreatorStudioSDXL-Source
```

Non usare la cartella dati di una build installabile come home della versione Source.

## Requisiti

- sistema operativo a 64 bit;
- Python 3.11 a 64 bit;
- browser moderno;
- connessione Internet durante l’installazione delle dipendenze;
- spazio sufficiente per ambienti e modelli;
- per CUDA: GPU NVIDIA compatibile e driver già funzionante.

La procedura Source non installa né sostituisce i driver NVIDIA o un toolkit CUDA globale.

## Avvio locale

Dopo aver completato la guida del proprio sistema operativo, apri:

```text
https://127.0.0.1:8298
```

Il certificato HTTPS è locale e autofirmato, quindi al primo collegamento il browser può mostrare un avviso.

## Modelli e licenze

La licenza Apache-2.0 dell’app non sostituisce le licenze di checkpoint, LoRA, InstantID, InsightFace, modelli Face Swap, modelli Vision, llama.cpp, FFmpeg o dataset/media forniti dall’utente.

Consulta:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [Modelli e licenze](docs/MODELS_AND_LICENSES.md)
- [Attribuzioni e ridistribuzione](docs/ATTRIBUTION_AND_LICENSES.md)

## Sicurezza

L’app è pensata principalmente per uso locale o su LAN fidata. Non esporre direttamente l’applicazione o le porte dei worker su Internet. Mantieni private password, token, chiavi API e log contenenti dati personali.

Per le segnalazioni di sicurezza consulta [SECURITY.md](SECURITY.md).

## Contribuire

Bug report e contributi tecnici sono benvenuti. Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

---

**Zetalvx Image Lab — SDXL Edition** fa parte della famiglia software **Zetalvx Labs**.
