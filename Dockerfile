# Usar una imagen base oficial de Python (bullseye aún incluye wkhtmltopdf)
FROM python:3.9-slim-bullseye

# Evitar interrupciones interactivas de debconf
ENV DEBIAN_FRONTEND=noninteractive

# Establecer el directorio de trabajo en /app
WORKDIR /app

# Instalar dependencias del sistema y la versión oficial de wkhtmltopdf (con patched Qt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fontconfig \
    libfreetype6 \
    libjpeg62-turbo \
    libpng16-16 \
    libx11-6 \
    libxcb1 \
    libxext6 \
    libxrender1 \
    xfonts-75dpi \
    xfonts-base \
    && ARCH=$(dpkg --print-architecture) \
    && wget -nv "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.bullseye_${ARCH}.deb" -O /tmp/wkhtmltox.deb \
    && (dpkg -i /tmp/wkhtmltox.deb || apt-get install -f -y --no-install-recommends) \
    && rm -f /tmp/wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* \
    && wkhtmltopdf --version

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
