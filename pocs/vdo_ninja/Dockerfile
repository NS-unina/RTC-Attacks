# Usa l'immagine ufficiale di Nuclei come base
FROM projectdiscovery/nuclei:latest

# Imposta la directory di lavoro
WORKDIR /app

# (Opzionale) Copia i tuoi template locali nel container
# Assicurati che il file .yaml sia nella stessa cartella del Dockerfile
# COPY CVE-2025-62613.yaml /app/templates/cve-2025-62613.yaml
RUN nuclei -update-templates

# Comando di default: mostra l'aiuto o resta in attesa
ENTRYPOINT ["nuclei"]
