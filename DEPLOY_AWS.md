# Deploy AI Job Hunter on AWS EC2 (Ubuntu)

You have: EC2 with Ubuntu AMI, security group with ports **22** (SSH), **80** (HTTP), **8501** (Streamlit).

## 1. SSH into your EC2 instance

```bash
ssh -i "your-key.pem" ubuntu@<EC2_PUBLIC_IP>
```

Replace `your-key.pem` with your key path and `<EC2_PUBLIC_IP>` with your instance’s public IP.

---

## 2. Install dependencies on Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

---

## 3. Clone your repository

```bash
cd ~
git clone https://github.com/SanketDeshmukh29/AI-Job-Hunter-A-360-Career-Agent.git
cd AI-Job-Hunter-A-360-Career-Agent
```

If the repo is private, use a personal access token or deploy key.

---

## 4. Create virtual environment and install Python packages

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Set up secrets (API keys)

**Do not commit real API keys to Git.** Create the secrets file only on the server.

```bash
mkdir -p .streamlit
nano .streamlit/secrets.toml
```

Paste (with your real keys):

```toml
GEMINI_API_KEY = "your-gemini-api-key"
JSEARCH_API_KEY = "your-jsearch-rapidapi-key"
```

Save (Ctrl+O, Enter, Ctrl+X).

---

## 6. Run Streamlit so it’s reachable from the internet

Bind to all interfaces and use port 8501:

```bash
source .venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

- App URL: **http://\<EC2_PUBLIC_IP\>:8501**
- To run in background:  
  `nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &`

---

## 7. (Optional) Run as a systemd service (auto-start, restart on crash)

Create the service file:

```bash
sudo nano /etc/systemd/system/streamlit-ai-job-hunter.service
```

Paste (replace `ubuntu` with your EC2 user if different):

```ini
[Unit]
Description=AI Job Hunter Streamlit App
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/AI-Job-Hunter-A-360-Career-Agent
Environment="PATH=/home/ubuntu/AI-Job-Hunter-A-360-Career-Agent/.venv/bin"
ExecStart=/home/ubuntu/AI-Job-Hunter-A-360-Career-Agent/.venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable streamlit-ai-job-hunter
sudo systemctl start streamlit-ai-job-hunter
sudo systemctl status streamlit-ai-job-hunter
```

Logs: `sudo journalctl -u streamlit-ai-job-hunter -f`

---

## 8. (Optional) Use port 80 with Nginx (reverse proxy)

So users can open **http://\<EC2_PUBLIC_IP\>** instead of `:8501`:

```bash
sudo apt install -y nginx
sudo nano /etc/nginx/sites-available/streamlit
```

Paste:

```nginx
server {
    listen 80;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/streamlit /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Ensure Streamlit is running (step 6 or 7). Then open **http://\<EC2_PUBLIC_IP\>**.

---

## Checklist

| Step | Done |
|------|------|
| EC2 security group: 22, 80, 8501 | ✓ |
| SSH and install Python/git | |
| Clone repo, venv, `pip install -r requirements.txt` | |
| Create `.streamlit/secrets.toml` (Gemini + JSearch keys) | |
| Run Streamlit with `--server.address 0.0.0.0` | |
| (Optional) systemd service | |
| (Optional) Nginx on port 80 | |

---

## Troubleshooting

- **Can’t connect to app**  
  - Check security group allows **8501** (and **80** if using Nginx) for your IP or `0.0.0.0/0`.  
  - Confirm Streamlit is running: `ps aux | grep streamlit`.

- **Missing GEMINI_API_KEY**  
  - Ensure `.streamlit/secrets.toml` exists in the app directory and contains `GEMINI_API_KEY`.

- **Repo private**  
  - Use HTTPS with a personal access token, or add the EC2 SSH key as a deploy key in GitHub.

- **Port 80 permission errors**  
  - Use Nginx (or another reverse proxy) to listen on 80; run Streamlit on 8501.
