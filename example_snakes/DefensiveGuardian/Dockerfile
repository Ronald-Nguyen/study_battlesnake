FROM python:3.10-slim

# Install app
COPY . /usr/app
WORKDIR /usr/app

# Install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Set default port but allow override via environment variable
ENV PORT=7124

# Expose the port
EXPOSE $PORT

# Run Battlesnake
CMD [ "python", "main.py" ]
