# Usar una imagen base oficial de Python (bullseye aún incluye wkhtmltopdf)
FROM python:3.9-slim-bullseye

# Evitar interrupciones interactivas de debconf
ENV DEBIAN_FRONTEND=noninteractive

# Establecer el directorio de trabajo en /app
WORKDIR /app

# Instalar dependencias del sistema requeridas para pdfkit (wkhtmltopdf) usando archive.debian.org
RUN echo 'deb http://archive.debian.org/debian bullseye main contrib non-free' > /etc/apt/sources.list \
    && echo 'deb http://archive.debian.org/debian-security bullseye-security main contrib non-free' >> /etc/apt/sources.list \
    && echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99archive \
    && apt-get update && apt-get install -y --no-install-recommends \
        wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de dependencias
COPY requirements.txt .

# Instalar las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el contenido del proyecto al contenedor
COPY . .

# Crear el directorio para la base de datos local (por si acaso o fallback)
RUN mkdir -p database

# Exponer el puerto que Render usará
EXPOSE $PORT

# Comando para iniciar la aplicación con gunicorn
CMD gunicorn app:app --bind 0.0.0.0:$PORT
